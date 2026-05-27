# Desktop Frontend Backend Gaps

Checkpoint date: 2026-05-28

This report records the backend and system contracts still missing after the
Task 3 through Task 8R desktop frontend slices. It is a handoff document for
backend / Tauri work. It does not change the frontend contract or implementation.

## Current Completed Capabilities

- `/desktop/snapshot` returns a real Supervisor desktop snapshot adapter output.
- The desktop frontend loads snapshot state through `createIsotopeClient(...)`
  and `createAppState(...)`.
- Floating Orb renders a snapshot-driven preview and keeps `source.kind` visible.
- MiniWindow renders a static thin shell from the current snapshot.
- MiniWindow submit is explicitly `mock`; the local preview is not counted as a
  real Supervisor interaction.
- MainWindow snapshot shell renders ActivityTree, selected activity, active goal,
  counts, and approval summary from the snapshot.
- EventStream static shell renders typed `IsotopeEvent` fixtures with
  `source.kind = replay_mock`.

## Current Not Completed Capabilities

- Real MiniWindow submit.
- Real desktop event replay or SSE.
- Tauri orb / MiniWindow / MainWindow as independent desktop windows.
- Window positioning, focus behavior, global shortcuts, and saved window state.
- Windows overlay spike for topmost, transparency, borderless fullscreen,
  multi-display, DPI, and focus behavior.
- Artifact and approval deep contracts beyond low-sensitive summaries.

## Gap 1: MiniWindow Real Submit Path

Frontend needs:
- A real MiniWindow -> Supervisor submit path.
- A low-sensitive response preview suitable for the MiniWindow.
- A source-aware result that can be marked `real`, `mock`, or `disabled`.

Current backend mismatch:
- The current MiniWindow uses `submitMode = "mock"`.
- `buildMockSubmitPreview(...)` updates only local UI state.
- Mock submit preview does not satisfy the MVP real interaction requirement.

Proposed contract:
- Provide either:
  - `POST /desktop/supervisor/input`; or
  - a Tauri invoke bridge such as `submit_supervisor_input`.
- Minimum response shape:

```ts
type DesktopSubmitResult = {
  mode: "real";
  preview: string;
  activityRef?: ResourceRef;
  eventCursor?: string;
  source: DataSourceInfo;
};
```

Blocking level:
- Partial for the current snapshot-only MVP.
- Blocking for target MVP acceptance that requires a real MiniWindow ->
  Supervisor interaction.

Temporary mock boundary:
- Frontend may keep the current mock preview for UI development.
- Mock preview must stay visibly marked as mock and cannot be counted as a real
  Supervisor interaction.

## Gap 2: Desktop Event Replay And SSE

Frontend needs:
- Historical replay endpoint:
  `GET /desktop/events?cursor=<cursor>&limit=<limit>`.
- Real-time stream endpoint:
  `GET /desktop/events/stream?cursor=<cursor>`.
- Responses must use the final `IsotopeEvent` discriminated union.
- Event replay and stream must preserve `source.kind`.

Current backend mismatch:
- Current EventStream uses local `replay_mock` fixture events.
- No frontend code fetches `/desktop/events`.
- Existing bell / refresh `/events` is not a desktop agent event stream and must
  not be cast to `EventReplayResponse`.

Proposed contract:
- `GET /desktop/events?cursor=&limit=` returns:

```ts
type EventReplayResponse = {
  events: IsotopeEvent[];
  nextCursor?: string;
  hasMore: boolean;
};
```

- `GET /desktop/events/stream?cursor=` emits SSE events where:
  - SSE `id = event.eventCursor ?? event.id`;
  - `GET /desktop/events?cursor=` is exclusive after cursor;
  - first SSE connection uses query cursor;
  - EventSource reconnect uses `Last-Event-ID`;
  - if query cursor and `Last-Event-ID` both exist, service must not
    unconditionally prefer the initial query cursor.

Blocking level:
- Partial for static MVP explanation UI.
- Blocking for real-time EventStream acceptance.

Temporary mock boundary:
- `replay_mock` fixtures may be used for static UI only.
- `source.kind = replay_mock` must remain visible in EventStream items.
- No existing `/events` endpoint may be treated as desktop event replay without a
  backend contract change.

## Gap 3: Desktop API Base URL Discovery

Frontend needs:
- A reliable desktop API base URL for:
  - `GET /desktop/snapshot`;
  - future `GET /desktop/events`;
  - future `GET /desktop/events/stream`.

Current backend mismatch:
- Current frontend depends on `VITE_ISOTOPE_DESKTOP_API_BASE`.
- Tauri/Rust does not yet start, discover, or supervise the local Supervisor
  server.
- Without the configured base URL, the UI falls back to mock snapshot data.

Proposed contract:
- Tauri/Rust command such as:
  - `ensure_supervisor_server`; and/or
  - `get_desktop_api_base_url`.
- Minimum response shape:

```ts
type DesktopApiBaseUrlResult = {
  baseUrl: string;
  source: DataSourceInfo;
};
```

Blocking level:
- Blocking for packaged desktop MVP real snapshot acceptance when the env var is
  absent.
