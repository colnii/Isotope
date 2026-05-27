# Isotope Desktop

Windows-first desktop frontend for Isotope.

## Commands

```bash
npm install
npm run check
npm run test
npm run build
npm run tauri dev
```

## MVP Boundaries

- Tauri/Rust owns windows, shortcuts, local settings, lifecycle.
- Python/Supervisor owns snapshot, events, approval, artifact refs.
- UI components call `isotopeClient`; do not scatter raw `fetch()` / `invoke()`.
- Mock data must use `DataSourceInfo.kind = "mock"` or `"replay_mock"`.
