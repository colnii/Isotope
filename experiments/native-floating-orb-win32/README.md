# Native Floating Orb Win32 Spike

This is a Windows-only native desktop experiment. It does not use Tauri, Svelte, or WebView.

The spike creates an 88px topmost `WS_POPUP` layered window, clips it with `SetWindowRgn`, paints a supersampled premultiplied-alpha BGRA orb with `UpdateLayeredWindow`, and treats the visible circle as client-area input so left-click, right-click, and drag can be handled separately.

Run from PowerShell on Windows:

```powershell
cd "\\wsl.localhost\Ubuntu\home\lumber\Github\isotope\.worktrees\native-floating-orb-win32\experiments\native-floating-orb-win32"
$env:CARGO_INCREMENTAL = "0"
$env:CARGO_TARGET_DIR = "E:\DevCache\cargo-target\native-floating-orb-win32"
cargo build
Start-Process "E:\DevCache\cargo-target\native-floating-orb-win32\debug\native-floating-orb-win32.exe"
```

Left-click the orb to show the MiniWindow integration placeholder. Right-click the orb to close it.
