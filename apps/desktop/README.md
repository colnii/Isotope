# Isotope Desktop

Windows-first desktop frontend for Isotope.

## Commands

```bash
npm install
npm run dev:full
npm run check
npm run test
npm run build
npm run tauri dev
```

`npm run dev:full` writes `VITE_ISOTOPE_DESKTOP_API_BASE` to `.env.local` when
the key is missing, starts the local Supervisor backend, then starts the Vite
desktop frontend.

## MVP Boundaries

- Tauri/Rust owns windows, shortcuts, local settings, lifecycle.
- Python/Supervisor owns snapshot, events, approval, artifact refs.
- UI components call `isotopeClient`; do not scatter raw `fetch()` / `invoke()`.
- Mock data must use `DataSourceInfo.kind = "mock"` or `"replay_mock"`.
