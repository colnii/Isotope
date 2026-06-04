# Native Floating Orb Win32

This is the Windows-only native floating orb used by the desktop app. It does not
use Tauri, Svelte, or WebView for the orb window itself.

The orb creates an 88px topmost `WS_POPUP` layered window, clips it with
`SetWindowRgn`, loads `assets/orb-default.png` as the default
premultiplied-alpha BGRA orb for `UpdateLayeredWindow`, and treats the visible
circle as client-area input so left-click, right-click, and drag can be handled
separately.

To replace the default look, swap `assets/orb-default.png`. The app crops visible artwork, rescales it to the fixed 88px orb size, and masks the final output to the round window at startup.

The Tauri desktop process starts this crate through the library API:
`run_native_orb(handler)`. A left click dispatches `NativeOrbEvent::OpenMiniWindow`;
the desktop app handles that event by opening the Tauri MiniWindow.

Run the standalone binary from PowerShell on Windows:

```powershell
cd "\\wsl.localhost\Ubuntu\home\lumber\Github\isotope\apps\desktop\orb"
$env:CARGO_INCREMENTAL = "0"
$env:CARGO_TARGET_DIR = "E:\DevCache\cargo-target\isotope-native-orb"
cargo build
Start-Process "E:\DevCache\cargo-target\isotope-native-orb\debug\native-floating-orb-win32.exe"
```

In the standalone binary, left-click shows a local diagnostic message. In the
desktop app, left-click opens MiniWindow. Right-click closes the orb window.
