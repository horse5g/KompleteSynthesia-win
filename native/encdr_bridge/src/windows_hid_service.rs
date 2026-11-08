//! Windows S61 MK2 backend using official drivers, NOT WinUSB/Zadig.
//! Encdr's discovery via nusb requires WinUSB, but the normal S61 MK2 has HID
//! for MI_02 and a Native Instruments driver for MI_03. We therefore connect
//! HID directly and use Encdr's public NI hardware-service screen protocol.

use std::error::Error;
use std::sync::mpsc::{sync_channel, TrySendError};
use std::time::Duration;

use encdr::screen::protocol::encode_ni_color_rle;
use crate::ni_service_compat as ni_service;
use hidapi::{HidApi, HidDevice};
use serde_json::json;

use crate::{emit, receive_commands, Command, FRAME_BYTES};

const VID: u16 = 0x17cc;
const PID: u16 = 0x1620;
const FIRST_BUTTON_REPORT: u8 = 0x01;
const KNOBS_REPORT: u8 = 0xaa;
const WIDTH: usize = 960;
const HEIGHT: usize = 272;

const BUTTONS: &[(&str, usize, u8)] = &[
    ("top_1", 1, 0x10), ("top_2", 1, 0x20),
    ("top_3", 1, 0x40), ("top_4", 1, 0x80),
    ("top_5", 1, 0x01), ("top_6", 1, 0x02),
    ("top_7", 1, 0x04), ("top_8", 1, 0x08),
    ("play", 2, 0x10), ("restart", 2, 0x20),
    ("stop", 3, 0x01), ("rec", 3, 0x02),
    ("metro", 3, 0x08), ("preset_up", 3, 0x10),
    ("page_right", 3, 0x20), ("preset_down", 3, 0x40),
    ("page_left", 3, 0x80), ("mute", 4, 0x01),
    ("solo", 4, 0x02), ("scene", 4, 0x04),
    ("clear", 4, 0x20), ("plugin", 5, 0x02),
    ("setup", 5, 0x08), ("midi", 5, 0x20),
    ("encoder_main_left", 6, 0x10),
    ("encoder_main_up", 6, 0x20),
    ("encoder_main_down", 6, 0x40),
    ("encoder_main_right", 6, 0x80),
    ("encoder_main_press", 6, 0x08),
];

fn led_frame(colors: &[u8; 61]) -> Vec<u8> {
    let mut output = Vec::with_capacity(62);
    output.push(0x81);
    output.extend_from_slice(colors);
    output
}

fn open_s61() -> Result<HidDevice, Box<dyn Error>> {
    let api = HidApi::new()?;
    let found: Vec<_> = api.device_list()
        .filter(|d| d.vendor_id() == VID && d.product_id() == PID)
        .collect();
    if found.is_empty() {
        return Err("Windows HID enumeration did not find S61 MK2 (17cc:1620)".into());
    }
    for d in &found {
        eprintln!(
            "HID candidate {:04x}:{:04x} interface={} path={:?}",
            d.vendor_id(), d.product_id(), d.interface_number(), d.path()
        );
    }
    // Use MI_02 rather than another USB function; do not assume which
    // candidate HidApi::open(VID, PID) will select.
    let device_info = found.iter().find(|d| d.interface_number() == 2)
        .or_else(|| found.first())
        .ok_or("No S61 HID interface present")?;
    let hid = device_info.open_device(&api)
        .map_err(|e| format!("Unable to open S61 HID MI_02: {e}"))?;
    hid.write(&[0xa0, 0x00, 0x00])?;
    hid.write(&led_frame(&[0; 61]))?;
    Ok(hid)
}

#[derive(Default)]
struct ButtonState {
    last_buttons: Option<[u8; 32]>,
    last_knobs: Option<[u8; 8]>,
}

fn delta_wrap(previous: u8, current: u8, modulus: i32) -> i32 {
    let mut delta = current as i32 - previous as i32;
    if delta > modulus / 2 {
        delta -= modulus;
    } else if delta < -modulus / 2 {
        delta += modulus;
    }
    delta
}

impl ButtonState {
    fn receive(&mut self, packet: &[u8]) {
        if packet.is_empty() {
            return;
        }
        if packet[0] == FIRST_BUTTON_REPORT && packet.len() >= 32 {
            let mut current = [0u8; 32];
            current.copy_from_slice(&packet[..32]);
            if let Some(old) = self.last_buttons {
                for (name, byte, mask) in BUTTONS {
                    let pressed = current[*byte] & mask != 0;
                    let before = old[*byte] & mask != 0;
                    if pressed != before {
                        emit(json!({"kind": "button", "name": name, "pressed": pressed}));
                    }
                }
                let before = old[30] & 0x0f;
                let now = current[30] & 0x0f;
                let delta = delta_wrap(before, now, 16);
                if delta != 0 {
                    emit(json!({"kind": "encoder", "name": "encoder_main", "delta": delta}));
                }
            }
            self.last_buttons = Some(current);
        } else if packet[0] == KNOBS_REPORT && packet.len() >= 33 {
            let mut current = [0u8; 8];
            for (index, slot) in current.iter_mut().enumerate() {
                *slot = packet[17 + index * 2];
            }
            if let Some(old) = self.last_knobs {
                for i in 0..8 {
                    let delta = delta_wrap(old[i], current[i], 256);
                    if delta != 0 {
                        emit(json!({"kind": "encoder", "name": format!("encoder_{}", i + 1), "delta": delta}));
                    }
                }
            }
            self.last_knobs = Some(current);
        }
    }
}

