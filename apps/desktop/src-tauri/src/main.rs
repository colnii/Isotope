mod native_orb;
mod window_commands;

use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};

const SKIP_GLOBAL_SHORTCUTS_ENV: &str = "ISOTOPE_DESKTOP_SKIP_GLOBAL_SHORTCUTS";

fn global_shortcuts_enabled(skip_value: Option<&str>) -> bool {
    !matches!(
        skip_value.map(|value| value.trim().to_ascii_lowercase()),
        Some(value) if matches!(value.as_str(), "1" | "true" | "yes" | "on")
    )
}

fn register_global_shortcuts(app: &tauri::App) {
    let skip_value = std::env::var(SKIP_GLOBAL_SHORTCUTS_ENV).ok();
    if !global_shortcuts_enabled(skip_value.as_deref()) {
        return;
    }

    if let Err(error) =
        app.global_shortcut()
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

fn open_startup_windows(app: &tauri::App) {
    native_orb::spawn_startup_orb(app.handle().clone());
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            window_commands::open_window,
            window_commands::hide_window,
            window_commands::open_path
        ])
        .setup(|app| {
            register_global_shortcuts(app);
            open_startup_windows(app);
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("failed to run Isotope desktop");
}

#[cfg(test)]
mod tests {
    use super::global_shortcuts_enabled;

    #[test]
    fn global_shortcuts_are_enabled_by_default() {
        assert!(global_shortcuts_enabled(None));
    }

    #[test]
    fn global_shortcuts_can_be_disabled_for_automation() {
        assert!(!global_shortcuts_enabled(Some("1")));
        assert!(!global_shortcuts_enabled(Some("true")));
        assert!(!global_shortcuts_enabled(Some("YES")));
        assert!(!global_shortcuts_enabled(Some(" on ")));
    }

    #[test]
    fn unrelated_values_keep_global_shortcuts_enabled() {
        assert!(global_shortcuts_enabled(Some("0")));
        assert!(global_shortcuts_enabled(Some("false")));
        assert!(global_shortcuts_enabled(Some("")));
    }
}
