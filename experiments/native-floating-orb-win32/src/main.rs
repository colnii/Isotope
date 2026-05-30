#![cfg_attr(windows, windows_subsystem = "windows")]

#[cfg(not(windows))]
fn main() {
    println!(
        "native-floating-orb-win32 is a Windows-only spike. Run it from PowerShell on Windows."
    );
}

#[cfg(windows)]
fn main() -> windows::core::Result<()> {
    win32::run()
}

#[cfg(windows)]
mod win32 {
    use native_floating_orb_win32::geometry::point_in_circle;
    use windows::{
        core::w,
        Win32::{
            Foundation::{COLORREF, HINSTANCE, HWND, LPARAM, LRESULT, POINT, RECT, WPARAM},
            Graphics::Gdi::{
                BeginPaint, CreateEllipticRgn, CreateSolidBrush, DeleteObject, Ellipse, EndPaint,
                FillRect, ScreenToClient, SelectObject, SetWindowRgn, HBRUSH, PAINTSTRUCT,
            },
            System::LibraryLoader::GetModuleHandleW,
            UI::{
                HiDpi::{
                    SetProcessDpiAwarenessContext, DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2,
                },
                WindowsAndMessaging::{
                    CreateWindowExW, DefWindowProcW, DestroyWindow, DispatchMessageW, GetMessageW,
                    LoadCursorW, PostQuitMessage, RegisterClassW, ShowWindow, TranslateMessage,
                    CS_HREDRAW, CS_VREDRAW, HTCAPTION, HTNOWHERE, IDC_ARROW, MSG, SW_SHOW,
                    WINDOW_EX_STYLE, WM_DESTROY, WM_ERASEBKGND, WM_NCHITTEST, WM_PAINT,
                    WM_RBUTTONUP, WNDCLASSW, WS_EX_TOOLWINDOW, WS_EX_TOPMOST, WS_POPUP,
                },
            },
        },
    };

    const ORB_SIZE: i32 = 96;
    const START_X: i32 = 240;
    const START_Y: i32 = 240;

    pub fn run() -> windows::core::Result<()> {
        unsafe {
            let _ = SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);

            let hmodule = GetModuleHandleW(None)?;
            let instance = HINSTANCE(hmodule.0);
            let class_name = w!("IsotopeNativeFloatingOrbSpike");
            let cursor = LoadCursorW(None, IDC_ARROW)?;
            let window_class = WNDCLASSW {
                hCursor: cursor,
                hInstance: instance,
                lpszClassName: class_name,
                lpfnWndProc: Some(window_proc),
                style: CS_HREDRAW | CS_VREDRAW,
                ..Default::default()
            };

            RegisterClassW(&window_class);

            let hwnd = CreateWindowExW(
                WINDOW_EX_STYLE(WS_EX_TOPMOST.0 | WS_EX_TOOLWINDOW.0),
                class_name,
                w!("Native Orb Spike"),
                WS_POPUP,
                START_X,
                START_Y,
                ORB_SIZE,
                ORB_SIZE,
                None,
                None,
                Some(instance),
                None,
            )?;

            apply_circle_region(hwnd)?;
            let _ = ShowWindow(hwnd, SW_SHOW);
            run_message_loop();
        }

        Ok(())
    }

    unsafe fn apply_circle_region(hwnd: HWND) -> windows::core::Result<()> {
        let region = CreateEllipticRgn(0, 0, ORB_SIZE, ORB_SIZE);
        if region.is_invalid() {
            return Err(windows::core::Error::from_win32());
        }

        if SetWindowRgn(hwnd, Some(region), true) == 0 {
            let _ = DeleteObject(region.into());
            return Err(windows::core::Error::from_win32());
        }

        Ok(())
    }

    unsafe fn run_message_loop() {
        let mut message = MSG::default();
        while GetMessageW(&mut message, None, 0, 0).as_bool() {
            let _ = TranslateMessage(&message);
            DispatchMessageW(&message);
        }
    }

    extern "system" fn window_proc(
        hwnd: HWND,
        message: u32,
        wparam: WPARAM,
        lparam: LPARAM,
    ) -> LRESULT {
        unsafe {
            match message {
                WM_ERASEBKGND => LRESULT(1),
                WM_PAINT => {
                    paint_orb(hwnd);
                    LRESULT(0)
                }
                WM_NCHITTEST => hit_test_orb(hwnd, lparam),
                WM_RBUTTONUP => {
                    let _ = DestroyWindow(hwnd);
                    LRESULT(0)
                }
                WM_DESTROY => {
                    PostQuitMessage(0);
                    LRESULT(0)
                }
                _ => DefWindowProcW(hwnd, message, wparam, lparam),
            }
        }
    }

    unsafe fn hit_test_orb(hwnd: HWND, lparam: LPARAM) -> LRESULT {
        let mut point = POINT {
            x: low_word_signed(lparam),
            y: high_word_signed(lparam),
        };

        let _ = ScreenToClient(hwnd, &mut point);
        if point_in_circle(point.x, point.y, ORB_SIZE, ORB_SIZE) {
            return LRESULT(HTCAPTION as isize);
        }

        LRESULT(HTNOWHERE as isize)
    }

    unsafe fn paint_orb(hwnd: HWND) {
        let mut paint = PAINTSTRUCT::default();
        let hdc = BeginPaint(hwnd, &mut paint);

        let orb_brush = CreateSolidBrush(rgb(20, 158, 146));
        let previous_brush = SelectObject(hdc, orb_brush.into());
        let _ = Ellipse(hdc, 0, 0, ORB_SIZE, ORB_SIZE);
        let _ = SelectObject(hdc, previous_brush);
        let _ = DeleteObject(orb_brush.into());

        let white_brush = CreateSolidBrush(rgb(255, 255, 255));
        fill_rect(hdc, white_brush, 45, 28, 51, 68);
        fill_rect(hdc, white_brush, 39, 28, 57, 34);
        fill_rect(hdc, white_brush, 39, 62, 57, 68);
        let _ = DeleteObject(white_brush.into());

        let _ = EndPaint(hwnd, &paint);
    }

    unsafe fn fill_rect(
        hdc: windows::Win32::Graphics::Gdi::HDC,
        brush: HBRUSH,
        left: i32,
        top: i32,
        right: i32,
        bottom: i32,
    ) {
        let rect = RECT {
            left,
            top,
            right,
            bottom,
        };
        let _ = FillRect(hdc, &rect, brush);
    }

    fn low_word_signed(lparam: LPARAM) -> i32 {
        (lparam.0 & 0xffff) as i16 as i32
    }

    fn high_word_signed(lparam: LPARAM) -> i32 {
        ((lparam.0 >> 16) & 0xffff) as i16 as i32
    }

    fn rgb(red: u8, green: u8, blue: u8) -> COLORREF {
        COLORREF((red as u32) | ((green as u32) << 8) | ((blue as u32) << 16))
    }
}
