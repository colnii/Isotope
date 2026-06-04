use serde::Serialize;
use std::process::Command;
use tauri::{AppHandle, Manager, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

#[derive(Clone, Copy)]
enum DesktopWindowLabel {
    Mini,
    Main,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct WindowCommandResult {
    label: String,
    visible: bool,
    focused: bool,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct OpenPathResult {
    status: String,
    path: String,
}

impl DesktopWindowLabel {
    fn parse(label: &str) -> Result<Self, String> {
        match label {
            "mini" => Ok(Self::Mini),
            "main" => Ok(Self::Main),
            _ => Err(format!("unknown desktop window label: {label}")),
        }
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::Mini => "mini",
            Self::Main => "main",
        }
    }

    fn title(self) -> &'static str {
        match self {
            Self::Mini => "Isotope Mini",
            Self::Main => "Isotope",
        }
    }

    fn size(self) -> (f64, f64) {
        match self {
            Self::Mini => (380.0, 520.0),
            Self::Main => (1180.0, 760.0),
        }
    }

    fn always_on_top(self) -> bool {
        matches!(self, Self::Mini)
    }

    fn decorations(self) -> bool {
        matches!(self, Self::Main)
    }

    fn resizable(self) -> bool {
        true
    }
}

fn window_url(label: DesktopWindowLabel) -> WebviewUrl {
    WebviewUrl::App(format!("/?window={}", label.as_str()).into())
}

fn apply_focus(window: &WebviewWindow, focus: bool) -> Result<(), String> {
    if focus {
        window.set_focus().map_err(|error| error.to_string())?;
    }
    Ok(())
}

fn command_result(label: DesktopWindowLabel, visible: bool, focused: bool) -> WindowCommandResult {
    WindowCommandResult {
        label: label.as_str().to_string(),
        visible,
        focused,
    }
}

fn build_window(
    app: &AppHandle,
    label: DesktopWindowLabel,
    focus: bool,
) -> Result<WebviewWindow, String> {
    let (width, height) = label.size();

    let window = WebviewWindowBuilder::new(app, label.as_str(), window_url(label))
        .title(label.title())
        .inner_size(width, height)
        .resizable(label.resizable())
        .decorations(label.decorations())
        .transparent(!label.decorations())
        .always_on_top(label.always_on_top())
        .focused(focus)
        .visible(true)
        .build()
        .map_err(|error| error.to_string())?;

    Ok(window)
}

fn show_or_create_window(
    app: &AppHandle,
    label: DesktopWindowLabel,
    focus: bool,
) -> Result<WindowCommandResult, String> {
    let window = match app.get_webview_window(label.as_str()) {
        Some(window) => {
            window.show().map_err(|error| error.to_string())?;
            apply_focus(&window, focus)?;
            window
        }
        None => build_window(app, label, focus)?,
    };

    if focus {
        apply_focus(&window, true)?;
    }

    Ok(command_result(label, true, focus))
}

#[tauri::command]
pub async fn open_window(
    app: AppHandle,
    label: String,
    focus: Option<bool>,
) -> Result<WindowCommandResult, String> {
    let parsed = DesktopWindowLabel::parse(&label)?;
    show_or_create_window(&app, parsed, focus.unwrap_or(false))
}

#[tauri::command]
pub fn hide_window(app: AppHandle, label: String) -> Result<WindowCommandResult, String> {
    let parsed = DesktopWindowLabel::parse(&label)?;
    if let Some(window) = app.get_webview_window(parsed.as_str()) {
        window.hide().map_err(|error| error.to_string())?;
    }

    Ok(command_result(parsed, false, false))
}

#[tauri::command]
pub fn open_path(path: String) -> Result<OpenPathResult, String> {
    if path.trim().is_empty() {
        return Err("path must not be empty".to_string());
    }
    let clean_path = path.trim().to_string();
    system_open_path(&clean_path)?;
    Ok(OpenPathResult {
        status: "ok".to_string(),
        path: clean_path,
    })
}

pub async fn open_mini_window(app: AppHandle) -> Result<WindowCommandResult, String> {
    show_or_create_window(&app, DesktopWindowLabel::Mini, true)
}

pub async fn open_mini_from_shortcut(app: AppHandle) -> Result<WindowCommandResult, String> {
    open_mini_window(app).await
}

#[cfg(target_os = "windows")]
fn system_open_path(path: &str) -> Result<(), String> {
    Command::new("explorer")
        .arg(path)
        .spawn()
        .map_err(|error| error.to_string())?;
    Ok(())
}

#[cfg(target_os = "macos")]
fn system_open_path(path: &str) -> Result<(), String> {
    Command::new("open")
        .arg(path)
        .spawn()
        .map_err(|error| error.to_string())?;
    Ok(())
}

#[cfg(all(not(target_os = "windows"), not(target_os = "macos")))]
fn system_open_path(path: &str) -> Result<(), String> {
    Command::new("xdg-open")
        .arg(path)
        .spawn()
        .map_err(|error| error.to_string())?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::DesktopWindowLabel;

    #[test]
    fn parses_known_window_labels() {
        assert_eq!(DesktopWindowLabel::parse("mini").unwrap().as_str(), "mini");
        assert_eq!(DesktopWindowLabel::parse("main").unwrap().as_str(), "main");
    }

    #[test]
    fn rejects_unknown_window_labels() {
        assert!(DesktopWindowLabel::parse("settings").is_err());
        assert!(DesktopWindowLabel::parse("orb").is_err());
    }

    #[test]
    fn open_path_rejects_empty_path() {
        assert!(super::open_path("  ".to_string()).is_err());
    }

    #[test]
    fn mini_window_is_the_only_always_on_top_tauri_window() {
        assert!(DesktopWindowLabel::Mini.always_on_top());
        assert!(!DesktopWindowLabel::Main.always_on_top());
    }
}
