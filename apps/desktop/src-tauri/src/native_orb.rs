#[cfg(windows)]
pub fn spawn_startup_orb(app: tauri::AppHandle) {
    let spawn_result = std::thread::Builder::new()
        .name("isotope-native-orb".to_string())
        .spawn(move || {
            if let Err(error) = native_floating_orb_win32::run_native_orb(move |event| {
                handle_native_orb_event(&app, event);
            }) {
                eprintln!("failed to run native orb: {error}");
            }
        });

    if let Err(error) = spawn_result {
        eprintln!("failed to spawn native orb thread: {error}");
    }
}

#[cfg(not(windows))]
pub fn spawn_startup_orb(_app: tauri::AppHandle) {}

#[cfg(windows)]
fn handle_native_orb_event(
    app: &tauri::AppHandle,
    event: native_floating_orb_win32::NativeOrbEvent,
) {
    match event {
        native_floating_orb_win32::NativeOrbEvent::OpenMiniWindow => {
            let app = app.clone();
            tauri::async_runtime::spawn(async move {
                if let Err(error) = crate::window_commands::open_mini_window(app).await {
                    eprintln!("failed to open mini window from native orb: {error}");
                }
            });
        }
    }
}
