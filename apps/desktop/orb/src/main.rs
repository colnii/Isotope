#![cfg_attr(windows, windows_subsystem = "windows")]

use native_floating_orb_win32::{run_native_orb, NativeOrbEvent};

fn main() {
    if let Err(error) = run_native_orb(handle_native_orb_event) {
        eprintln!("{error}");
    }
}

fn handle_native_orb_event(event: NativeOrbEvent) {
    match event {
        NativeOrbEvent::OpenMiniWindow => show_standalone_open_mini_message(),
    }
}

#[cfg(windows)]
fn show_standalone_open_mini_message() {
    use windows::{
        core::w,
        Win32::UI::WindowsAndMessaging::{MessageBoxW, MB_ICONINFORMATION, MB_OK},
    };

    unsafe {
        let _ = MessageBoxW(
            None,
            w!("Left click received. In the desktop app this opens MiniWindow."),
            w!("Isotope Orb"),
            MB_OK | MB_ICONINFORMATION,
        );
    }
}

#[cfg(not(windows))]
fn show_standalone_open_mini_message() {}
