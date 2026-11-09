//! Windows S61 MK2 NI display transport with selectable client identifiers.
//! Adapted from Encdr 0.9.0's GPL-3.0-or-later named-pipe client:
//! https://github.com/RufusIbiza/Encdr/blob/v0.9.0/encdr/src/usb/ni_service/windows.rs
//! Purpose: NIHostIntegrationAgent refuses the stock Maschine bootstrap
//! on some Komplete Kontrol devices. Allow the KKiN client identifier,
//! and include each stage in diagnostic output. No driver modifications.

use std::sync::mpsc::{channel, Sender};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use windows_sys::Win32::Foundation::{
    CloseHandle, GetLastError, ERROR_PIPE_BUSY, ERROR_PIPE_CONNECTED, GENERIC_READ, GENERIC_WRITE, HANDLE,
    INVALID_HANDLE_VALUE,
};
use windows_sys::Win32::Storage::FileSystem::{
    CreateFileW, ReadFile, WriteFile, OPEN_EXISTING, PIPE_ACCESS_DUPLEX,
};
use windows_sys::Win32::System::Pipes::{
    ConnectNamedPipe, CreateNamedPipeW, DisconnectNamedPipe, PeekNamedPipe, SetNamedPipeHandleState,
    WaitNamedPipeW, PIPE_READMODE_MESSAGE, PIPE_TYPE_MESSAGE, PIPE_WAIT,
};

use encdr::usb::ni_service::protocol::{self, TRUE_WORD};
use std::sync::mpsc::{Receiver, RecvTimeoutError};

const KONTROL_ROLE: u32 = 0x4e694b4b;
const MASCHINE_ROLE: u32 = 0x4e694d32;
const CLIENT_ROLE: u32 = 0x70726d79;

fn role_label(kind: u32) -> &'static str {
    if kind == KONTROL_ROLE { "KKiN" } else { "NiM2" }
}

fn roles_to_try() -> Vec<u32> {
    match std::env::var("KSW_NI_ROLE").unwrap_or_else(|_| "auto".to_string()).to_lowercase().as_str() {
        "kontrol" | "kkin" => vec![KONTROL_ROLE],
        "maschine" | "nim2" => vec![MASCHINE_ROLE],
        "auto" => vec![KONTROL_ROLE, MASCHINE_ROLE],
        unknown => {
            eprintln!("Unknown KSW_NI_ROLE={unknown:?}; using auto");
            vec![KONTROL_ROLE, MASCHINE_ROLE]
        }
    }
}

fn words(parts: &[u32]) -> Vec<u8> {
    parts.iter().flat_map(|part| part.to_le_bytes()).collect()
}

/// Global registration is usually a 21-byte packet on Windows:
/// five LE u32 words, final serial length = 1, and one trailing NUL.
/// Encdr's earlier 20-byte version declared serial length = 0 and
/// omitted the NUL. Preserve that older framing as a fallback.
fn device_connect(product_id: u16, kind: u32, terminated_serial: bool) -> Vec<u8> {
    let mut packet = words(&[
        0x0344_7500, product_id as u32, kind, CLIENT_ROLE,
        if terminated_serial { 1 } else { 0 },
    ]);
    if terminated_serial {
        packet.push(0);
    }
    packet
}

fn instance_connect(product_id: u16, serial: &str, kind: u32) -> Vec<u8> {
    let mut packet = words(&[0x0344_4900, product_id as u32, kind, CLIENT_ROLE, serial.len() as u32 + 1]);
    packet.extend_from_slice(serial.as_bytes());
    packet.push(0);
    packet
}

fn pick_serial(rx: &Receiver<Vec<u8>>, wanted: Option<&str>, timeout: Duration) -> Result<String, String> {
    const GRACE: Duration = Duration::from_millis(1500);
    let mut deadline = Instant::now() + timeout;
    let mut serials: Vec<String> = Vec::new();
    let mut chosen: Option<String> = None;
    while chosen.is_none() {
        let left = deadline.saturating_duration_since(Instant::now());
        if left.is_zero() { break; }
        match rx.recv_timeout(left.min(Duration::from_millis(200))) {
            Ok(data) => {
                if let Some(state) = protocol::parse_device_state(&data) {
                    if state.present {
                        if wanted.is_some_and(|s| s.eq_ignore_ascii_case(&state.serial)) {
                            chosen = Some(state.serial);
                        } else if !serials.contains(&state.serial) {
                            serials.push(state.serial);
                            deadline = deadline.min(Instant::now() + GRACE);
                        }
                    }
                }
            }
            Err(RecvTimeoutError::Timeout) => {}
            Err(RecvTimeoutError::Disconnected) => break,
        }
    }
    chosen.or_else(|| serials.into_iter().next())
        .ok_or_else(|| "NI service did not announce an S61 MK2 device serial".to_string())
}


