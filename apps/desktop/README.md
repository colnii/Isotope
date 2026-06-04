# Isotope Desktop

Windows-first desktop frontend for Isotope.

## Commands

```bash
npm install
npm run dev:full
npm run check
npm run test
npm run test:tauri-cdp
npm run build
npm run tauri dev
```

`npm run dev:full` writes `VITE_ISOTOPE_DESKTOP_API_BASE` to `.env.local` when
the key is missing, starts the local Supervisor backend, then starts the Vite
desktop frontend.

`npm run test:tauri-cdp` drives a running Windows Tauri WebView2 window through
the Chrome DevTools Protocol. Start the desktop app with
`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS="--remote-debugging-port=9223 --remote-allow-origins=*"`
and keep the local backend/frontend running first. Override
`ISOTOPE_TAURI_CDP_URL`, `ISOTOPE_TAURI_CDP_QUESTION`, and
`ISOTOPE_TAURI_CDP_EXPECTED` when a smoke fixture uses different values.
When the checkout lives under WSL, run the script with Windows Node directly
instead of `npm.cmd` from a UNC current directory:

```powershell
node "\\wsl.localhost\Ubuntu\home\lumber\Github\isotope\apps\desktop\scripts\tauri-cdp-smoke.mjs"
```

## MVP Boundaries

- Tauri/Rust owns windows, shortcuts, local settings, lifecycle.
- Python/Supervisor owns snapshot, events, approval, artifact refs.
- UI components call `isotopeClient`; do not scatter raw `fetch()` / `invoke()`.
- Mock data must use `DataSourceInfo.kind = "mock"` or `"replay_mock"`.
