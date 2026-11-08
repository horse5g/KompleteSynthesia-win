//! Encdr 0.9 hardware adapter for Windows KompleteSynthesia.
//! Python handles MIDI, palette, capture, controls, and settings.
//! Protocol: stdin 'L' + 61 colors, 'F' + 960x272 RGBA frame, 'Q'.
//! stdout emits one JSON event per line; stderr reports diagnostics.

use std::io::{self, Read};
use std::sync::mpsc::{self, Receiver};
use std::time::Duration;

use encdr::{Encdr, EncdrConfig, Event, LedValue};
use serde_json::json;

const FRAME_BYTES: usize = 960 * 272 * 4;

enum Command {
    Lights([u8; 61]),
    Frame(Vec<u8>),
    Quit,
}

fn receive_commands() -> Receiver<Command> {
    let (tx, rx) = mpsc::sync_channel(2);
    std::thread::spawn(move || {
        let mut input = io::stdin().lock();
        loop {
            let mut op = [0u8; 1];
            if input.read_exact(&mut op).is_err() {
                let _ = tx.send(Command::Quit);
                break;
            }
            let cmd = match op[0] {
                b'L' => {
                    let mut colors = [0u8; 61];
                    if input.read_exact(&mut colors).is_err() { break; }
                    Command::Lights(colors)
                }
                b'F' => {
                    let mut pixels = vec![0u8; FRAME_BYTES];
                    if input.read_exact(&mut pixels).is_err() { break; }
                    Command::Frame(pixels)
                }
                b'Q' => Command::Quit,
                other => {
                    eprintln!("Unknown command {other}; terminating");
                    break;
                }
            };
            let quitting = matches!(cmd, Command::Quit);
            if tx.send(cmd).is_err() || quitting { break; }
        }
    });
    rx
}

fn emit(event: serde_json::Value) {
    println!("{event}");
}

fn main() {
    if let Err(err) = run() {
        emit(json!({"kind": "error", "message": err.to_string()}));
        std::process::exit(1);
    }
}

#[cfg(windows)]
mod windows_hid_service;

#[cfg(windows)]
fn run() -> Result<(), Box<dyn std::error::Error>> {
    windows_hid_service::run()
}

#[cfg(not(windows))]
fn run() -> Result<(), Box<dyn std::error::Error>> {
    let mut driver = Encdr::new(EncdrConfig::default())?;
    let device = driver.scan()?.into_iter().find(|id| {
        driver.device_descriptor(*id).is_some_and(|desc| {
            desc.vendor_id.0 == 0x17cc && desc.product_id.0 == 0x1620
        })
    }).ok_or("S61 MK2 (17cc:1620) not detected by Encdr")?;
    let name = driver.device_descriptor(device).unwrap().name.clone();
    let events = driver.events().clone();
    let commands = receive_commands();

    // Emulate the macOS app's illuminated Play and display-control buttons.
    driver.set_led(device, "play", LedValue::Single(180));
    driver.set_led(device, "top_5", LedValue::Single(100));
    driver.set_led_strip(device, "light_guide", &[0u8; 61]);
    emit(json!({"kind": "ready", "device": name}));

    let mut disconnected = false;
    loop {
        while let Ok(event) = events.try_recv() {
            match event {
                Event::Button { name, pressed, .. } =>
                    emit(json!({"kind": "button", "name": name, "pressed": pressed})),
                Event::Encoder { name, delta, .. } =>
                    emit(json!({"kind": "encoder", "name": name, "delta": delta})),
                Event::EncoderFine { name, delta, .. } =>
                    emit(json!({"kind": "encoder", "name": name, "delta": delta})),
                Event::DeviceDisconnected { .. } => {
                    emit(json!({"kind": "error", "message": "S61 MK2 disconnected"}));
                    disconnected = true;
                    break;
                }
                _ => {}
            }
        }
        if disconnected {
            break;
        }
        match commands.try_recv() {
            Ok(Command::Lights(colors)) => driver.set_led_strip(device, "light_guide", &colors),
            Ok(Command::Frame(pixels)) => {
                if driver.screen_backlog(device) <= 1 {
                    driver.submit_dual_screen(device, "left", "right", &pixels);
                }
            }
            Ok(Command::Quit) | Err(mpsc::TryRecvError::Disconnected) => break,
            Err(mpsc::TryRecvError::Empty) => std::thread::sleep(Duration::from_millis(2)),
        }
    }
    driver.set_led_strip(device, "light_guide", &[0u8; 61]);
    driver.set_led(device, "play", LedValue::Off);
    driver.set_led(device, "top_5", LedValue::Off);
    Ok(())
}