fn wide(s: &str) -> Vec<u16> {
    s.encode_utf16().chain(std::iter::once(0)).collect()
}

fn pipe_path(name: &str) -> Vec<u16> {
    wide(&format!(r"\\.\pipe\{name}"))
}

/// Client end of a pipe the service created.
struct ClientPipe(HANDLE);

// SAFETY: a pipe HANDLE can be used from any thread; access is serialised by
// the callers (a `Mutex` around the only shared instance).
unsafe impl Send for ClientPipe {}
unsafe impl Sync for ClientPipe {}

impl Drop for ClientPipe {
    fn drop(&mut self) {
        unsafe { CloseHandle(self.0) };
    }
}

impl ClientPipe {
    fn open(name: &str, attempts: u32) -> Result<Self, String> {
        let path = pipe_path(name);
        let mut last = 0;
        for attempt in 0..attempts.max(1) {
            let h = unsafe {
                CreateFileW(
                    path.as_ptr(),
                    GENERIC_READ | GENERIC_WRITE,
                    0,
                    std::ptr::null(),
                    OPEN_EXISTING,
                    0,
                    std::ptr::null_mut(),
                )
            };
            if h != INVALID_HANDLE_VALUE {
                let mode = PIPE_READMODE_MESSAGE;
                if unsafe { SetNamedPipeHandleState(h, &mode, std::ptr::null(), std::ptr::null()) } == 0 {
                    tracing::debug!("SetNamedPipeHandleState failed for '{name}' ({})", unsafe { GetLastError() });
                }
                return Ok(Self(h));
            }
            last = unsafe { GetLastError() };
            if last == ERROR_PIPE_BUSY {
                unsafe { WaitNamedPipeW(path.as_ptr(), 500) };
            } else if attempt + 1 < attempts {
                thread::sleep(Duration::from_millis(200));
            }
        }
        Err(format!(r"could not open \\.\pipe\{name} (Windows error {last})"))
    }

    fn write(&self, data: &[u8]) -> Result<(), String> {
        let mut written: u32 = 0;
        let ok = unsafe { WriteFile(self.0, data.as_ptr().cast(), data.len() as u32, &mut written, std::ptr::null_mut()) };
        if ok == 0 {
            return Err(format!("writing to the NI service failed (Windows error {})", unsafe { GetLastError() }));
        }
        Ok(())
    }

    /// Wait up to `timeout` for a reply message. `Ok(None)` means none came.
    fn read_reply(&self, timeout: Duration) -> Result<Option<Vec<u8>>, String> {
        let start = Instant::now();
        loop {
            let mut avail: u32 = 0;
            let peeked = unsafe {
                PeekNamedPipe(self.0, std::ptr::null_mut(), 0, std::ptr::null_mut(), &mut avail, std::ptr::null_mut())
            };
            if peeked == 0 {
                return Err(format!("the NI service closed the pipe (Windows error {})", unsafe { GetLastError() }));
            }
            if avail > 0 {
                let mut buf = vec![0u8; avail.max(4096) as usize];
                let mut read: u32 = 0;
                let ok = unsafe { ReadFile(self.0, buf.as_mut_ptr().cast(), buf.len() as u32, &mut read, std::ptr::null_mut()) };
                if ok != 0 {
                    buf.truncate(read as usize);
                    return Ok(Some(buf));
                }
            }
            let waited = start.elapsed();
            if waited >= timeout {
                return Ok(None);
            }
            // Spin briefly for low latency, then back off.
            if waited < Duration::from_millis(20) {
                thread::yield_now();
            } else {
                thread::sleep(Duration::from_millis(1));
            }
        }
    }

    /// Write and read the reply in one step; for the bootstrap pipe, where
    /// every request is answered.
    fn transact(&self, request: &[u8]) -> Result<Vec<u8>, String> {
        self.write(request)?;
        // Block in ReadFile rather than polling: the service closes the
        // bootstrap pipe right after replying, and a reply not yet read is
        // lost (Windows error 233) when it does.
        let mut buf = vec![0u8; 4096];
        let mut read: u32 = 0;
        let ok = unsafe { ReadFile(self.0, buf.as_mut_ptr().cast(), buf.len() as u32, &mut read, std::ptr::null_mut()) };
        if ok == 0 {
            return Err(format!("the NI service closed the pipe (Windows error {})", unsafe { GetLastError() }));
        }
        buf.truncate(read as usize);
        Ok(buf)
    }
}