/// Convert each 480x272 panel from Python's RGBA8888 to device-native RGB565
/// (the protocol calls this BGR565-BE). Do not dither this diagnostic build.
fn panel_native(pixels: &[u8], screen: usize) -> Vec<u8> {
    let mut native = Vec::with_capacity(480 * HEIGHT * 2);
    for y in 0..HEIGHT {
        for x in 0..480 {
            let at = (y * WIDTH + screen * 480 + x) * 4;
            let r = (pixels[at] as u16) >> 3;
            let g = (pixels[at + 1] as u16) >> 2;
            let b = (pixels[at + 2] as u16) >> 3;
            native.extend_from_slice(&((r << 11) | (g << 5) | b).to_be_bytes());
        }
    }
    native
}

fn send_panels(
    service: &ni_service::ServiceSession,
    pixels: &[u8],
) -> Result<(), String> {
    if pixels.len() != FRAME_BYTES {
        return Err(format!("Incorrect frame length: {}", pixels.len()));
    }
    for display in 0..2 {
        let native = panel_native(pixels, display);
        let commands = encode_ni_color_rle(display as u8, 0, 0, 480, 272, &native);
        service.send_display(display as u8, 480, 272, &commands)
            .map_err(|e| format!("NI display {display}: {e}"))?;
    }
    Ok(())
}

pub fn run() -> Result<(), Box<dyn Error>> {
    eprintln!("Windows backend: HID MI_02 + NI hardware service; no WinUSB/Zadig");
    let hid = open_s61()?;
    eprintln!("S61 MK2 HID control/Light Guide interface opened successfully");

    // The NI service is responsible for bulk display MI_03 on an official
    // Windows driver installation. It must be installed and running.
    let service = ni_service::connect_with_retry(PID, None, Duration::from_secs(5))
        .map_err(|e| format!(
            "S61 HID works, but NI screen registration failed: {e}. \
             If NIHostIntegrationAgent and NIHardwareService are running, \
             this is a protocol or client-registration issue, not missing USB drivers. \
             Try --ni-role kontrol or --ni-role maschine for more targeted diagnostics."
        ))?;

    // Decouple screen encoding and blocking NI service IPC from key presses.
    let (screen_tx, screen_rx) = sync_channel::<Vec<u8>>(1);
    let screen_thread = std::thread::Builder::new()
        .name("s61-ni-screens".into())
        .spawn(move || {
            for frame in screen_rx {
                if let Err(e) = send_panels(&service, &frame) {
                    emit(json!({"kind": "error", "message": e}));
                    break;
                }
            }
        })?;
    let commands = receive_commands();
    let mut state = ButtonState::default();
    emit(json!({"kind":"ready", "device":"Komplete Kontrol S61 MK2", "backend":"hid+ni-service"}));

    let mut input = [0u8; 128];
    loop {
        match hid.read_timeout(&mut input, 5) {
            Ok(n) if n != 0 => state.receive(&input[..n]),
            Ok(_) => {},
            Err(err) => {
                emit(json!({"kind":"error", "message": format!("S61 HID read error: {err}")}));
                break;
            }
        }
        match commands.try_recv() {
            Ok(Command::Lights(colors)) => {
                if let Err(err) = hid.write(&led_frame(&colors)) {
                    emit(json!({"kind":"error", "message": format!("S61 HID LED write error: {err}")}));
                    break;
                }
            }
            Ok(Command::Frame(pixels)) => {
                match screen_tx.try_send(pixels) {
                    Ok(()) | Err(TrySendError::Full(_)) => {}, // Keep latency low.
                    Err(TrySendError::Disconnected(_)) => break,
                }
            }
            Ok(Command::Quit) | Err(std::sync::mpsc::TryRecvError::Disconnected) => break,
            Err(std::sync::mpsc::TryRecvError::Empty) => {},
        }
    }

    // Stop all Light Guide colors before closing the HID interface.
    let _ = hid.write(&led_frame(&[0u8; 61]));
    drop(screen_tx);
    let _ = screen_thread.join();
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn converts_native_rgb565_and_splits_panels() {
        let mut frame = vec![0u8; FRAME_BYTES];
        frame[0] = 255;
        frame[3] = 255;
        frame[480 * 4 + 1] = 255;
        frame[480 * 4 + 3] = 255;
        let left = panel_native(&frame, 0);
        let right = panel_native(&frame, 1);
        assert_eq!(&left[..2], &[0xf8, 0x00]);
        assert_eq!(&right[..2], &[0x07, 0xe0]);
    }

    #[test]
    fn relative_encoders_wrap() {
        assert_eq!(delta_wrap(15, 0, 16), 1);
        assert_eq!(delta_wrap(0, 15, 16), -1);
        assert_eq!(delta_wrap(254, 1, 256), 3);
    }
}
