use serde::Serialize;
use tauri::{AppHandle, Manager, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

#[derive(Clone, Copy)]
enum DesktopWindowLabel {
    Orb,
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

#[derive(Clone, Copy)]
struct WindowOpenRequest {
    label: DesktopWindowLabel,
    focus: bool,
}

impl DesktopWindowLabel {
    fn parse(label: &str) -> Result<Self, String> {
        match label {
            "orb" => Ok(Self::Orb),
            "mini" => Ok(Self::Mini),
            "main" => Ok(Self::Main),
            _ => Err(format!("unknown desktop window label: {label}")),
        }
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::Orb => "orb",
            Self::Mini => "mini",
            Self::Main => "main",
        }
    }

    fn title(self) -> &'static str {
        match self {
            Self::Orb => "Isotope Orb",
            Self::Mini => "Isotope Mini",
            Self::Main => "Isotope",
        }
    }

    fn size(self) -> (f64, f64) {
        match self {
            Self::Orb => (96.0, 112.0),
            Self::Mini => (380.0, 520.0),
            Self::Main => (1180.0, 760.0),
        }
    }

    fn always_on_top(self) -> bool {
        matches!(self, Self::Orb | Self::Mini)
    }

    fn decorations(self) -> bool {
        matches!(self, Self::Main)
    }

    fn resizable(self) -> bool {
        !matches!(self, Self::Orb)
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

    WebviewWindowBuilder::new(app, label.as_str(), window_url(label))
        .title(label.title())
        .inner_size(width, height)
        .resizable(label.resizable())
        .decorations(label.decorations())
        .transparent(!label.decorations())
        .always_on_top(label.always_on_top())
        .focused(focus)
        .visible(true)
        .build()
        .map_err(|error| error.to_string())
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

fn startup_window_request() -> WindowOpenRequest {
    WindowOpenRequest {
        label: DesktopWindowLabel::Orb,
        focus: false,
    }
}

pub fn open_startup_orb(app: &AppHandle) -> Result<WindowCommandResult, String> {
    let request = startup_window_request();
    show_or_create_window(app, request.label, request.focus)
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

pub async fn open_mini_from_shortcut(app: AppHandle) -> Result<WindowCommandResult, String> {
    show_or_create_window(&app, DesktopWindowLabel::Mini, true)
}

#[cfg(test)]
mod tests {
    use super::DesktopWindowLabel;

    #[test]
    fn parses_known_window_labels() {
        assert_eq!(DesktopWindowLabel::parse("orb").unwrap().as_str(), "orb");
        assert_eq!(DesktopWindowLabel::parse("mini").unwrap().as_str(), "mini");
        assert_eq!(DesktopWindowLabel::parse("main").unwrap().as_str(), "main");
    }

    #[test]
    fn rejects_unknown_window_labels() {
        assert!(DesktopWindowLabel::parse("settings").is_err());
    }

    #[test]
    fn startup_window_request_opens_orb_without_focus() {
        let request = super::startup_window_request();

        assert_eq!(request.label.as_str(), "orb");
        assert!(!request.focus);
    }
}