/// Serve a notification pipe the service connects back to. Messages are
/// forwarded to `events`; each is acknowledged with an empty reply.
fn serve_notifications(name: String, events: Sender<Vec<u8>>) -> Result<(), String> {
    let path = pipe_path(&name);
    let h = unsafe {
        CreateNamedPipeW(
            path.as_ptr(),
            PIPE_ACCESS_DUPLEX,
            PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
            1,
            65536,
            65536,
            5000,
            std::ptr::null(),
        )
    };
    if h == INVALID_HANDLE_VALUE {
        return Err(format!(r"could not create \\.\pipe\{name} (Windows error {})", unsafe { GetLastError() }));
    }
    let h = h as isize;
    thread::Builder::new()
        .name("encdr-ni-notify".to_string())
        .spawn(move || {
            let h = h as HANDLE;
            loop {
                let connected = unsafe { ConnectNamedPipe(h, std::ptr::null_mut()) };
                if connected == 0 && unsafe { GetLastError() } != ERROR_PIPE_CONNECTED {
                    break;
                }
                loop {
                    let mut buf = vec![0u8; 65536];
                    let mut read: u32 = 0;
                    let ok = unsafe { ReadFile(h, buf.as_mut_ptr().cast(), buf.len() as u32, &mut read, std::ptr::null_mut()) };
                    if ok == 0 || read == 0 {
                        break;
                    }
                    buf.truncate(read as usize);
                    tracing::trace!(
                        "NI service notification on '{name}': {} bytes {:02x?}",
                        buf.len(),
                        &buf[..buf.len().min(128)]
                    );
                    let _ = events.send(buf);
                    let mut written: u32 = 0;
                    let acked = unsafe { WriteFile(h, [0u8; 1].as_ptr().cast(), 0, &mut written, std::ptr::null_mut()) };
                    if acked == 0 {
                        break;
                    }
                }
                unsafe { DisconnectNamedPipe(h) };
            }
            unsafe { CloseHandle(h) };
        })
        .map_err(|e| e.to_string())?;
    Ok(())
}

/// Register with the service for the bootstrap step shared by device and
/// instance connects, returning the request pipe.
fn register(bootstrap_name: &str, request: &[u8], events: &Sender<Vec<u8>>) -> Result<ClientPipe, String> {
    let bootstrap = ClientPipe::open(bootstrap_name, 10)?;
    let reply = bootstrap.transact(request).map_err(|e| format!("connect request: {e}"))?;
    drop(bootstrap);
    let ports = protocol::parse_connect_reply(&reply)?;
    serve_notifications(ports.notification.clone(), events.clone())?;
    let request_pipe = ClientPipe::open(&ports.request, 10)?;
    request_pipe
        .write(&protocol::ack_notification_port(&ports.notification))
        .map_err(|e| format!("notification port ack: {e}"))?;
    request_pipe.read_reply(Duration::from_millis(500)).map_err(|e| format!("notification port ack reply: {e}"))?;
    Ok(request_pipe)
}

/// A registered client session for one physical device.
pub struct ServiceSession {
    /// Held open so the service keeps the device-level registration.
    _device: Mutex<ClientPipe>,
    instance: Mutex<ClientPipe>,
    _notification_rx: Receiver<Vec<u8>>,
}

impl ServiceSession {
    /// Connect to the service and register for the unit with the given
    /// serial number (or the first one it reports when `serial` is `None` or
    /// not found).
    pub fn connect(product_id: u16, serial: Option<&str>, timeout: Duration) -> Result<Self, String> {
        let mut failures = Vec::new();
        let mut checked = false;
        // Prioritize the framing used by DrivenByKate's Windows NI client.
        // Retain Encdr's original zero-length frame if the service requires it.
        for terminated in [true, false] {
            let framing = if terminated { "nul-terminated-21" } else { "zero-length-20" };
            for kind in roles_to_try() {
                for &bootstrap_name in protocol::BOOTSTRAP_PIPES {
                    if ClientPipe::open(bootstrap_name, 1).is_err() {
                        continue;
                    }
                    checked = true;
                    eprintln!(
                        "NI service handshake: pipe={bootstrap_name}, role={}, frame={framing}",
                        role_label(kind)
                    );
                    match Self::connect_via(bootstrap_name, product_id, serial, timeout, kind, terminated) {
                        Ok(session) => {
                            eprintln!(
                                "NI service handshake accepted: pipe={bootstrap_name}, role={}, frame={framing}",
                                role_label(kind)
                            );
                            return Ok(session);
                        }
                        Err(err) => {
                            eprintln!(
                                "NI service handshake failed: pipe={bootstrap_name}, role={}, frame={framing}: {err}",
                                role_label(kind)
                            );
                            failures.push(format!("{bootstrap_name}/{}/{framing}: {err}", role_label(kind)));
                        }
                    }
                }
            }
        }
        if !checked {
            return Err("neither NI hardware-service bootstrap pipe is available".into());
        }
        Err(format!("NI registration unsuccessful [{}]", failures.join(" ; ")))
    }