- Partial for browser dev shell work.

Temporary mock boundary:
- Browser/dev shell may use `VITE_ISOTOPE_DESKTOP_API_BASE`.
- If no base URL is configured, fallback mock must remain labeled `mock`, and
  real snapshot acceptance is not satisfied.

## Gap 4: Tauri Multi-Window Manager

Frontend needs:
- Floating Orb, MiniWindow, and MainWindow as independent Tauri windows.
- Create / show / hide / focus control for each surface.
- Persisted window position and size for Orb and MiniWindow.
- Focus behavior that can show windows without always stealing focus.

Current backend mismatch:
- Current implementation renders orb, MiniWindow, and MainWindow inside the
  browser/dev shell.
- There is no active Tauri window manager for `orb`, `mini`, or `main`.
- There is no implemented persisted MiniWindow position behavior.

Proposed contract:
- Tauri/Rust window manager commands:

```ts
type WindowLabel = "orb" | "mini" | "main";

type ShowWindowRequest = {
  label: WindowLabel;
  focus?: boolean;
};

type SavedWindowState = {
  label: WindowLabel;
  x: number;
  y: number;
  width?: number;
  height?: number;
  displayId?: string;
};
```

- Required operations:
  - create or show a window;
  - hide a window;
  - save window position;
  - load saved window state;
  - validate saved position and fall back near Orb when invalid.

Blocking level:
- Blocking for true desktop companion acceptance.
- Partial for browser/dev shell UI acceptance.

Temporary mock boundary:
- Current browser/dev shell may continue to render components in one page.
- It must not be described as validating Tauri multi-window runtime behavior.

## Gap 5: Windows Overlay Spike

Frontend needs:
- Windows-first proof for:
  - always-on-top;
  - transparent windows;
  - dragging;
  - borderless fullscreen visibility;
  - multi-display behavior;
  - DPI scaling;
  - non-focus or configurable focus behavior;
  - CPU/GPU overhead.

Current backend mismatch:
- Current work ran in the frontend/dev shell path.
- No Windows runtime overlay spike result has been recorded for this branch.
- No exclusive fullscreen or fallback behavior has been validated.

Proposed contract:
- A separate Windows overlay spike report with:
  - environment details;
  - tested apps / display setup;
  - pass/fail table;
  - known non-goals;
  - fallback behavior.

Blocking level:
- Non-blocking for current browser/dev shell.
- Blocking for Windows-first desktop acceptance.

Temporary mock boundary:
- UI screenshots or browser behavior cannot be used as proof for overlay,
  topmost, focus, transparency, or fullscreen behavior.

## Gap 6: Artifact And Approval Deep Contracts

Frontend needs:
- Low-sensitive artifact references and summaries.
- Approval summaries sufficient for compact UI.
- Optional deeper approval / artifact details through explicit user action.

Current backend mismatch:
- Approval summary is currently sufficient for compact display.
- Artifact display is still summary/ref only.
- There is no deep artifact viewer or approval-resolution UI in the desktop
  frontend.

Proposed contract:
- Artifact summary:

```ts
type ArtifactSummary = {
  id: string;
  title: string;
  artifactRef: ResourceRef;
  source: DataSourceInfo;
};
```

- Approval summary:

```ts
type ApprovalSummary = {
  id: string;
  title: string;
  status: "pending" | "resolved" | "expired";
  riskLevel?: "low" | "medium" | "high";
  source: DataSourceInfo;
};
```

- Future deep detail calls must avoid default full-content exposure and should
  return low-sensitive previews unless explicitly expanded.

Blocking level:
- Later for deep artifact viewer.
- Partial for approval UI until real approval resolution exists.

Temporary mock boundary:
- Current UI may show artifact counts and low-sensitive refs only.
- No mock artifact full text should be presented as real artifact content.

## MVP Checkpoint

Satisfied now:
- Real Supervisor desktop snapshot endpoint exists.
- Frontend snapshot wiring uses the desktop client and app state.
- Floating Orb, MiniWindow, and MainWindow shells can render from snapshot state.
- MainWindow ActivityTree can render parent/child activity structure.
- EventStream can render typed static `IsotopeEvent` fixtures with visible
  `replay_mock` source.

Static or mock only:
- MiniWindow submit is mock only.
- EventStream is static `replay_mock` only.
- MainWindow EventStream does not prove replay, SSE, or cursor behavior.
- Browser/dev shell surfaces do not prove Tauri multi-window behavior.

Not satisfied:
- Real MiniWindow -> Supervisor interaction.
- Real desktop event replay.
- Real desktop SSE.
- Tauri independent Orb / MiniWindow / MainWindow windows.
- Saved window position and focus behavior.
- Global shortcut behavior.
- Windows overlay spike acceptance.
- Deep artifact viewer and approval resolution UI.

## Next Recommended Slice

Do not start real SSE or Tauri window work in the same batch as this checkpoint.
The next implementation slice should choose one of:

- MiniWindow real submit contract spike; or
- desktop event replay without SSE; or
- Tauri multi-window manager spike.

Each slice should keep mock boundaries visible and update this gap report when a
gap changes status.
