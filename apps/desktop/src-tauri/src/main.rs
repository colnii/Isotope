mod window_commands;

use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};

fn register_global_shortcuts(app: &tauri::App) {
    if let Err(error) = app
        .global_shortcut()
        .on_shortcut("Alt+Shift+Space", |app, _shortcut, event| {
            if event.state == ShortcutState::Pressed {
                let app = app.clone();
                tauri::async_runtime::spawn(async move {
                    if let Err(error) = window_commands::open_mini_from_shortcut(app).await {
                        eprintln!("failed to open mini window from shortcut: {error}");
                    }
                });
            }
        })
    {
        eprintln!("failed to register Alt+Shift+Space shortcut: {error}");
    }
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            window_commands::open_window,
            window_commands::hide_window
        ])
        .setup(|app| {
            register_global_shortcuts(app);
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("failed to run Isotope desktop");
}