    fn connect_via(
        bootstrap_name: &str,
        product_id: u16,
        serial: Option<&str>,
        timeout: Duration,
        kind: u32,
        terminated_serial: bool,
    ) -> Result<Self, String> {
        let (tx, rx) = channel::<Vec<u8>>();
        let device = register(bootstrap_name, &device_connect(product_id, kind, terminated_serial), &tx)
            .map_err(|e| format!("device bootstrap: {e}"))?;
        device.write(&protocol::device_state_request()).map_err(|e| format!("device state request: {e}"))?;

        let serial = pick_serial(&rx, serial, timeout)?;
        tracing::info!("NI service ('{bootstrap_name}') reports device {serial}; registering for its screens");
        // Hold notifications open so the service retains this registration.

        let instance = register(bootstrap_name, &instance_connect(product_id, &serial, kind), &tx)
            .map_err(|e| format!("instance bootstrap: {e}"))?;
        for (i, message) in protocol::instance_setup(product_id).into_iter().enumerate() {
            instance.write(&message).map_err(|e| format!("setup message {i}: {e}"))?;
            instance.read_reply(Duration::from_millis(40)).map_err(|e| format!("setup message {i} reply: {e}"))?;
        }

        Ok(Self { _device: Mutex::new(device), instance: Mutex::new(instance), _notification_rx: rx })
    }

    /// Draw a screen command stream (the bytes a USB bulk transfer would
    /// carry) on display `display`, waiting for the service to accept it.
    pub fn send_display(&self, display: u8, width: u16, height: u16, commands: &[u8]) -> Result<(), String> {
        let message = protocol::display_message(display, width, height, commands);
        let pipe = self.instance.lock().map_err(|_| "NI service session poisoned".to_string())?;
        pipe.write(&message)?;
        match pipe.read_reply(protocol::DISPLAY_REPLY_TIMEOUT)? {
            Some(reply) if reply.get(..4).is_some_and(|w| w == TRUE_WORD.to_le_bytes()) => Ok(()),
            Some(reply) => Err(format!("{} (reply {:02x?})", "the NI service rejected a frame",&reply[..reply.len().min(8)])),
            None => Err("the NI service did not acknowledge a frame in time".to_string()),
        }
    }
}

pub fn connect_with_retry(product_id: u16, serial: Option<&str>, timeout: Duration)
    -> Result<ServiceSession, String>
{
    let mut last = String::new();
    for attempt in 0..2 {
        match ServiceSession::connect(product_id, serial, timeout) {
            Ok(session) => return Ok(session),
            Err(err) => {
                last = err;
                if attempt == 0 { std::thread::sleep(Duration::from_millis(300)); }
            }
        }
    }
    Err(last)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn kontrol_role_packets_use_distinct_kind() {
        assert_eq!(device_connect(0x1620, KONTROL_ROLE, true)[8..12], KONTROL_ROLE.to_le_bytes());
        assert_eq!(device_connect(0x1620, MASCHINE_ROLE, true)[8..12], MASCHINE_ROLE.to_le_bytes());
        assert_eq!(instance_connect(0x1620, "XYZ", KONTROL_ROLE)[20..], *b"XYZ\0");
        assert_eq!(&instance_connect(0x1620, "XYZ", KONTROL_ROLE)[16..20], &4u32.to_le_bytes());
    }

    #[test]
    fn bootstrap_null_terminated_and_legacy_frames() {
        let modern = device_connect(0x1620, KONTROL_ROLE, true);
        assert_eq!(modern.len(), 21);
        assert_eq!(&modern[..8], &[0x00, 0x75, 0x44, 0x03, 0x20, 0x16, 0, 0]);
        assert_eq!(&modern[16..20], &1u32.to_le_bytes());
        assert_eq!(modern[20], 0);

        let legacy = device_connect(0x1620, KONTROL_ROLE, false);
        assert_eq!(legacy.len(), 20);
        assert_eq!(&legacy[16..20], &0u32.to_le_bytes());
    }
}
