# Isotope Desktop

Windows-first desktop frontend for Isotope.

## Commands

```bash
npm install
npm run dev:full
npm run observe:desktop -- --plan
npm run check
npm run test
npm run test:tauri-cdp
npm run test:tauri-screen
npm run build
npm run tauri dev
```

`npm run dev:full` writes `VITE_ISOTOPE_DESKTOP_API_BASE` to `.env.local` when
the key is missing, starts the local Supervisor backend, then starts the Vite
desktop frontend.

`npm run observe:desktop` is the agent-facing entrypoint for desktop UI
diagnosis. It defaults to the CDP smoke path, accepts `--mode screen` for
screen artifact verification, and `--plan` prints the commands and setup as
JSON for a new agent session.

`npm run test:tauri-cdp` drives a running Windows Tauri WebView2 window through
the Chrome DevTools Protocol. Start the desktop app with
`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS="--remote-debugging-port=9223 --remote-allow-origins=*"`
and keep the local backend/frontend running first. Set
`ISOTOPE_DESKTOP_SKIP_GLOBAL_SHORTCUTS=1` when another local Tauri instance might
already own the global shortcut. Override
`ISOTOPE_TAURI_CDP_URL`, `ISOTOPE_TAURI_CDP_QUESTION`, and
`ISOTOPE_TAURI_CDP_EXPECTED` when a smoke fixture uses different values.
Use `npm run tauri -- dev --config '{"build":{"devUrl":"http://127.0.0.1:5174","beforeDevCommand":""}}'`
when the default Vite port is already occupied and a separate frontend is
running on another port.
When the checkout lives under WSL, run the script with Windows Node directly
instead of `npm.cmd` from a UNC current directory:

```powershell
node "\\wsl.localhost\Ubuntu\home\lumber\Github\isotope\apps\desktop\scripts\tauri-cdp-smoke.mjs"
```

`npm run test:tauri-screen` uses the same WebView2 CDP setup, then drives the
desktop chat through `screen.observe`, opens the original screenshot modal, and
verifies the PNG data URL, download action, and `open_path` folder action. It
expects a backend fixture that can complete `screen.observe` and return a real
screen screenshot artifact. Under WSL, run it with Windows Node directly:

```powershell
node "\\wsl.localhost\Ubuntu\home\lumber\Github\isotope\apps\desktop\scripts\tauri-screen-artifact-smoke.mjs"
```

## MVP Boundaries

- Tauri/Rust owns windows, shortcuts, local settings, lifecycle.
- Python/Supervisor owns snapshot, events, approval, artifact refs.
- UI components call `isotopeClient`; do not scatter raw `fetch()` / `invoke()`.
- Mock data must use `DataSourceInfo.kind = "mock"` or `"replay_mock"`.
