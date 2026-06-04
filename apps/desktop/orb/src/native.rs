use crate::NativeOrbEvent;

#[cfg(not(windows))]
pub fn run_native_orb<H>(_handler: H) -> Result<(), String>
where
    H: Fn(NativeOrbEvent) + Send + 'static,
{
    Err("native floating orb is only available on Windows".to_string())
}

#[cfg(windows)]
pub fn run_native_orb<H>(handler: H) -> Result<(), String>
where
    H: Fn(NativeOrbEvent) + Send + 'static,
{
    win32::run(Box::new(handler))
}

#[cfg(windows)]
mod win32 {
    use std::{mem::size_of, ptr::copy_nonoverlapping, sync::Mutex};

    use crate::{
        dispatch_left_click,
        geometry::point_in_circle,
        interaction::moved_far_enough_to_drag,
        render::{orb_bitmap_to_bgra_bytes, render_default_orb_bitmap, ORB_BITMAP_SIZE},
        NativeOrbEventHandler,
    };
    use windows::{
        core::w,
        Win32::{
            Foundation::{COLORREF, HINSTANCE, HWND, LPARAM, LRESULT, POINT, RECT, SIZE, WPARAM},
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
                Input::KeyboardAndMouse::{ReleaseCapture, SetCapture},
                WindowsAndMessaging::{
                    CreateWindowExW, DefWindowProcW, DestroyWindow, DispatchMessageW, GetCursorPos,
                    GetMessageW, GetWindowRect, LoadCursorW, PostQuitMessage, RegisterClassW,
                    SetWindowPos, ShowWindow, TranslateMessage, UpdateLayeredWindow, CS_HREDRAW,
                    CS_VREDRAW, HTCLIENT, HTNOWHERE, IDC_ARROW, MSG, SWP_NOACTIVATE, SWP_NOSIZE,
                    SWP_NOZORDER, SW_SHOWNOACTIVATE, ULW_ALPHA, WINDOW_EX_STYLE, WM_DESTROY,
                    WM_ERASEBKGND, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_MOUSEMOVE, WM_NCHITTEST,
                    WM_NCRBUTTONDOWN, WM_NCRBUTTONUP, WM_RBUTTONDOWN, WM_RBUTTONUP, WNDCLASSW,
                    WS_EX_LAYERED, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TOPMOST, WS_POPUP,
                },
            },
        },
    };

    static DRAG_STATE: Mutex<Option<DragState>> = Mutex::new(None);
    static EVENT_HANDLER: Mutex<Option<Box<NativeOrbEventHandler>>> = Mutex::new(None);

    const ORB_WINDOW_SIZE: i32 = ORB_BITMAP_SIZE as i32;
    const START_X: i32 = 240;
    const START_Y: i32 = 240;

    #[derive(Clone, Copy)]
    struct DragState {
        start_cursor: POINT,
        start_window: RECT,
        dragging: bool,
    }

    pub fn run(handler: Box<NativeOrbEventHandler>) -> Result<(), String> {
        install_event_handler(handler)?;
        let result = run_message_window();
        clear_event_handler();
        result
    }

    fn install_event_handler(handler: Box<NativeOrbEventHandler>) -> Result<(), String> {
        let mut guard = EVENT_HANDLER
            .lock()
            .map_err(|_| "native orb event handler mutex poisoned".to_string())?;
        if guard.is_some() {
            return Err("native orb is already running".to_string());
        }
        *guard = Some(handler);
        Ok(())
    }

    fn clear_event_handler() {
        if let Ok(mut guard) = EVENT_HANDLER.lock() {
            *guard = None;
        }
    }

    fn emit_left_click_event() {
        if let Ok(guard) = EVENT_HANDLER.lock() {
            if let Some(handler) = guard.as_ref() {
                dispatch_left_click(handler.as_ref());
            }
        }
    }

    fn run_message_window() -> Result<(), String> {
        unsafe {
            let _ = SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);

            let hmodule = GetModuleHandleW(None).map_err(|error| error.to_string())?;
            let instance = HINSTANCE(hmodule.0);
            let class_name = w!("IsotopeNativeFloatingOrb");
            let cursor = LoadCursorW(None, IDC_ARROW).map_err(|error| error.to_string())?;
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
                w!("Isotope Native Orb"),
                WS_POPUP,
                START_X,
                START_Y,
                ORB_WINDOW_SIZE,
                ORB_WINDOW_SIZE,
                None,
                None,
                Some(instance),
                None,
            )
            .map_err(|error| error.to_string())?;

            apply_circle_region(hwnd).map_err(|error| error.to_string())?;
            update_layered_orb(hwnd).map_err(|error| error.to_string())?;
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
                WM_LBUTTONDOWN => handle_left_button_down(hwnd),
                WM_MOUSEMOVE => handle_mouse_move(hwnd),
                WM_LBUTTONUP => handle_left_button_up(hwnd),
                WM_NCRBUTTONDOWN | WM_NCRBUTTONUP | WM_RBUTTONDOWN | WM_RBUTTONUP => {
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
            return LRESULT(HTCLIENT as isize);
        }

        LRESULT(HTNOWHERE as isize)
    }

    unsafe fn handle_left_button_down(hwnd: HWND) -> LRESULT {
        let mut cursor = POINT::default();
        if GetCursorPos(&mut cursor).is_err() {
            return LRESULT(0);
        }

        let mut window_rect = RECT::default();
        if GetWindowRect(hwnd, &mut window_rect).is_err() {
            return LRESULT(0);
        }

        let _ = SetCapture(hwnd);
        *DRAG_STATE.lock().expect("drag state mutex poisoned") = Some(DragState {
            start_cursor: cursor,
            start_window: window_rect,
            dragging: false,
        });

        LRESULT(0)
    }

    unsafe fn handle_mouse_move(hwnd: HWND) -> LRESULT {
        let mut guard = DRAG_STATE.lock().expect("drag state mutex poisoned");
        let Some(state) = guard.as_mut() else {
            return LRESULT(0);
        };

        let mut cursor = POINT::default();
        if GetCursorPos(&mut cursor).is_err() {
            return LRESULT(0);
        }

        let dx = cursor.x - state.start_cursor.x;
        let dy = cursor.y - state.start_cursor.y;
        if !state.dragging
            && !moved_far_enough_to_drag(
                state.start_cursor.x,
                state.start_cursor.y,
                cursor.x,
                cursor.y,
            )
        {
            return LRESULT(0);
        }

        state.dragging = true;
        let _ = SetWindowPos(
            hwnd,
            None,
            state.start_window.left + dx,
            state.start_window.top + dy,
            0,
            0,
            SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
        );

        LRESULT(0)
    }

    unsafe fn handle_left_button_up(_hwnd: HWND) -> LRESULT {
        let _ = ReleaseCapture();
        let state = DRAG_STATE.lock().expect("drag state mutex poisoned").take();
        if let Some(state) = state {
            let mut cursor = POINT::default();
            let still_click = GetCursorPos(&mut cursor).is_ok()
                && !moved_far_enough_to_drag(
                    state.start_cursor.x,
                    state.start_cursor.y,
                    cursor.x,
                    cursor.y,
                );
            if !state.dragging || still_click {
                emit_left_click_event();
            }
        }

        LRESULT(0)
    }

    fn low_word_signed(lparam: LPARAM) -> i32 {
        (lparam.0 & 0xffff) as i16 as i32
    }

    fn high_word_signed(lparam: LPARAM) -> i32 {
        ((lparam.0 >> 16) & 0xffff) as i16 as i32
    }
}
