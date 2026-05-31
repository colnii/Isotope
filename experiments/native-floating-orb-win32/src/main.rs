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
    use std::{mem::size_of, ptr::copy_nonoverlapping};

    use native_floating_orb_win32::{
        geometry::point_in_circle,
        render::{orb_bitmap_to_bgra_bytes, render_default_orb_bitmap, ORB_BITMAP_SIZE},
    };
    use windows::{
        core::w,
        Win32::{
            Foundation::{COLORREF, HINSTANCE, HWND, LPARAM, LRESULT, POINT, SIZE, WPARAM},
            Graphics::Gdi::{
                CreateCompatibleDC, CreateDIBSection, CreateEllipticRgn, DeleteDC, DeleteObject,
                GetDC, ReleaseDC, ScreenToClient, SelectObject, SetWindowRgn, AC_SRC_ALPHA,
                AC_SRC_OVER, BITMAPINFO, BITMAPINFOHEADER, BI_RGB, BLENDFUNCTION, DIB_RGB_COLORS,
            },
            System::LibraryLoader::GetModuleHandleW,
            UI::{
                HiDpi::{
                    SetProcessDpiAwarenessContext, DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2,
                },
                WindowsAndMessaging::{
                    CreateWindowExW, DefWindowProcW, DestroyWindow, DispatchMessageW, GetMessageW,
                    LoadCursorW, PostQuitMessage, RegisterClassW, ShowWindow, TranslateMessage,
                    UpdateLayeredWindow, CS_HREDRAW, CS_VREDRAW, HTCAPTION, HTNOWHERE, IDC_ARROW,
                    MSG, SW_SHOWNOACTIVATE, ULW_ALPHA, WINDOW_EX_STYLE, WM_DESTROY, WM_ERASEBKGND,
                    WM_NCHITTEST, WM_RBUTTONUP, WNDCLASSW, WS_EX_LAYERED, WS_EX_NOACTIVATE,
                    WS_EX_TOOLWINDOW, WS_EX_TOPMOST, WS_POPUP,
                },
            },
        },
    };

    const ORB_WINDOW_SIZE: i32 = ORB_BITMAP_SIZE as i32;
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
                WINDOW_EX_STYLE(
                    WS_EX_TOPMOST.0 | WS_EX_TOOLWINDOW.0 | WS_EX_LAYERED.0 | WS_EX_NOACTIVATE.0,
                ),
                class_name,
                w!("Native Orb Spike"),
                WS_POPUP,
                START_X,
                START_Y,
                ORB_WINDOW_SIZE,
                ORB_WINDOW_SIZE,
                None,
                None,
                Some(instance),
                None,
            )?;

            apply_circle_region(hwnd)?;
            update_layered_orb(hwnd)?;
            let _ = ShowWindow(hwnd, SW_SHOWNOACTIVATE);
            run_message_loop();
        }

        Ok(())
    }

    unsafe fn apply_circle_region(hwnd: HWND) -> windows::core::Result<()> {
        let region = CreateEllipticRgn(0, 0, ORB_WINDOW_SIZE, ORB_WINDOW_SIZE);
        if region.is_invalid() {
            return Err(windows::core::Error::from_win32());
        }

        if SetWindowRgn(hwnd, Some(region), true) == 0 {
            let _ = DeleteObject(region.into());
            return Err(windows::core::Error::from_win32());
        }

        Ok(())
    }

    unsafe fn update_layered_orb(hwnd: HWND) -> windows::core::Result<()> {
        let bitmap = render_default_orb_bitmap();
        let bytes = orb_bitmap_to_bgra_bytes(&bitmap);

        let screen_dc = GetDC(None);
        if screen_dc.is_invalid() {
            return Err(windows::core::Error::from_win32());
        }

        let memory_dc = CreateCompatibleDC(Some(screen_dc));
        if memory_dc.is_invalid() {
            let _ = ReleaseDC(None, screen_dc);
            return Err(windows::core::Error::from_win32());
        }

        let mut bitmap_info = BITMAPINFO::default();
        bitmap_info.bmiHeader = BITMAPINFOHEADER {
            biSize: size_of::<BITMAPINFOHEADER>() as u32,
            biWidth: ORB_WINDOW_SIZE,
            biHeight: -ORB_WINDOW_SIZE,
            biPlanes: 1,
            biBitCount: 32,
            biCompression: BI_RGB.0,
            ..Default::default()
        };

        let mut bits = std::ptr::null_mut();
        let hbitmap = match CreateDIBSection(
            Some(screen_dc),
            &bitmap_info,
            DIB_RGB_COLORS,
            &mut bits,
            None,
            0,
        ) {
            Ok(hbitmap) => hbitmap,
            Err(error) => {
                let _ = DeleteDC(memory_dc);
                let _ = ReleaseDC(None, screen_dc);
                return Err(error);
            }
        };

        copy_nonoverlapping(bytes.as_ptr(), bits.cast::<u8>(), bytes.len());
        let previous_object = SelectObject(memory_dc, hbitmap.into());

        let source = POINT { x: 0, y: 0 };
        let destination = POINT {
            x: START_X,
            y: START_Y,
        };
        let size = SIZE {
            cx: ORB_WINDOW_SIZE,
            cy: ORB_WINDOW_SIZE,
        };
        let blend = BLENDFUNCTION {
            BlendOp: AC_SRC_OVER as u8,
            BlendFlags: 0,
            SourceConstantAlpha: 255,
            AlphaFormat: AC_SRC_ALPHA as u8,
        };

        let update_result = UpdateLayeredWindow(
            hwnd,
            Some(screen_dc),
            Some(&destination),
            Some(&size),
            Some(memory_dc),
            Some(&source),
            COLORREF(0),
            Some(&blend),
            ULW_ALPHA,
        );

        let _ = SelectObject(memory_dc, previous_object);
        let _ = DeleteObject(hbitmap.into());
        let _ = DeleteDC(memory_dc);
        let _ = ReleaseDC(None, screen_dc);

        update_result
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
        if point_in_circle(point.x, point.y, ORB_WINDOW_SIZE, ORB_WINDOW_SIZE) {
            return LRESULT(HTCAPTION as isize);
        }

        LRESULT(HTNOWHERE as isize)
    }

    fn low_word_signed(lparam: LPARAM) -> i32 {
        (lparam.0 & 0xffff) as i16 as i32
    }

    fn high_word_signed(lparam: LPARAM) -> i32 {
        ((lparam.0 >> 16) & 0xffff) as i16 as i32
    }
}
