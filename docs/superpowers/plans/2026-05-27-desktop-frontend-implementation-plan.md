# Desktop Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first Windows-first Isotope desktop frontend MVP: Floating Orb -> MiniWindow -> MainWindow plus a thin real Supervisor snapshot path and contract-first event/activity adapters.

**Architecture:** Add `apps/desktop/` as a Tauri 2 + Svelte 5 + TypeScript desktop app. Keep system window behavior in Tauri/Rust commands, keep UI state and rendering in Svelte, and route all backend/window access through typed `isotopeClient` adapters. Use real Supervisor snapshot data where available, and label derived/replay/mock data with `DataSourceInfo`.

**Tech Stack:** Tauri 2, Rust, Svelte 5, TypeScript, SvelteKit static SPA, Tailwind CSS, Vitest, Playwright or Webdriver smoke later, Python 3.13 pytest for backend adapter tests.

---

## Source Spec

Implement from:

- `docs/superpowers/specs/2026-05-27-desktop-frontend-design.md`

Non-negotiable constraints from the spec:

- Windows-first.
- MVP must show a real Supervisor snapshot.
- Worker session / active goal must have at least one real source.
- Mock replies do not count as real interaction.
- Event stream may be derived or replay_mock for MVP, but must use the final `IsotopeEvent` contract.
- Tauri/Rust owns windows, shortcuts, local settings, lifecycle, and optional Python bridge.
- Python/Supervisor owns snapshot, event replay, event stream, approval, artifact refs.
- UI components must use `isotopeClient`; do not scatter raw `fetch()` / `invoke()`.
- Backend mismatches must be recorded as Backend Gap entries.

## File Structure

Create:

- `apps/desktop/README.md`
  - Desktop app setup, dev commands, MVP boundaries, Windows-first notes.
- `apps/desktop/package.json`
  - Node scripts and frontend dependencies.
- `apps/desktop/package-lock.json`
  - Lockfile for reproducible installs.
- `apps/desktop/svelte.config.js`
  - SvelteKit static SPA config.
- `apps/desktop/vite.config.ts`
  - Vite + Svelte + Vitest config.
- `apps/desktop/tsconfig.json`
  - TypeScript config.
- `apps/desktop/tailwind.config.ts`
  - Tailwind config.
- `apps/desktop/postcss.config.cjs`
  - Tailwind/PostCSS wiring.
- `apps/desktop/src/app.css`
  - Global styles and CSS variables.
- `apps/desktop/src/app.html`
  - Required SvelteKit HTML shell for static SPA output.
- `apps/desktop/src/routes/+layout.svelte`
  - Svelte shell wrapper.
- `apps/desktop/src/routes/+page.svelte`
  - Dev route that can render orb, MiniWindow, and MainWindow states in browser mode.
- `apps/desktop/src/lib/contracts/isotope.ts`
  - Final frontend TypeScript contract from the spec.
- `apps/desktop/src/lib/contracts/isotope.test.ts`
  - Contract helper tests.
- `apps/desktop/src/lib/client/isotopeClient.ts`
  - Unified frontend client boundary.
- `apps/desktop/src/lib/client/windowClient.ts`
  - Tauri window/settings command adapter.
- `apps/desktop/src/lib/client/agentClient.ts`
  - Supervisor snapshot and MiniWindow submit adapter.
- `apps/desktop/src/lib/client/eventClient.ts`
  - Event replay/SSE adapter with cursor rules.
- `apps/desktop/src/lib/client/mockData.ts`
  - Typed mock/replay data for missing backend surfaces.
- `apps/desktop/src/lib/stores/appState.ts`
  - Svelte stores for snapshot, activities, selected node, window settings, and event stream.
- `apps/desktop/src/lib/components/orb/FloatingOrb.svelte`
  - Orb UI.
- `apps/desktop/src/lib/components/mini/MiniWindow.svelte`
  - MiniWindow UI.
- `apps/desktop/src/lib/components/main/MainWindow.svelte`
  - MainWindow shell.
- `apps/desktop/src/lib/components/activity/ActivityTree.svelte`
  - ActivityTree / AgentTree renderer.
- `apps/desktop/src/lib/components/activity/tree.ts`
  - Pure helper that projects `ActivityNode[]` into stable tree rows.
- `apps/desktop/src/lib/components/activity/tree.test.ts`
  - ActivityTree hierarchy and stable ordering tests.
- `apps/desktop/src/lib/components/events/EventStream.svelte`
  - Event stream renderer and auto-scroll behavior.
- `apps/desktop/src/lib/components/common/SourceBadge.svelte`
  - `real/mock/replay_mock/derived` source indicator.
- `apps/desktop/src/lib/components/common/CommandComposer.svelte`
  - Shared composer for MiniWindow and MainWindow.
- `apps/desktop/src/lib/components/common/QuickActionArea.svelte`
  - MiniWindow input lower action area.
- `apps/desktop/src/lib/components/common/RightDock.svelte`
  - EventStream + summary cards.
- `apps/desktop/src/lib/a11y/focus.ts`
  - Focus helpers.
- `apps/desktop/src/lib/a11y/focus.test.ts`
  - Focus helper tests.
- `apps/desktop/src-tauri/Cargo.toml`
  - Tauri Rust crate.
- `apps/desktop/src-tauri/build.rs`
  - Tauri build hook.
- `apps/desktop/src-tauri/tauri.conf.json`
  - Tauri windows config.
- `apps/desktop/src-tauri/capabilities/default.json`
  - Tauri v2 capability grants for main/orb/mini windows.
- `apps/desktop/src-tauri/src/main.rs`
  - Tauri command entry.
- `apps/desktop/src-tauri/src/window_state.rs`
  - Window settings persistence and validation.
- `apps/desktop/src-tauri/src/window_commands.rs`
  - Tauri commands for orb/MiniWindow/MainWindow behavior.
- `apps/desktop/src-tauri/src/shortcuts.rs`
  - Global shortcut registration.
- `apps/desktop/src-tauri/src/window_state_tests.rs`
  - Rust tests for fallback position and settings validation.
- `src/isotope/features/supervisor/desktop_snapshot.py`
  - Python adapter from existing Supervisor state/dashboard data to desktop snapshot contract.
- `tests/integration/supervisor/test_supervisor_desktop_snapshot.py`
  - Python tests for real snapshot mapping and low-sensitive previews.
- `docs/superpowers/plans/backend-gaps/2026-05-27-desktop-frontend-backend-gaps.md`
  - Backend Gap report produced during implementation.

Modify:

- `src/isotope/features/supervisor/web.py`
  - Add a `GET /desktop/snapshot` endpoint that exposes the desktop snapshot contract.
- `docs/current/supervisor-capability-map.md`
  - Add a short pointer after MVP lands, not during scaffold-only tasks.
- `docs/current/status.md`
  - Add a current-state line only after a runnable desktop thin loop exists.

Do not modify in MVP:

- `AGENTS.md`
- `README.md`
- Existing Supervisor runner behavior, unless a later reviewed backend-gap task explicitly requires it.

## Implementation Tasks

### Task -1: Persist Reviewed Docs Before Worktree

**Files:**
- Stage: `docs/superpowers/specs/2026-05-27-desktop-frontend-design.md`
- Stage: `docs/superpowers/plans/2026-05-27-desktop-frontend-implementation-plan.md`

This task prevents a common multi-worktree failure: untracked docs do not appear
in a worktree created from `origin/main`.

- [ ] **Step 1: Confirm the reviewed docs are present**

Run:

```bash
git status --short --branch
test -f docs/superpowers/specs/2026-05-27-desktop-frontend-design.md
test -f docs/superpowers/plans/2026-05-27-desktop-frontend-implementation-plan.md
```

Expected:

```text
## <current branch>
?? docs/superpowers/plans/2026-05-27-desktop-frontend-implementation-plan.md
?? docs/superpowers/specs/2026-05-27-desktop-frontend-design.md
```

If either file is already tracked, `git status` may show it as modified instead
of untracked. That is acceptable; the key requirement is that both reviewed docs
exist before creating the implementation worktree.

- [ ] **Step 2: Stage only the reviewed docs**

Run:

```bash
git add docs/superpowers/specs/2026-05-27-desktop-frontend-design.md \
        docs/superpowers/plans/2026-05-27-desktop-frontend-implementation-plan.md
git diff --cached --check
git diff --cached --name-only
```

Expected:

```text
docs/superpowers/plans/2026-05-27-desktop-frontend-implementation-plan.md
docs/superpowers/specs/2026-05-27-desktop-frontend-design.md
```

- [ ] **Step 3: Commit the reviewed docs**

Run:

```bash
git commit -m "docs(desktop): add frontend design and implementation plan"
git rev-parse --short HEAD
```

Expected: commit succeeds. Save the printed commit hash in task notes.

- [ ] **Step 4: Do not start implementation from `origin/main`**

Record this invariant in task notes:

```text
Task 0 worktree must be created from the docs commit or its branch HEAD, not from origin/main.
```

### Task 0: Isolated Worktree And Toolchain Preflight

**Files:**
- Read: `pyproject.toml`
- Read: `docs/superpowers/specs/2026-05-27-desktop-frontend-design.md`
- Read: `docs/superpowers/plans/2026-05-27-desktop-frontend-implementation-plan.md`

- [ ] **Step 1: Create an isolated worktree**

Run:

```bash
git fetch origin --prune
git worktree add .worktrees/desktop-frontend -b feature/desktop-frontend HEAD
cd .worktrees/desktop-frontend
```

Expected:

```text
Preparing worktree (new branch 'feature/desktop-frontend')
HEAD is now at <docs commit from Task -1>
```

Verify the docs are visible in the new worktree:

```bash
test -f docs/superpowers/specs/2026-05-27-desktop-frontend-design.md
test -f docs/superpowers/plans/2026-05-27-desktop-frontend-implementation-plan.md
```

- [ ] **Step 2: Verify Python and repo state**

Run:

```bash
python3 --version
git status --short --branch
```

Expected:

```text
Python 3.13.x
## feature/desktop-frontend
```

- [ ] **Step 3: Verify Node, npm, Rust, and Tauri prerequisites**

Run:

```bash
node --version
npm --version
rustc --version
cargo --version
rustup show
```

Expected:

```text
node v20.x or newer
npm 10.x or newer
rustc 1.8x or newer
cargo 1.8x or newer
```

If any tool is missing, stop and record a Backend Gap-style environment note in
`docs/superpowers/plans/backend-gaps/2026-05-27-desktop-frontend-backend-gaps.md`.
Do not start scaffold work with missing desktop toolchain.

- [ ] **Step 4: Check Windows desktop prerequisites**

Run:

```bash
uname -a
```

If the output is Linux/WSL/macOS, record this environment note and continue only
with non-Windows build/check work:

```text
Windows overlay/window acceptance is pending. This environment can verify source build and tests only.
```

If the output is Windows or the task is running in PowerShell, run:

```powershell
where cl
reg query "HKLM\SOFTWARE\Microsoft\EdgeUpdate\Clients" /s /f "WebView2 Runtime"
```

Expected:

```text
cl.exe is available from Microsoft C++ Build Tools or Visual Studio Build Tools
WebView2 Runtime registry entry exists
```

If MSVC/C++ Build Tools or WebView2 Runtime is missing, stop before Tauri runtime
acceptance and record an environment note. Do not claim Windows MVP acceptance
from a non-Windows or incomplete Windows toolchain.

- [ ] **Step 5: Verify current Python tests before frontend work**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/integration/supervisor/test_supervisor_state_projection.py -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit worktree creation is not a commit**

No commit is needed in this task. Worktree creation is workspace setup only.

### Task 1: Desktop Scaffold

**Files:**
- Create: `apps/desktop/package.json`
- Create: `apps/desktop/svelte.config.js`
- Create: `apps/desktop/vite.config.ts`
- Create: `apps/desktop/tsconfig.json`
- Create: `apps/desktop/tailwind.config.ts`
- Create: `apps/desktop/postcss.config.cjs`
- Create: `apps/desktop/src/app.css`
- Create: `apps/desktop/src/app.html`
- Create: `apps/desktop/src/routes/+layout.svelte`
- Create: `apps/desktop/src/routes/+page.svelte`
- Create: `apps/desktop/src-tauri/Cargo.toml`
- Create: `apps/desktop/src-tauri/build.rs`
- Create: `apps/desktop/src-tauri/tauri.conf.json`
- Create: `apps/desktop/src-tauri/capabilities/default.json`
- Create: `apps/desktop/src-tauri/src/main.rs`
- Create: `apps/desktop/README.md`

- [ ] **Step 1: Create the desktop directory**

Run:

```bash
mkdir -p apps/desktop/src/routes apps/desktop/src/lib apps/desktop/src-tauri/src apps/desktop/src-tauri/capabilities
```

Expected: directories exist.

- [ ] **Step 2: Create `package.json`**

Create `apps/desktop/package.json`:

```json
{
  "name": "@isotope/desktop",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite --host 127.0.0.1",
    "build": "vite build",
    "preview": "vite preview --host 127.0.0.1",
    "prepare": "svelte-kit sync",
    "check": "svelte-kit sync && svelte-check --tsconfig ./tsconfig.json",
    "test": "vitest run --passWithNoTests",
    "tauri": "tauri"
  },
  "dependencies": {
    "@sveltejs/adapter-static": "^3.0.8",
    "@sveltejs/kit": "^2.15.0",
    "@tauri-apps/api": "^2.0.0",
    "@tauri-apps/plugin-global-shortcut": "^2.0.0",
    "svelte": "^5.0.0"
  },
  "devDependencies": {
    "@sveltejs/vite-plugin-svelte": "^5.0.0",
    "@tauri-apps/cli": "^2.0.0",
    "autoprefixer": "^10.4.20",
    "jsdom": "^26.0.0",
    "postcss": "^8.4.49",
    "svelte-check": "^4.0.0",
    "tailwindcss": "^3.4.17",
    "typescript": "^5.7.2",
    "vite": "^6.0.0",
    "vitest": "^2.1.8"
  }
}
```

- [ ] **Step 3: Add SvelteKit static SPA config**

Create `apps/desktop/svelte.config.js`:

```js
import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

const config = {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      pages: 'build',
      assets: 'build',
      fallback: 'index.html'
    })
  }
};

export default config;
```

- [ ] **Step 4: Add Vite/Vitest config**

Create `apps/desktop/vite.config.ts`:

```ts
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [sveltekit()],
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.ts']
  }
});
```

- [ ] **Step 5: Add TypeScript config**

Create `apps/desktop/tsconfig.json`:

```json
{
  "extends": "./.svelte-kit/tsconfig.json",
  "compilerOptions": {
    "allowJs": false,
    "checkJs": false,
    "esModuleInterop": true,
    "forceConsistentCasingInFileNames": true,
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "skipLibCheck": true,
    "sourceMap": true,
    "strict": true
  }
}
```

- [ ] **Step 6: Add Tailwind/PostCSS config**

Create `apps/desktop/tailwind.config.ts`:

```ts
import type { Config } from 'tailwindcss';

export default {
  content: ['./src/**/*.{html,js,svelte,ts}'],
  theme: {
    extend: {
      colors: {
        isotope: {
          bg: '#f6f7f9',
          panel: '#ffffff',
          text: '#1f2933',
          muted: '#667085',
          line: '#d9dee7',
          attention: '#b42318',
          running: '#175cd3',
          done: '#067647'
        }
      },
      borderRadius: {
        panel: '6px'
      }
    }
  },
  plugins: []
} satisfies Config;
```

Create `apps/desktop/postcss.config.cjs`:

```js
module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {}
  }
};
```

- [ ] **Step 7: Add base Svelte files**

Create `apps/desktop/src/app.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  color-scheme: light;
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

body {
  margin: 0;
  background: transparent;
  color: #1f2933;
}

button,
input,
textarea {
  font: inherit;
}
```

Create `apps/desktop/src/app.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    %sveltekit.head%
  </head>
  <body data-sveltekit-preload-data="hover">
    <div>%sveltekit.body%</div>
  </body>
</html>
```

Create `apps/desktop/src/routes/+layout.svelte`:

```svelte
<script lang="ts">
  import '../app.css';
  let { children } = $props();
</script>

{@render children()}
```

Create `apps/desktop/src/routes/+page.svelte`:

```svelte
<script lang="ts">
  const title = 'Isotope Desktop';
</script>

<main class="min-h-screen bg-isotope-bg p-6 text-isotope-text">
  <h1 class="text-xl font-semibold">{title}</h1>
  <p class="mt-2 text-sm text-isotope-muted">
    Desktop scaffold is ready. Orb, MiniWindow, and MainWindow land in later tasks.
  </p>
</main>
```

- [ ] **Step 8: Add minimal Tauri config**

Create `apps/desktop/src-tauri/Cargo.toml`:

```toml
[package]
name = "isotope-desktop"
version = "0.1.0"
edition = "2021"

[build-dependencies]
tauri-build = { version = "2", features = [] }

[dependencies]
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tauri = { version = "2", features = [] }
tauri-plugin-global-shortcut = "2"
```

Create `apps/desktop/src-tauri/build.rs`:

```rust
fn main() {
    tauri_build::build()
}
```

Create `apps/desktop/src-tauri/tauri.conf.json`:

```json
{
  "$schema": "https://schema.tauri.app/config/2",
  "productName": "Isotope",
  "version": "0.1.0",
  "identifier": "dev.isotope.desktop",
  "build": {
    "beforeDevCommand": "npm run dev",
    "devUrl": "http://127.0.0.1:5173",
    "beforeBuildCommand": "npm run build",
    "frontendDist": "../build"
  },
  "app": {
    "windows": [
      {
        "label": "main",
        "title": "Isotope",
        "width": 1180,
        "height": 760,
        "minWidth": 860,
        "minHeight": 560,
        "resizable": true,
        "visible": true
      }
    ],
    "security": {
      "csp": null
    }
  },
  "bundle": {
    "active": false,
    "targets": "all",
    "icon": []
  }
}
```

Create `apps/desktop/src-tauri/capabilities/default.json`:

```json
{
  "$schema": "../gen/schemas/desktop-schema.json",
  "identifier": "default",
  "description": "Default capability for Isotope desktop MVP",
  "windows": ["main", "orb", "mini"],
  "permissions": [
    "core:default",
    "global-shortcut:default"
  ]
}
```

`orb` and `mini` are created dynamically in Task 9. They are still listed here
so their webviews receive the same baseline capability grants once created.

Create `apps/desktop/src-tauri/src/main.rs`:

```rust
fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .run(tauri::generate_context!())
        .expect("failed to run Isotope desktop");
}
```

- [ ] **Step 9: Add desktop README**

Create `apps/desktop/README.md`:

```markdown
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
```

- [ ] **Step 10: Install frontend dependencies after scaffold files exist**

Run:

```bash
cd apps/desktop
npm install
```

Expected:

```text
added <n> packages
found 0 vulnerabilities
```

`npm install` runs the `prepare` script, so this step must happen after
`svelte.config.js`, `tsconfig.json`, `src/app.html`, and the base route files
exist. If npm reports vulnerabilities, record them in the task notes and do not
hide them.

- [ ] **Step 11: Run scaffold checks**

Run:

```bash
cd apps/desktop
npm run check
npm run test
npm run build
```

Expected:

```text
svelte-check found 0 errors and 0 warnings
No test files found, exiting with code 0
build completed
```

The `test` script uses `--passWithNoTests` so Task 1 can pass before contract tests exist.

- [ ] **Step 12: Commit scaffold**

Run:

```bash
git add apps/desktop
git commit -m "feat(desktop): scaffold Tauri Svelte app"
```

Expected: commit succeeds and stages only `apps/desktop`.

### Task 2: Frontend Contracts And Cursor Helpers

**Files:**
- Create: `apps/desktop/src/lib/contracts/isotope.ts`
- Create: `apps/desktop/src/lib/contracts/isotope.test.ts`

- [ ] **Step 1: Write failing contract tests**

Create `apps/desktop/src/lib/contracts/isotope.test.ts`:

```ts
import { describe, expect, test } from 'vitest';
import {
  cursorForEvent,
  isLowSensitivePreview,
  sortActivityNodes,
  type ActivityNode,
  type IsotopeEvent
} from './isotope';

const realSource = { kind: 'real' as const, label: 'test', backendRef: 'test://source' };

describe('desktop contract helpers', () => {
  test('uses eventCursor before id for resumable event cursor', () => {
    const event: IsotopeEvent = {
      id: 'uuid-event-1',
      eventCursor: 'cursor-10',
      type: 'message_created',
      createdAt: '2026-05-27T00:00:00Z',
      source: realSource,
      title: 'Message',
      payload: { messageId: 'msg-1', role: 'assistant', preview: 'Done.' }
    };

    expect(cursorForEvent(event)).toBe('cursor-10');
  });

  test('falls back to id when eventCursor is absent', () => {
    const event: IsotopeEvent = {
      id: 'cursor-11',
      type: 'worker_started',
      createdAt: '2026-05-27T00:00:01Z',
      source: realSource,
      title: 'Worker started',
      payload: { workerId: 'worker-1', workerTitle: 'Review worker' }
    };

    expect(cursorForEvent(event)).toBe('cursor-11');
  });

  test('sorts activity nodes by parent, order, createdAt, then title/id', () => {
    const nodes: ActivityNode[] = [
      { id: 'b', kind: 'worker', title: 'B', status: 'running', source: realSource, parentId: 'root', createdAt: '2026-05-27T00:00:03Z' },
      { id: 'a', kind: 'worker', title: 'A', status: 'running', source: realSource, parentId: 'root', order: 1, createdAt: '2026-05-27T00:00:04Z' },
      { id: 'c', kind: 'worker', title: 'C', status: 'running', source: realSource, parentId: 'root', order: 0, createdAt: '2026-05-27T00:00:05Z' }
    ];

    expect(sortActivityNodes(nodes).map((node) => node.id)).toEqual(['c', 'a', 'b']);
  });

  test('rejects previews that expose obvious secrets or large content', () => {
    expect(isLowSensitivePreview('Short status summary.')).toBe(true);
    expect(isLowSensitivePreview('token=sk-test-secret')).toBe(false);
    expect(isLowSensitivePreview('x'.repeat(2200))).toBe(false);
  });
});
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
cd apps/desktop
npm run test -- src/lib/contracts/isotope.test.ts
```

Expected: FAIL because `./isotope` does not exist.

- [ ] **Step 3: Implement contracts and helpers**

Create `apps/desktop/src/lib/contracts/isotope.ts` with the final types from the design spec, plus these helpers:

```ts
export type DataSourceKind = 'real' | 'mock' | 'replay_mock' | 'derived';

export type ResourceRef = {
  kind:
    | 'activity'
    | 'session'
    | 'agent'
    | 'goal'
    | 'event'
    | 'artifact'
    | 'approval'
    | 'tool_call'
    | 'capability_run';
  id: string;
  label?: string;
};

export type DataSourceInfo = {
  kind: DataSourceKind;
  label: string;
  backendRef?: string;
  sourceRef?: ResourceRef;
  replacementCondition?: string;
  mockReason?: string;
  expectedRealContract?: string;
};

export type ActivityNodeKind =
  | 'supervisor'
  | 'worker'
  | 'agent'
  | 'goal'
  | 'capability_run'
  | 'tool_call'
  | 'artifact'
  | 'group';

export type ActivityStatus =
  | 'idle'
  | 'running'
  | 'needs_attention'
  | 'done'
  | 'blocked'
  | 'error'
  | 'unknown';

export type ActivityNode = {
  id: string;
  kind: ActivityNodeKind;
  title: string;
  status: ActivityStatus;
  source: DataSourceInfo;
  parentId?: string;
  childIds?: string[];
  relatedRefs?: ResourceRef[];
  sourceRef?: ResourceRef;
  order?: number;
  createdAt?: string;
  updatedAt?: string;
  summary?: string;
};

export type ActivitySummary = {
  id: string;
  kind: ActivityNodeKind;
  title: string;
  status: ActivityStatus;
  source: DataSourceInfo;
};

export type AgentSummary = {
  id: string;
  title: string;
  status: ActivityStatus;
  kind?: 'supervisor' | 'worker' | 'agent';
  role?: string;
  source: DataSourceInfo;
  updatedAt?: string;
};

export type GoalSummary = {
  id: string;
  title: string;
  status: ActivityStatus;
  source: DataSourceInfo;
  updatedAt?: string;
};

export type ApprovalSummary = {
  id: string;
  title: string;
  status: 'pending' | 'resolved' | 'expired';
  riskLevel?: 'low' | 'medium' | 'high';
  source: DataSourceInfo;
};

export type ArtifactSummary = {
  id: string;
  title: string;
  artifactRef: ResourceRef;
  source: DataSourceInfo;
};

export type ToolCallSummary = {
  id: string;
  toolName: string;
  status: 'running' | 'success' | 'failed' | 'cancelled' | 'unknown';
  source: DataSourceInfo;
};

export type SnapshotCounts = {
  runningAgents: number;
  needsAttention: number;
  approvals: number;
  artifacts: number;
  errors: number;
};

export type IsotopeSnapshot = {
  schemaVersion: 1;
  snapshotId: string;
  generatedAt: string;
  eventCursor?: string;
  lastEventId?: string;
  source: DataSourceInfo;
  activeActivity?: ActivitySummary;
  activeAgent?: AgentSummary;
  activeGoal?: GoalSummary;
  counts: SnapshotCounts;
  agents: AgentSummary[];
  activities: ActivityNode[];
  approvals: ApprovalSummary[];
  artifacts: ArtifactSummary[];
  runningToolCalls: ToolCallSummary[];
};

export type BaseEvent = {
  id: string;
  eventCursor?: string;
  createdAt: string;
  source: DataSourceInfo;
  activityId?: string;
  agentId?: string;
  parentEventId?: string;
  relatedRefs?: ResourceRef[];
  severity?: 'info' | 'success' | 'warning' | 'error';
  title: string;
  summary?: string;
  payloadPreview?: unknown;
};

export type IsotopeEvent =
  | (BaseEvent & { type: 'message_created'; payload: { messageId: string; role: 'user' | 'assistant' | 'system' | 'tool'; preview: string } })
  | (BaseEvent & { type: 'worker_started'; payload: { workerId: string; workerTitle: string } })
  | (BaseEvent & { type: 'worker_finished'; payload: { workerId: string; result: 'done' | 'blocked' | 'failed' | 'cancelled' | 'unknown' } })
  | (BaseEvent & { type: 'tool_call_started'; payload: { toolCallId: string; toolName: string } })
  | (BaseEvent & { type: 'tool_call_finished'; payload: { toolCallId: string; toolName: string; result: 'success' | 'failed' | 'cancelled' | 'unknown' } })
  | (BaseEvent & { type: 'approval_required'; payload: { approvalId: string; riskLevel?: 'low' | 'medium' | 'high'; promptPreview: string } })
  | (BaseEvent & { type: 'approval_resolved'; payload: { approvalId: string; resolution: 'approved' | 'denied' | 'expired' | 'cancelled' } })
  | (BaseEvent & { type: 'artifact_created'; payload: { artifactRef: ResourceRef } })
  | (BaseEvent & { type: 'error_reported'; payload: { errorCode?: string; message: string } })
  | (BaseEvent & { type: 'snapshot_updated'; payload: { snapshotId?: string; eventCursor?: string } });

export type EventReplayResponse = {
  events: IsotopeEvent[];
  nextCursor?: string;
  hasMore: boolean;
};

export function cursorForEvent(event: IsotopeEvent): string {
  return event.eventCursor ?? event.id;
}

export function sortActivityNodes(nodes: ActivityNode[]): ActivityNode[] {
  return [...nodes].sort((left, right) => {
    const leftOrder = left.order ?? Number.POSITIVE_INFINITY;
    const rightOrder = right.order ?? Number.POSITIVE_INFINITY;
    if (leftOrder !== rightOrder) return leftOrder - rightOrder;
    const leftCreated = left.createdAt ?? '';
    const rightCreated = right.createdAt ?? '';
    if (leftCreated !== rightCreated) return leftCreated.localeCompare(rightCreated);
    const titleCompare = left.title.localeCompare(right.title);
    if (titleCompare !== 0) return titleCompare;
    return left.id.localeCompare(right.id);
  });
}

export function isLowSensitivePreview(value: string): boolean {
  const normalized = value.toLowerCase();
  if (value.length > 2000) return false;
  return !/(api[_-]?key|secret|token|sk-[a-z0-9_-]+)/i.test(normalized);
}
```

- [ ] **Step 4: Run tests**

Run:

```bash
cd apps/desktop
npm run test -- src/lib/contracts/isotope.test.ts
npm run check
```

Expected:

```text
PASS src/lib/contracts/isotope.test.ts
svelte-check found 0 errors and 0 warnings
```

- [ ] **Step 5: Commit contracts**

Run:

```bash
git add apps/desktop/src/lib/contracts
git commit -m "feat(desktop): add frontend state contracts"
```

Expected: commit succeeds.

### Task 3: Supervisor Desktop Snapshot Adapter

**Files:**
- Create: `src/isotope/features/supervisor/desktop_snapshot.py`
- Create: `tests/integration/supervisor/test_supervisor_desktop_snapshot.py`
- Modify: `src/isotope/features/supervisor/web.py`

- [ ] **Step 1: Write failing Python tests for empty snapshot**

Create `tests/integration/supervisor/test_supervisor_desktop_snapshot.py`:

```python
from __future__ import annotations

from isotope.features.supervisor.desktop_snapshot import build_desktop_snapshot, _low_sensitive_preview


def test_desktop_snapshot_empty_root_uses_contract_shape(tmp_path):
    snapshot = build_desktop_snapshot(codex_home=tmp_path)

    assert snapshot["schemaVersion"] == 1
    assert isinstance(snapshot["snapshotId"], str)
    assert snapshot["source"] == {
        "kind": "real",
        "label": "supervisor_state_projection",
        "backendRef": f"codex_home:{tmp_path}",
    }
    assert snapshot["counts"] == {
        "runningAgents": 0,
        "needsAttention": 0,
        "approvals": 0,
        "artifacts": 0,
        "errors": 0,
    }
    assert snapshot["activeAgent"]["kind"] == "supervisor"
    assert snapshot["activeAgent"]["source"]["kind"] == "real"
    assert snapshot["agents"][0]["kind"] == "supervisor"
    assert snapshot["activities"][0]["kind"] == "supervisor"
    assert snapshot["activities"][0]["source"]["backendRef"] == f"codex_home:{tmp_path}"
    assert snapshot["approvals"] == []
    assert snapshot["artifacts"] == []
    assert snapshot["runningToolCalls"] == []
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/integration/supervisor/test_supervisor_desktop_snapshot.py -q
```

Expected: FAIL because `desktop_snapshot.py` does not exist.

- [ ] **Step 3: Implement minimal empty snapshot adapter**

Create `src/isotope/features/supervisor/desktop_snapshot.py`:

```python
"""Desktop snapshot adapter for the Isotope desktop frontend."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from isotope.features.supervisor.state.projection import build_supervisor_state_snapshot
from isotope.platform.ids import new_id


def build_desktop_snapshot(*, codex_home: Path | str) -> dict[str, Any]:
    root = Path(codex_home)
    supervisor = build_supervisor_state_snapshot(codex_home=root)
    summary = supervisor.get("summary", {})
    source = {
        "kind": "real",
        "label": "supervisor_state_projection",
        "backendRef": f"codex_home:{root}",
    }
    supervisor_agent = {
        "id": "supervisor_root",
        "title": "Isotope Supervisor",
        "status": "idle",
        "kind": "supervisor",
        "role": "coordinator",
        "source": source,
    }
    supervisor_activity = {
        "id": "activity_supervisor_root",
        "kind": "supervisor",
        "title": "Isotope Supervisor",
        "status": "idle",
        "source": source,
        "sourceRef": {"kind": "agent", "id": "supervisor_root", "label": "Isotope Supervisor"},
        "order": 0,
        "summary": "Supervisor state projection is connected.",
    }
    return {
        "schemaVersion": 1,
        "snapshotId": new_id("desktop_snapshot"),
        "generatedAt": datetime.now(UTC).isoformat(),
        "eventCursor": None,
        "lastEventId": None,
        "source": source,
        "activeActivity": supervisor_activity,
        "activeAgent": supervisor_agent,
        "activeGoal": None,
        "counts": {
            "runningAgents": 0,
            "needsAttention": int(summary.get("active_decisions", 0) or 0)
            + int(summary.get("failed_lanes", 0) or 0),
            "approvals": int(summary.get("active_decisions", 0) or 0),
            "artifacts": 0,
            "errors": int(summary.get("failed_lanes", 0) or 0),
        },
        "agents": [supervisor_agent],
        "activities": [supervisor_activity],
        "approvals": [],
        "artifacts": [],
        "runningToolCalls": [],
    }


def _low_sensitive_preview(value: object) -> str | None:
    text = str(value)
    lowered = text.lower()
    if len(text) > 2000:
        return None
    if any(marker in lowered for marker in ("api_key", "api-key", "secret", "token=", "sk-")):
        return None
    return text
```

- [ ] **Step 4: Run empty snapshot test**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/integration/supervisor/test_supervisor_desktop_snapshot.py -q
```

Expected: PASS.

- [ ] **Step 5: Add test for active goal mapping**

Append to `tests/integration/supervisor/test_supervisor_desktop_snapshot.py`:

```python
from isotope.features.supervisor.planner.goal_queue import record_supervisor_goal


def test_desktop_snapshot_maps_active_goal_to_activity(tmp_path):
    record_supervisor_goal(
        codex_home=tmp_path,
        goal="Ship the desktop MVP",
        cwd="/repo",
        target_name="desktop-mvp",
        depends_on=(),
        stage="frontend",
        scope="desktop",
        merge_gate="manual",
    )

    snapshot = build_desktop_snapshot(codex_home=tmp_path)

    assert snapshot["activities"][0]["kind"] == "supervisor"
    assert snapshot["activeGoal"]["title"] == "Ship the desktop MVP"
    goal_node = next(activity for activity in snapshot["activities"] if activity["kind"] == "goal")
    assert goal_node["title"] == "Ship the desktop MVP"
    assert goal_node["parentId"] == snapshot["activities"][0]["id"]
    assert snapshot["activeGoal"]["id"] == goal_node["sourceRef"]["id"]
    assert goal_node["source"]["kind"] == "derived"
    assert goal_node["source"]["sourceRef"]["kind"] == "goal"


def test_desktop_snapshot_redacts_long_or_secret_preview_content(tmp_path):
    snapshot = build_desktop_snapshot(codex_home=tmp_path)

    serialized = str(snapshot).lower()

    assert "sk-test-secret" not in serialized
    assert "token=" not in serialized
    assert "x" * 2200 not in serialized


def test_low_sensitive_preview_guard_rejects_secrets_and_long_content():
    assert _low_sensitive_preview("Short status summary.") == "Short status summary."
    assert _low_sensitive_preview("token=sk-test-secret") is None
    assert _low_sensitive_preview("x" * 2200) is None
```

- [ ] **Step 6: Implement active goal mapping**

Modify `build_desktop_snapshot(...)` so it maps `supervisor["active_goals"]` to `GoalSummary` and `ActivityNode`:

```python
def _goal_activity(goal: dict[str, Any], *, index: int) -> dict[str, Any]:
    goal_id = str(goal["goal_id"])
    title = str(goal["goal"])
    source_ref = {"kind": "goal", "id": goal_id, "label": title}
    return {
        "id": f"activity_goal_{goal_id}",
        "kind": "goal",
        "title": title,
        "status": _goal_status(goal),
        "source": {
            "kind": "derived",
            "label": "supervisor_active_goal",
            "sourceRef": source_ref,
        },
        "sourceRef": source_ref,
        "order": index,
        "createdAt": goal.get("created_at"),
        "updatedAt": goal.get("last_status_at") or goal.get("created_at"),
        "summary": goal.get("last_summary") or title,
    }


def _goal_summary(goal: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(goal["goal_id"]),
        "kind": "goal",
        "title": str(goal["goal"]),
        "status": _goal_status(goal),
        "source": {
            "kind": "derived",
            "label": "supervisor_active_goal",
            "sourceRef": {"kind": "goal", "id": str(goal["goal_id"]), "label": str(goal["goal"])},
        },
        "updatedAt": goal.get("last_status_at") or goal.get("created_at"),
    }


def _goal_status(goal: dict[str, Any]) -> str:
    status = goal.get("last_status")
    if status in {"done", "blocked", "needs_attention", "error", "running"}:
        return str(status)
    return "running"
```

Then set:

```python
active_goals = list(supervisor.get("active_goals", []))
goal_activities = [_goal_activity(goal, index=index) for index, goal in enumerate(active_goals)]
active_goal = _goal_summary(active_goals[0]) if active_goals else None
activities = [
    supervisor_activity,
    *[
        {**activity, "parentId": supervisor_activity["id"], "order": index + 1}
        for index, activity in enumerate(goal_activities)
    ],
]
```

Update the returned snapshot so `activeGoal` is `active_goal`, `activities` is
`activities`, and `activeActivity` remains the supervisor root unless a later
reviewed interaction design chooses to focus the active goal by default. The
important MVP invariant is: even with no worker and no active goal, the snapshot
still exposes real Supervisor basic information through `activeAgent`,
`agents[0]`, and a supervisor/root `ActivityNode` traceable to
`supervisor_state_projection`.

- [ ] **Step 7: Add desktop snapshot HTTP endpoint**

Modify `src/isotope/features/supervisor/web.py`.

Add this import near the other supervisor imports:

```python
from isotope.features.supervisor.desktop_snapshot import build_desktop_snapshot
```

Add this method to `SupervisorDashboardServer`:

```python
    def desktop_snapshot_payload(self) -> dict[str, Any]:
        return build_desktop_snapshot(codex_home=self.codex_home)
```

Add this branch in `_DashboardRequestHandler.do_GET` after `/dashboard.json` and
before `/events`:

```python
        if path == "/desktop/snapshot":
            payload = self.server.desktop_snapshot_payload()
            self._send_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                content_type="application/json; charset=utf-8",
            )
            return
```

This endpoint is the MVP real snapshot path used by the desktop frontend. Do not
rename it to `/snapshot`; frontend Task 4 must fetch `/desktop/snapshot`.

- [ ] **Step 8: Add endpoint smoke test**

Append to `tests/integration/supervisor/test_supervisor_desktop_snapshot.py`:

```python
import http.client
import json
import threading

from isotope.features.supervisor.web import create_dashboard_server


def test_desktop_snapshot_endpoint_serves_real_snapshot(tmp_path):
    server = create_dashboard_server(
        codex_home=tmp_path,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/desktop/snapshot")
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 200
    assert payload["schemaVersion"] == 1
    assert payload["source"]["kind"] == "real"
```

- [ ] **Step 9: Run tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/integration/supervisor/test_supervisor_desktop_snapshot.py tests/integration/supervisor/test_supervisor_state_projection.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit snapshot adapter and endpoint**

Run:

```bash
git add src/isotope/features/supervisor/desktop_snapshot.py \
        src/isotope/features/supervisor/web.py \
        tests/integration/supervisor/test_supervisor_desktop_snapshot.py
git commit -m "feat(supervisor): add desktop snapshot adapter"
```

Expected: commit succeeds.

### Task 4: Frontend Clients And Mock Boundaries

**Files:**
- Create: `apps/desktop/src/lib/client/mockData.ts`
- Create: `apps/desktop/src/lib/client/agentClient.ts`
- Create: `apps/desktop/src/lib/client/eventClient.ts`
- Create: `apps/desktop/src/lib/client/windowClient.ts`
- Create: `apps/desktop/src/lib/client/isotopeClient.ts`
- Create: `apps/desktop/src/lib/client/eventClient.test.ts`

- [ ] **Step 1: Write failing event client tests**

Create `apps/desktop/src/lib/client/eventClient.test.ts`:

```ts
import { describe, expect, test } from 'vitest';
import { buildEventStreamUrl, chooseReconnectCursor } from './eventClient';

describe('eventClient cursor behavior', () => {
  test('builds first stream URL with query cursor', () => {
    expect(buildEventStreamUrl('/desktop/events/stream', 'cursor-1')).toBe('/desktop/events/stream?cursor=cursor-1');
  });

  test('keeps absolute stream URL host and port', () => {
    expect(buildEventStreamUrl('http://127.0.0.1:1234/desktop/events/stream', 'cursor-1')).toBe(
      'http://127.0.0.1:1234/desktop/events/stream?cursor=cursor-1'
    );
  });

  test('uses Last-Event-ID for automatic reconnect when cursors are not comparable', () => {
    expect(chooseReconnectCursor({ queryCursor: 'cursor-1', lastEventId: 'cursor-9', comparable: false })).toBe('cursor-9');
  });

  test('uses later comparable cursor', () => {
    expect(chooseReconnectCursor({ queryCursor: '10', lastEventId: '12', comparable: true })).toBe('12');
  });
});
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
cd apps/desktop
npm run test -- src/lib/client/eventClient.test.ts
```

Expected: FAIL because `eventClient` does not exist.

- [ ] **Step 3: Implement client files**

Create `apps/desktop/src/lib/client/eventClient.ts`:

```ts
import type { EventReplayResponse, IsotopeEvent } from '../contracts/isotope';
import { replayMockEvents } from './mockData';

export type ReconnectCursorInput = {
  queryCursor?: string;
  lastEventId?: string;
  comparable: boolean;
};

export function buildEventStreamUrl(baseUrl: string, cursor?: string): string {
  if (!cursor) return baseUrl;
  const isAbsolute = /^https?:\/\//.test(baseUrl);
  const url = new URL(baseUrl, isAbsolute ? undefined : 'http://localhost');
  url.searchParams.set('cursor', cursor);
  return isAbsolute ? url.toString() : `${url.pathname}${url.search}`;
}

export function chooseReconnectCursor(input: ReconnectCursorInput): string | undefined {
  if (!input.queryCursor) return input.lastEventId;
  if (!input.lastEventId) return input.queryCursor;
  if (!input.comparable) return input.lastEventId;
  return Number(input.lastEventId) > Number(input.queryCursor)
    ? input.lastEventId
    : input.queryCursor;
}

export type EventClient = {
  replay(cursor?: string, limit?: number): Promise<EventReplayResponse>;
  stream(cursor: string | undefined, onEvent: (event: IsotopeEvent) => void): () => void;
};

export function createEventClient(baseUrl = ''): EventClient {
  return {
    async replay(cursor, limit) {
      try {
        const params = new URLSearchParams();
        if (cursor) params.set('cursor', cursor);
        if (limit) params.set('limit', String(limit));
        const response = await fetch(`${baseUrl}/desktop/events?${params.toString()}`);
        if (!response.ok) {
          return { events: replayMockEvents, hasMore: false };
        }
        return (await response.json()) as EventReplayResponse;
      } catch {
        return { events: replayMockEvents, hasMore: false };
      }
    },
    stream(cursor, onEvent) {
      const source = new EventSource(buildEventStreamUrl(`${baseUrl}/desktop/events/stream`, cursor));
      source.onmessage = (message) => onEvent(JSON.parse(message.data) as IsotopeEvent);
      return () => source.close();
    }
  };
}
```

Create `apps/desktop/src/lib/client/mockData.ts`:

```ts
import type { IsotopeEvent, IsotopeSnapshot } from '../contracts/isotope';

const mockSource = {
  kind: 'mock' as const,
  label: 'desktop_mock_snapshot',
  mockReason: 'The real /desktop/snapshot endpoint is unavailable in this frontend runtime.',
  expectedRealContract: 'IsotopeSnapshot from Python/Supervisor desktop snapshot adapter'
};

const replaySource = {
  kind: 'replay_mock' as const,
  label: 'desktop_replay_mock_events',
  mockReason: 'No desktop event replay endpoint is connected in the frontend scaffold.',
  expectedRealContract: 'EventReplayResponse from Python/Supervisor desktop event replay adapter'
};

export const mockSnapshot: IsotopeSnapshot = {
  schemaVersion: 1,
  snapshotId: 'mock_snapshot_001',
  generatedAt: '2026-05-27T00:00:00Z',
  eventCursor: 'mock_cursor_001',
  lastEventId: 'mock_cursor_001',
  source: mockSource,
  activeActivity: {
    id: 'activity_supervisor_mock',
    kind: 'supervisor',
    title: 'Mock Supervisor',
    status: 'running',
    source: mockSource
  },
  activeAgent: {
    id: 'agent_supervisor_mock',
    title: 'Mock Supervisor',
    status: 'running',
    kind: 'supervisor',
    role: 'coordinator',
    source: mockSource
  },
  activeGoal: {
    id: 'goal_desktop_mock',
    title: 'Connect the desktop MVP',
    status: 'running',
    source: mockSource
  },
  counts: {
    runningAgents: 1,
    needsAttention: 0,
    approvals: 0,
    artifacts: 0,
    errors: 0
  },
  agents: [],
  activities: [
    {
      id: 'activity_supervisor_mock',
      kind: 'supervisor',
      title: 'Mock Supervisor',
      status: 'running',
      source: mockSource,
      order: 0,
      createdAt: '2026-05-27T00:00:00Z'
    }
  ],
  approvals: [],
  artifacts: [],
  runningToolCalls: []
};

export const replayMockEvents: IsotopeEvent[] = [
  {
    id: 'mock_event_001',
    eventCursor: 'mock_cursor_001',
    type: 'message_created',
    createdAt: '2026-05-27T00:00:01Z',
    source: replaySource,
    activityId: 'activity_supervisor_mock',
    title: 'Mock supervisor status',
    summary: 'Desktop event contract is rendering replay_mock data.',
    payload: {
      messageId: 'mock_message_001',
      role: 'assistant',
      preview: 'Desktop event contract is rendering replay_mock data.'
    }
  },
  {
    id: 'mock_event_002',
    eventCursor: 'mock_cursor_002',
    type: 'worker_started',
    createdAt: '2026-05-27T00:00:02Z',
    source: replaySource,
    activityId: 'activity_supervisor_mock',
    title: 'Mock worker started',
    payload: {
      workerId: 'worker_mock_001',
      workerTitle: 'Mock desktop worker'
    }
  }
];
```

Create `apps/desktop/src/lib/client/agentClient.ts` with:

```ts
import type { IsotopeSnapshot } from '../contracts/isotope';
import { mockSnapshot } from './mockData';

export type SubmitMode = 'real' | 'mock' | 'disabled';

export type AgentClient = {
  loadSnapshot(): Promise<IsotopeSnapshot>;
  submitMiniCommand(text: string): Promise<{ mode: SubmitMode; preview: string }>;
};

export function createAgentClient(baseUrl = ''): AgentClient {
  return {
    async loadSnapshot() {
      try {
        const response = await fetch(`${baseUrl}/desktop/snapshot`, { cache: 'no-store' });
        if (!response.ok) return mockSnapshot;
        return (await response.json()) as IsotopeSnapshot;
      } catch {
        return mockSnapshot;
      }
    },
    async submitMiniCommand(text) {
      if (!text.trim()) return { mode: 'disabled', preview: 'Empty command disabled.' };
      return { mode: 'mock', preview: 'Command submit backend is not connected yet.' };
    }
  };
}
```

Create `windowClient.ts` with typed stubs for now:

```ts
export type WindowKind = 'orb' | 'mini' | 'main';

export type WindowSettings = {
  orbOpacity: number;
  miniOpacity: number;
  quietMode: boolean;
  reducedMotion: boolean;
};

export type WindowClient = {
  open(kind: WindowKind, options?: { focus?: boolean }): Promise<void>;
  close(kind: WindowKind): Promise<void>;
  savePosition(kind: WindowKind, position: { x: number; y: number }): Promise<void>;
  loadSettings(): Promise<WindowSettings>;
};

export function createWindowClient(): WindowClient {
  return {
    async open() {},
    async close() {},
    async savePosition() {},
    async loadSettings() {
      return { orbOpacity: 0.92, miniOpacity: 0.96, quietMode: false, reducedMotion: false };
    }
  };
}
```

Create `apps/desktop/src/lib/client/isotopeClient.ts`:

```ts
import { createAgentClient } from './agentClient';
import { createEventClient } from './eventClient';
import { createWindowClient } from './windowClient';

export function resolveDesktopApiBaseUrl(): string | null {
  const configured = import.meta.env.VITE_ISOTOPE_DESKTOP_API_BASE as string | undefined;
  if (configured?.trim()) return configured.replace(/\/$/, '');
  return null;
}

export function createIsotopeClient(baseUrl: string | null = resolveDesktopApiBaseUrl()) {
  const apiBaseUrl = baseUrl ?? '';
  return {
    apiBaseUrl,
    hasRealApiBaseUrl: Boolean(baseUrl),
    agentClient: createAgentClient(apiBaseUrl),
    eventClient: createEventClient(apiBaseUrl),
    windowClient: createWindowClient()
  };
}

export type IsotopeClient = ReturnType<typeof createIsotopeClient>;
```

- [ ] **Step 4: Run tests and checks**

Run:

```bash
cd apps/desktop
npm run test
npm run check
```

Expected: PASS.

- [ ] **Step 5: Commit clients**

Run:

```bash
git add apps/desktop/src/lib/client
git commit -m "feat(desktop): add typed frontend clients"
```

Expected: commit succeeds.

### Task 5: App State Stores

**Files:**
- Create: `apps/desktop/src/lib/stores/appState.ts`
- Create: `apps/desktop/src/lib/stores/appState.test.ts`

- [ ] **Step 1: Write failing store tests**

Create `apps/desktop/src/lib/stores/appState.test.ts`:

```ts
import { get } from 'svelte/store';
import { describe, expect, test } from 'vitest';
import { createAppState } from './appState';
import { mockSnapshot, replayMockEvents } from '../client/mockData';

describe('appState', () => {
  test('loads snapshot and selects active activity', async () => {
    const state = createAppState({
      agentClient: { loadSnapshot: async () => mockSnapshot, submitMiniCommand: async () => ({ mode: 'mock', preview: 'mock' }) },
      eventClient: { replay: async () => ({ events: replayMockEvents, hasMore: false }), stream: () => () => {} },
      windowClient: {
        open: async () => {},
        close: async () => {},
        savePosition: async () => {},
        loadSettings: async () => ({ orbOpacity: 0.9, miniOpacity: 0.9, quietMode: false, reducedMotion: false })
      }
    });

    await state.initialize();

    expect(get(state.snapshot)?.snapshotId).toBe(mockSnapshot.snapshotId);
    expect(get(state.events)).toHaveLength(replayMockEvents.length);
  });
});
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
cd apps/desktop
npm run test -- src/lib/stores/appState.test.ts
```

Expected: FAIL because `appState` does not exist.

- [ ] **Step 3: Implement `createAppState`**

Create `apps/desktop/src/lib/stores/appState.ts`:

```ts
import { writable } from 'svelte/store';
import type { IsotopeEvent, IsotopeSnapshot } from '../contracts/isotope';
import type { AgentClient } from '../client/agentClient';
import type { EventClient } from '../client/eventClient';
import type { WindowClient, WindowSettings } from '../client/windowClient';

export type AppClients = {
  agentClient: AgentClient;
  eventClient: EventClient;
  windowClient: WindowClient;
};

export function createAppState(clients: AppClients) {
  const snapshot = writable<IsotopeSnapshot | null>(null);
  const events = writable<IsotopeEvent[]>([]);
  const settings = writable<WindowSettings | null>(null);
  const selectedActivityId = writable<string | null>(null);

  return {
    snapshot,
    events,
    settings,
    selectedActivityId,
    async initialize() {
      const loadedSettings = await clients.windowClient.loadSettings();
      settings.set(loadedSettings);
      const loadedSnapshot = await clients.agentClient.loadSnapshot();
      snapshot.set(loadedSnapshot);
      selectedActivityId.set(loadedSnapshot.activeActivity?.id ?? loadedSnapshot.activities[0]?.id ?? null);
      const replay = await clients.eventClient.replay(loadedSnapshot.eventCursor ?? loadedSnapshot.lastEventId, 100);
      events.set(replay.events);
    }
  };
}
```

`VITE_ISOTOPE_DESKTOP_API_BASE` is the first-version backend discovery strategy.
For local testing, start the Supervisor dashboard server and run the desktop app
with:

```bash
VITE_ISOTOPE_DESKTOP_API_BASE=http://127.0.0.1:<supervisor-port> npm run dev
```

If `hasRealApiBaseUrl` is false, the UI may render the fallback mock snapshot,
but the implementation summary must mark real Supervisor snapshot acceptance as
not passed. A later Tauri/Rust task may replace this env var with an invoke that
starts or discovers the local Supervisor dashboard server and returns `baseUrl`.

- [ ] **Step 4: Run tests and checks**

Run:

```bash
cd apps/desktop
npm run test -- src/lib/stores/appState.test.ts
npm run check
```

Expected: PASS.

- [ ] **Step 5: Commit stores**

Run:

```bash
git add apps/desktop/src/lib/stores
git commit -m "feat(desktop): add app state store"
```

Expected: commit succeeds.

### Task 6: Floating Orb Component

**Files:**
- Create: `apps/desktop/src/lib/components/orb/FloatingOrb.svelte`
- Create: `apps/desktop/src/lib/components/common/SourceBadge.svelte`
- Modify: `apps/desktop/src/routes/+page.svelte`

From this task onward, `+page.svelte` must initialize through
`createAppState(createIsotopeClient(desktopApiBaseUrl))`. Direct `mockSnapshot` imports are
allowed only inside tests and `mockData.ts`; visible UI must show whether the
loaded snapshot source is `real` or fallback `mock`.

`+page.svelte` must also pass an explicit desktop API base URL into
`createIsotopeClient(...)`:

```ts
const desktopApiBaseUrl = import.meta.env.VITE_ISOTOPE_DESKTOP_API_BASE as string | undefined;
const isotopeClient = createIsotopeClient(desktopApiBaseUrl?.trim() || null);
```

If `desktopApiBaseUrl` is absent, the page may run in mock fallback mode for UI
development, but it must not be counted as passing the real snapshot MVP.

- [ ] **Step 1: Create source badge**

Create `apps/desktop/src/lib/components/common/SourceBadge.svelte`:

```svelte
<script lang="ts">
  import type { DataSourceInfo } from '../../contracts/isotope';
  let { source } = $props<{ source: DataSourceInfo }>();
</script>

<span class="rounded border border-isotope-line px-1.5 py-0.5 text-[11px] text-isotope-muted">
  {source.kind}
</span>
```

- [ ] **Step 2: Create FloatingOrb**

Create `apps/desktop/src/lib/components/orb/FloatingOrb.svelte`:

```svelte
<script lang="ts">
  import type { ActivitySummary, AgentSummary } from '../../contracts/isotope';

  let {
    activeActivity = null,
    activeAgent = null,
    quietMode = false,
    needsAttention = 0,
    onOpenMini
  } = $props<{
    activeActivity?: ActivitySummary | null;
    activeAgent?: AgentSummary | null;
    quietMode?: boolean;
    needsAttention?: number;
    onOpenMini: () => void;
  }>();

  const label = $derived(activeActivity?.title ?? activeAgent?.title ?? 'Isotope');
  const status = $derived(activeActivity?.status ?? activeAgent?.status ?? 'idle');
</script>

<button
  type="button"
  class="relative grid h-14 w-14 place-items-center rounded-full border border-isotope-line bg-white text-sm font-semibold shadow-lg transition hover:scale-[1.03] focus:outline-none focus:ring-2 focus:ring-isotope-running"
  class:animate-pulse={!quietMode && needsAttention > 0}
  aria-label={`Open Isotope: ${label}`}
  title={`${label} / ${status}`}
  onclick={onOpenMini}
>
  <span>Iso</span>
  {#if needsAttention > 0}
    <span class="absolute -right-1 -top-1 min-w-5 rounded-full bg-isotope-attention px-1 text-xs text-white">{needsAttention}</span>
  {/if}
</button>
```

- [ ] **Step 3: Wire in dev page**

Modify `apps/desktop/src/routes/+page.svelte`:

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { createIsotopeClient } from '$lib/client/isotopeClient';
  import FloatingOrb from '$lib/components/orb/FloatingOrb.svelte';
  import SourceBadge from '$lib/components/common/SourceBadge.svelte';
  import { createAppState } from '$lib/stores/appState';

  const desktopApiBaseUrl = import.meta.env.VITE_ISOTOPE_DESKTOP_API_BASE as string | undefined;
  const isotopeClient = createIsotopeClient(desktopApiBaseUrl?.trim() || null);
  const appState = createAppState(isotopeClient);
  const { snapshot, settings, initialize } = appState;
  let miniOpen = $state(false);

  onMount(() => {
    void initialize();
  });
</script>

<main class="min-h-screen bg-isotope-bg p-6 text-isotope-text">
  <div class="flex items-start justify-between gap-4">
    <div>
      <h1 class="text-xl font-semibold">Isotope Desktop</h1>
      <p class="mt-2 text-sm text-isotope-muted">
        FloatingOrb loads through isotopeClient. Source is visible.
      </p>
    </div>
    {#if $snapshot}
      <SourceBadge source={$snapshot.source} />
    {/if}
  </div>

  {#if $snapshot}
  <div class="mt-6">
    <FloatingOrb
      activeActivity={$snapshot.activeActivity}
      activeAgent={$snapshot.activeAgent}
      quietMode={$settings?.quietMode ?? false}
      needsAttention={$snapshot.counts.needsAttention}
      onOpenMini={() => (miniOpen = true)}
    />
  </div>

  {#if miniOpen}
    <p class="mt-4 text-sm text-isotope-muted">MiniWindow lands in Task 7.</p>
  {/if}
  {:else}
    <p class="mt-6 text-sm text-isotope-muted">Loading Supervisor snapshot...</p>
  {/if}
</main>
```

- [ ] **Step 4: Run checks**

Run:

```bash
cd apps/desktop
npm run check
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit orb**

Run:

```bash
git add apps/desktop/src/lib/components apps/desktop/src/routes/+page.svelte
git commit -m "feat(desktop): add floating orb"
```

Expected: commit succeeds.

### Task 7: MiniWindow Thin Loop

**Files:**
- Create: `apps/desktop/src/lib/components/common/CommandComposer.svelte`
- Create: `apps/desktop/src/lib/components/common/QuickActionArea.svelte`
- Create: `apps/desktop/src/lib/components/mini/MiniWindow.svelte`
- Modify: `apps/desktop/src/routes/+page.svelte`

- [ ] **Step 1: Add shared composer**

Create `CommandComposer.svelte`:

```svelte
<script lang="ts">
  let {
    placeholder = 'Message Isotope',
    disabled = false,
    onSubmit
  } = $props<{
    placeholder?: string;
    disabled?: boolean;
    onSubmit: (value: string) => void;
  }>();

  let value = $state('');

  function submit() {
    const text = value.trim();
    if (!text) return;
    onSubmit(text);
    value = '';
  }
</script>

<form class="flex gap-2" onsubmit={(event) => { event.preventDefault(); submit(); }}>
  <input
    class="min-w-0 flex-1 rounded border border-isotope-line px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-isotope-running"
    {placeholder}
    bind:value
    {disabled}
  />
  <button class="rounded bg-isotope-running px-3 py-2 text-sm text-white disabled:opacity-50" type="submit" {disabled}>
    Send
  </button>
</form>
```

- [ ] **Step 2: Add QuickActionArea**

Create `QuickActionArea.svelte`:

```svelte
<script lang="ts">
  let { onOpenMain } = $props<{ onOpenMain: () => void }>();
</script>

<div class="grid grid-cols-2 gap-2 text-xs">
  <button class="rounded border border-isotope-line px-2 py-1 text-left" type="button">/ commands</button>
  <button class="rounded border border-isotope-line px-2 py-1 text-left" type="button">Events</button>
  <button class="rounded border border-isotope-line px-2 py-1 text-left" type="button">Attention</button>
  <button class="rounded border border-isotope-line px-2 py-1 text-left" type="button" onclick={onOpenMain}>Open main</button>
</div>
```

- [ ] **Step 3: Add MiniWindow component**

Create `MiniWindow.svelte`:

```svelte
<script lang="ts">
  import type { IsotopeSnapshot } from '../../contracts/isotope';
  import SourceBadge from '../common/SourceBadge.svelte';
  import CommandComposer from '../common/CommandComposer.svelte';
  import QuickActionArea from '../common/QuickActionArea.svelte';

  let {
    snapshot,
    submitMode = 'disabled',
    onSubmit,
    onOpenMain,
    onClose
  } = $props<{
    snapshot: IsotopeSnapshot;
    submitMode?: 'real' | 'mock' | 'disabled';
    onSubmit: (text: string) => void;
    onOpenMain: () => void;
    onClose: () => void;
  }>();
</script>

<section class="w-[360px] rounded-panel border border-isotope-line bg-white p-3 shadow-xl">
  <header class="flex items-center justify-between gap-2">
    <div>
      <div class="text-sm font-semibold">{snapshot.activeActivity?.title ?? 'Isotope Supervisor'}</div>
      <div class="text-xs text-isotope-muted">submit: {submitMode}</div>
    </div>
    <div class="flex items-center gap-2">
      <SourceBadge source={snapshot.source} />
      <button type="button" onclick={onOpenMain} aria-label="Open main">□</button>
      <button type="button" onclick={onClose} aria-label="Close mini">×</button>
    </div>
  </header>

  <div class="mt-3 grid grid-cols-3 gap-2 text-xs">
    <div class="rounded bg-isotope-bg p-2">Running<br />{snapshot.counts.runningAgents}</div>
    <div class="rounded bg-isotope-bg p-2">Attention<br />{snapshot.counts.needsAttention}</div>
    <div class="rounded bg-isotope-bg p-2">Artifacts<br />{snapshot.counts.artifacts}</div>
  </div>

  <p class="mt-3 text-sm text-isotope-muted">
    {snapshot.activeGoal?.title ?? snapshot.activeAgent?.title ?? 'No active goal yet.'}
  </p>

  <div class="mt-3">
    <CommandComposer disabled={submitMode === 'disabled'} onSubmit={onSubmit} />
  </div>

  <div class="mt-3">
    <QuickActionArea {onOpenMain} />
  </div>
</section>
```

- [ ] **Step 4: Wire MiniWindow into dev page**

Modify `apps/desktop/src/routes/+page.svelte`:

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { createIsotopeClient } from '$lib/client/isotopeClient';
  import type { SubmitMode } from '$lib/client/agentClient';
  import FloatingOrb from '$lib/components/orb/FloatingOrb.svelte';
  import MiniWindow from '$lib/components/mini/MiniWindow.svelte';
  import SourceBadge from '$lib/components/common/SourceBadge.svelte';
  import { createAppState } from '$lib/stores/appState';

  const desktopApiBaseUrl = import.meta.env.VITE_ISOTOPE_DESKTOP_API_BASE as string | undefined;
  const isotopeClient = createIsotopeClient(desktopApiBaseUrl?.trim() || null);
  const appState = createAppState(isotopeClient);
  const { snapshot, settings, initialize } = appState;
  let miniOpen = $state(false);
  let mainOpen = $state(false);
  let submitMode = $state<SubmitMode>('mock');
  let submitPreview = $state('No command submitted yet.');

  onMount(() => {
    void initialize();
  });

  async function submitMiniCommand(text: string) {
    const result = await isotopeClient.agentClient.submitMiniCommand(text);
    submitMode = result.mode;
    submitPreview = result.preview;
  }
</script>

<main class="min-h-screen bg-isotope-bg p-6 text-isotope-text">
  <div class="flex items-center justify-between">
    <div>
      <h1 class="text-xl font-semibold">Isotope Desktop</h1>
      <p class="mt-2 text-sm text-isotope-muted">Orb and MiniWindow thin loop.</p>
    </div>
    {#if $snapshot}
    <div class="flex items-center gap-3">
      <SourceBadge source={$snapshot.source} />
    <FloatingOrb
      activeActivity={$snapshot.activeActivity}
      activeAgent={$snapshot.activeAgent}
      quietMode={$settings?.quietMode ?? false}
      needsAttention={$snapshot.counts.needsAttention}
      onOpenMini={() => (miniOpen = true)}
    />
    </div>
    {/if}
  </div>

  {#if !$snapshot}
    <p class="mt-6 text-sm text-isotope-muted">Loading Supervisor snapshot...</p>
  {:else if miniOpen}
    <div class="mt-6">
      <MiniWindow
        snapshot={$snapshot}
        {submitMode}
        onSubmit={submitMiniCommand}
        onOpenMain={() => {
          mainOpen = true;
          miniOpen = false;
        }}
        onClose={() => (miniOpen = false)}
      />
      <p class="mt-2 text-xs text-isotope-muted">Submit preview: {submitPreview}</p>
    </div>
  {/if}

  {#if mainOpen}
    <p class="mt-6 rounded border border-isotope-line bg-white p-3 text-sm">
      MainWindow lands in Task 8.
    </p>
  {/if}
</main>
```

- [ ] **Step 5: Run checks**

Run:

```bash
cd apps/desktop
npm run check
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit MiniWindow**

Run:

```bash
git add apps/desktop/src/lib/components apps/desktop/src/routes/+page.svelte
git commit -m "feat(desktop): add mini window thin loop"
```

Expected: commit succeeds.

### Task 8: MainWindow ActivityTree And EventStream

**Files:**
- Create: `apps/desktop/src/lib/components/activity/tree.ts`
- Create: `apps/desktop/src/lib/components/activity/tree.test.ts`
- Create: `apps/desktop/src/lib/components/activity/ActivityTree.svelte`
- Create: `apps/desktop/src/lib/components/events/EventStream.svelte`
- Create: `apps/desktop/src/lib/components/common/RightDock.svelte`
- Create: `apps/desktop/src/lib/components/main/MainWindow.svelte`
- Modify: `apps/desktop/src/routes/+page.svelte`

- [ ] **Step 1: Add ActivityTree hierarchy helper tests**

Create `apps/desktop/src/lib/components/activity/tree.test.ts`:

```ts
import { describe, expect, test } from 'vitest';
import type { ActivityNode } from '../../contracts/isotope';
import { buildActivityTreeRows } from './tree';

const source = { kind: 'real' as const, label: 'test', backendRef: 'test://activity' };

describe('buildActivityTreeRows', () => {
  test('projects parentId and childIds into stable indented rows', () => {
    const nodes: ActivityNode[] = [
      { id: 'worker-2', kind: 'worker', title: 'Worker B', status: 'running', source, parentId: 'root', order: 1 },
      { id: 'root', kind: 'supervisor', title: 'Supervisor', status: 'running', source, childIds: ['worker-1', 'worker-2'], order: 0 },
      { id: 'worker-1', kind: 'worker', title: 'Worker A', status: 'done', source, parentId: 'root', order: 0 }
    ];

    expect(buildActivityTreeRows(nodes).map((row) => [row.node.id, row.depth])).toEqual([
      ['root', 0],
      ['worker-1', 1],
      ['worker-2', 1]
    ]);
  });
});
```

- [ ] **Step 2: Implement ActivityTree hierarchy helper**

Create `apps/desktop/src/lib/components/activity/tree.ts`:

```ts
import { sortActivityNodes, type ActivityNode } from '../../contracts/isotope';

export type ActivityTreeRow = {
  node: ActivityNode;
  depth: number;
};

export function buildActivityTreeRows(nodes: ActivityNode[]): ActivityTreeRow[] {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const childrenByParent = new Map<string, ActivityNode[]>();

  for (const node of nodes) {
    if (!node.parentId) continue;
    const children = childrenByParent.get(node.parentId) ?? [];
    children.push(node);
    childrenByParent.set(node.parentId, children);
  }

  const childIds = new Set(nodes.flatMap((node) => node.childIds ?? []));
  const roots = sortActivityNodes(nodes.filter((node) => !node.parentId && !childIds.has(node.id)));
  const rows: ActivityTreeRow[] = [];
  const visited = new Set<string>();

  function visit(node: ActivityNode, depth: number) {
    if (visited.has(node.id)) return;
    visited.add(node.id);
    rows.push({ node, depth });

    const explicitChildren = (node.childIds ?? [])
      .map((id) => byId.get(id))
      .filter((child): child is ActivityNode => Boolean(child));
    const parentChildren = childrenByParent.get(node.id) ?? [];
    const childMap = new Map([...explicitChildren, ...parentChildren].map((child) => [child.id, child]));
    for (const child of sortActivityNodes([...childMap.values()])) {
      visit(child, depth + 1);
    }
  }

  for (const root of roots) visit(root, 0);
  for (const node of sortActivityNodes(nodes)) visit(node, 0);
  return rows;
}
```

- [ ] **Step 3: Run ActivityTree helper test**

Run:

```bash
cd apps/desktop
npm run test -- src/lib/components/activity/tree.test.ts
```

Expected: PASS.

- [ ] **Step 4: Add ActivityTree**

Create `ActivityTree.svelte`:

```svelte
<script lang="ts">
  import type { ActivityNode } from '../../contracts/isotope';
  import SourceBadge from '../common/SourceBadge.svelte';
  import { buildActivityTreeRows } from './tree';

  let {
    nodes,
    selectedId = null,
    onSelect
  } = $props<{
    nodes: ActivityNode[];
    selectedId?: string | null;
    onSelect: (id: string) => void;
  }>();

  const rows = $derived(buildActivityTreeRows(nodes));
</script>

<nav class="space-y-1" aria-label="Activity tree">
  {#each rows as row (row.node.id)}
    <button
      type="button"
      class="flex w-full items-center justify-between gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-isotope-bg"
      class:bg-isotope-bg={selectedId === row.node.id}
      style={`padding-left: ${8 + row.depth * 14}px`}
      onclick={() => onSelect(row.node.id)}
    >
      <span class="min-w-0 truncate">{row.node.title}</span>
      <SourceBadge source={row.node.source} />
    </button>
  {/each}
</nav>
```

- [ ] **Step 5: Add EventStream**

Create `EventStream.svelte`:

```svelte
<script lang="ts">
  import { tick } from 'svelte';
  import type { IsotopeEvent } from '../../contracts/isotope';
  import SourceBadge from '../common/SourceBadge.svelte';

  let { events } = $props<{ events: IsotopeEvent[] }>();
  let scrollEl = $state<HTMLDivElement | null>(null);
  let followLatest = $state(true);
  let unseenCount = $state(0);
  let previousCount = 0;

  function nearBottom(element: HTMLDivElement): boolean {
    return element.scrollHeight - element.scrollTop - element.clientHeight < 24;
  }

  function handleScroll() {
    if (!scrollEl) return;
    followLatest = nearBottom(scrollEl);
    if (followLatest) unseenCount = 0;
  }

  async function scrollToLatest() {
    followLatest = true;
    unseenCount = 0;
    await tick();
    scrollEl?.scrollTo({ top: scrollEl.scrollHeight, behavior: 'smooth' });
  }

  $effect(() => {
    const count = events.length;
    if (count <= previousCount) {
      previousCount = count;
      return;
    }
    const added = count - previousCount;
    previousCount = count;
    if (followLatest) {
      void scrollToLatest();
    } else {
      unseenCount += added;
    }
  });
</script>

<section class="flex h-full flex-col">
  <header class="border-b border-isotope-line px-3 py-2 text-sm font-semibold">Events</header>
  <div bind:this={scrollEl} onscroll={handleScroll} class="min-h-0 flex-1 overflow-auto p-3">
    <div class="space-y-2">
      {#each events as event (event.id)}
        <article class="rounded border border-isotope-line bg-white p-2 text-sm">
          <div class="flex items-center justify-between gap-2">
            <strong class="truncate">{event.title}</strong>
            <SourceBadge source={event.source} />
          </div>
          <div class="mt-1 text-xs text-isotope-muted">{event.type} · {event.createdAt}</div>
          {#if event.summary}
            <p class="mt-1 text-xs text-isotope-muted">{event.summary}</p>
          {/if}
        </article>
      {/each}
    </div>
  </div>
  {#if unseenCount > 0}
    <button type="button" class="border-t border-isotope-line bg-white px-3 py-2 text-xs text-isotope-running" onclick={scrollToLatest}>
      {unseenCount} new events
    </button>
  {/if}
</section>
```

- [ ] **Step 6: Add RightDock and MainWindow**

Create `apps/desktop/src/lib/components/common/RightDock.svelte`:

```svelte
<script lang="ts">
  import type { ApprovalSummary, ArtifactSummary, IsotopeEvent } from '../../contracts/isotope';
  import EventStream from '../events/EventStream.svelte';
  import SourceBadge from './SourceBadge.svelte';

  let {
    events,
    approvals = [],
    artifacts = []
  } = $props<{
    events: IsotopeEvent[];
    approvals?: ApprovalSummary[];
    artifacts?: ArtifactSummary[];
  }>();
</script>

<aside class="grid h-full grid-rows-[1fr_auto] border-l border-isotope-line bg-isotope-bg">
  <EventStream {events} />
  <div class="grid gap-2 border-t border-isotope-line p-3 text-xs">
    <section class="rounded border border-isotope-line bg-white p-2">
      <div class="font-semibold">Approval summary</div>
      <div class="mt-1 text-isotope-muted">{approvals.length} approval items</div>
      {#each approvals as approval (approval.id)}
        <div class="mt-1 flex items-center justify-between gap-2">
          <span class="truncate">{approval.title}</span>
          <SourceBadge source={approval.source} />
        </div>
      {/each}
    </section>
    <section class="rounded border border-isotope-line bg-white p-2">
      <div class="font-semibold">Artifact summary</div>
      <div class="mt-1 text-isotope-muted">{artifacts.length} artifact items</div>
      {#each artifacts as artifact (artifact.id)}
        <div class="mt-1 flex items-center justify-between gap-2">
          <span class="truncate">{artifact.title}</span>
          <SourceBadge source={artifact.source} />
        </div>
      {/each}
    </section>
  </div>
</aside>
```

Create `apps/desktop/src/lib/components/main/MainWindow.svelte`:

```svelte
<script lang="ts">
  import type { IsotopeEvent, IsotopeSnapshot } from '../../contracts/isotope';
  import ActivityTree from '../activity/ActivityTree.svelte';
  import CommandComposer from '../common/CommandComposer.svelte';
  import RightDock from '../common/RightDock.svelte';
  import SourceBadge from '../common/SourceBadge.svelte';

  let {
    snapshot,
    events,
    selectedActivityId = null,
    onSelectActivity,
    onSubmit
  } = $props<{
    snapshot: IsotopeSnapshot;
    events: IsotopeEvent[];
    selectedActivityId?: string | null;
    onSelectActivity: (id: string) => void;
    onSubmit: (text: string) => void;
  }>();

  const selectedActivity = $derived(
    snapshot.activities.find((activity) => activity.id === selectedActivityId)
      ?? snapshot.activities[0]
      ?? null
  );
</script>

<section class="grid h-[720px] grid-cols-[280px_minmax(0,1fr)_360px] overflow-hidden rounded-panel border border-isotope-line bg-white shadow-xl">
  <aside class="border-r border-isotope-line bg-isotope-bg p-3">
    <div class="mb-3 flex items-center justify-between">
      <span class="text-sm font-semibold">ActivityTree</span>
      <SourceBadge source={snapshot.source} />
    </div>
    <ActivityTree nodes={snapshot.activities} selectedId={selectedActivityId} onSelect={onSelectActivity} />
  </aside>

  <main class="min-w-0 p-4">
    <div class="text-xs text-isotope-muted">Current activity</div>
    <h2 class="mt-1 text-xl font-semibold">{selectedActivity?.title ?? snapshot.activeGoal?.title ?? 'Isotope Supervisor'}</h2>
    <p class="mt-2 text-sm text-isotope-muted">
      {selectedActivity?.summary ?? snapshot.activeAgent?.title ?? 'No activity summary available.'}
    </p>
    <div class="mt-6">
      <CommandComposer placeholder="Message Supervisor" onSubmit={onSubmit} />
    </div>
  </main>

  <RightDock events={events} approvals={snapshot.approvals} artifacts={snapshot.artifacts} />
</section>
```

- [ ] **Step 7: Wire MainWindow into dev page**

Modify `apps/desktop/src/routes/+page.svelte` so clicking MiniWindow open main
renders MainWindow with the loaded snapshot and event stream. The source badges
show whether the data is `real`, `derived`, `mock`, or `replay_mock`.

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { createIsotopeClient } from '$lib/client/isotopeClient';
  import type { SubmitMode } from '$lib/client/agentClient';
  import FloatingOrb from '$lib/components/orb/FloatingOrb.svelte';
  import MiniWindow from '$lib/components/mini/MiniWindow.svelte';
  import MainWindow from '$lib/components/main/MainWindow.svelte';
  import SourceBadge from '$lib/components/common/SourceBadge.svelte';
  import { createAppState } from '$lib/stores/appState';

  const desktopApiBaseUrl = import.meta.env.VITE_ISOTOPE_DESKTOP_API_BASE as string | undefined;
  const isotopeClient = createIsotopeClient(desktopApiBaseUrl?.trim() || null);
  const appState = createAppState(isotopeClient);
  const { snapshot, events, settings, selectedActivityId, initialize } = appState;
  let miniOpen = $state(false);
  let mainOpen = $state(false);
  let submitMode = $state<SubmitMode>('mock');
  let submitPreview = $state('No command submitted yet.');

  onMount(() => {
    void initialize();
  });

  async function submitMiniCommand(text: string) {
    const result = await isotopeClient.agentClient.submitMiniCommand(text);
    submitMode = result.mode;
    submitPreview = result.preview;
  }
</script>

<main class="min-h-screen bg-isotope-bg p-6 text-isotope-text">
  <div class="flex items-center justify-between">
    <div>
      <h1 class="text-xl font-semibold">Isotope Desktop</h1>
      <p class="mt-2 text-sm text-isotope-muted">Thin desktop loop with typed mock events.</p>
    </div>
    {#if $snapshot}
    <div class="flex items-center gap-3">
      <SourceBadge source={$snapshot.source} />
    <FloatingOrb
      activeActivity={$snapshot.activeActivity}
      activeAgent={$snapshot.activeAgent}
      quietMode={$settings?.quietMode ?? false}
      needsAttention={$snapshot.counts.needsAttention}
      onOpenMini={() => (miniOpen = true)}
    />
    </div>
    {/if}
  </div>

  {#if !$snapshot}
    <p class="mt-6 text-sm text-isotope-muted">Loading Supervisor snapshot...</p>
  {:else if miniOpen}
    <div class="mt-6">
      <MiniWindow
        snapshot={$snapshot}
        {submitMode}
        onSubmit={submitMiniCommand}
        onOpenMain={() => {
          mainOpen = true;
          miniOpen = false;
        }}
        onClose={() => (miniOpen = false)}
      />
      <p class="mt-2 text-xs text-isotope-muted">Submit preview: {submitPreview}</p>
    </div>
  {/if}

  {#if mainOpen}
    <div class="mt-6">
      <MainWindow
        snapshot={$snapshot}
        events={$events}
        selectedActivityId={$selectedActivityId}
        onSelectActivity={(id) => selectedActivityId.set(id)}
        onSubmit={submitMiniCommand}
      />
    </div>
  {/if}
</main>
```

- [ ] **Step 8: Run checks**

Run:

```bash
cd apps/desktop
npm run check
npm run test -- src/lib/components/activity/tree.test.ts
npm run build
```

Expected: PASS.

Manual browser acceptance in `npm run dev`:

```text
ActivityTree renders parent/child indentation instead of a flat list.
EventStream starts at latest event.
Scrolling upward pauses automatic follow.
Adding an event while paused shows the new-events button.
Clicking the new-events button returns to the bottom.
```

- [ ] **Step 9: Commit MainWindow**

Run:

```bash
git add apps/desktop/src/lib/components apps/desktop/src/routes/+page.svelte
git commit -m "feat(desktop): add main window activity view"
```

Expected: commit succeeds.

### Task 9: Tauri Window Commands And Position State

**Files:**
- Create: `apps/desktop/src-tauri/src/window_state.rs`
- Create: `apps/desktop/src-tauri/src/window_commands.rs`
- Create: `apps/desktop/src-tauri/src/shortcuts.rs`
- Modify: `apps/desktop/src-tauri/src/main.rs`
- Modify: `apps/desktop/src/lib/client/windowClient.ts`
- Modify: `apps/desktop/src/routes/+page.svelte`

- [ ] **Step 1: Add Rust window state tests**

Create `apps/desktop/src-tauri/src/window_state.rs`:

```rust
use std::fs;
use std::path::Path;

use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct WindowPosition {
    pub x: i32,
    pub y: i32,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct SavedWindowState {
    pub orb: Option<WindowPosition>,
    pub mini: Option<WindowPosition>,
    pub quiet_mode: bool,
    pub reduced_motion: bool,
}

impl Default for SavedWindowState {
    fn default() -> Self {
        Self {
            orb: None,
            mini: None,
            quiet_mode: false,
            reduced_motion: false,
        }
    }
}

pub fn valid_position(position: &WindowPosition) -> bool {
    position.x > -10000 && position.y > -10000 && position.x < 20000 && position.y < 20000
}

pub fn load_window_state(path: &Path) -> SavedWindowState {
    let Ok(raw) = fs::read_to_string(path) else {
        return SavedWindowState::default();
    };
    serde_json::from_str(&raw).unwrap_or_default()
}

pub fn save_window_state(path: &Path, state: &SavedWindowState) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let raw = serde_json::to_string_pretty(state).map_err(|error| error.to_string())?;
    fs::write(path, raw).map_err(|error| error.to_string())
}

pub fn update_position(state: &mut SavedWindowState, label: &str, position: WindowPosition) {
    if !valid_position(&position) {
        return;
    }
    match label {
        "orb" => state.orb = Some(position),
        "mini" => state.mini = Some(position),
        _ => {}
    }
}

pub fn mini_open_position(state: &SavedWindowState) -> WindowPosition {
    if let Some(position) = &state.mini {
        if valid_position(position) {
            return position.clone();
        }
    }
    if let Some(orb) = &state.orb {
        if valid_position(orb) {
            return WindowPosition { x: orb.x + 84, y: orb.y };
        }
    }
    WindowPosition { x: 120, y: 120 }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_impossible_position() {
        assert!(!valid_position(&WindowPosition { x: -20000, y: 0 }));
        assert!(valid_position(&WindowPosition { x: 120, y: 80 }));
    }

    #[test]
    fn mini_position_prefers_saved_mini_then_orb_fallback() {
        let mut state = SavedWindowState::default();
        state.orb = Some(WindowPosition { x: 50, y: 60 });
        assert_eq!(mini_open_position(&state), WindowPosition { x: 134, y: 60 });
        state.mini = Some(WindowPosition { x: 300, y: 320 });
        assert_eq!(mini_open_position(&state), WindowPosition { x: 300, y: 320 });
    }
}
```

- [ ] **Step 2: Run Rust tests**

Run:

```bash
cd apps/desktop/src-tauri
cargo test
```

Expected: PASS.

- [ ] **Step 3: Add dynamic Tauri window commands**

Create `window_commands.rs` with Tauri commands:

```rust
use serde::Deserialize;
use tauri::{LogicalPosition, LogicalSize, Manager, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

use crate::window_state::{
    load_window_state, mini_open_position, save_window_state, update_position, SavedWindowState,
    WindowPosition,
};

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ShowWindowRequest {
    pub label: String,
    pub focus: Option<bool>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SaveWindowPositionRequest {
    pub label: String,
    pub x: i32,
    pub y: i32,
}

#[tauri::command]
pub async fn show_window(app: tauri::AppHandle, request: ShowWindowRequest) -> Result<(), String> {
    show_or_create_window(&app, &request.label, request.focus.unwrap_or(false))
}

#[tauri::command]
pub async fn hide_window(app: tauri::AppHandle, label: String) -> Result<(), String> {
    let window = app.get_webview_window(&label).ok_or_else(|| format!("unknown window: {label}"))?;
    window.hide().map_err(|error| error.to_string())?;
    Ok(())
}

#[tauri::command]
pub async fn save_window_position(
    app: tauri::AppHandle,
    request: SaveWindowPositionRequest,
) -> Result<(), String> {
    let path = state_path(&app)?;
    let mut state = load_window_state(&path);
    update_position(
        &mut state,
        &request.label,
        WindowPosition {
            x: request.x,
            y: request.y,
        },
    );
    save_window_state(&path, &state)
}

pub fn show_or_create_window(app: &tauri::AppHandle, label: &str, focus: bool) -> Result<(), String> {
    let window = match app.get_webview_window(label) {
        Some(window) => window,
        None => create_window(app, label)?,
    };
    window.show().map_err(|error| error.to_string())?;
    if focus {
        window.set_focus().map_err(|error| error.to_string())?;
    }
    Ok(())
}

fn create_window(app: &tauri::AppHandle, label: &str) -> Result<WebviewWindow, String> {
    let state = load_window_state(&state_path(app)?);
    let builder = WebviewWindowBuilder::new(
        app,
        label,
        WebviewUrl::App(format!("index.html?window={label}").into()),
    )
    .visible(false)
    .decorations(label == "main")
    .transparent(label != "main")
    .always_on_top(label != "main");

    let builder = match label {
        "orb" => builder
            .title("Isotope Orb")
            .inner_size(LogicalSize::new(72.0, 72.0))
            .resizable(false),
        "mini" => builder
            .title("Isotope Mini")
            .inner_size(LogicalSize::new(380.0, 520.0))
            .min_inner_size(LogicalSize::new(320.0, 360.0))
            .position({
                let position = mini_open_position(&state);
                LogicalPosition::new(position.x as f64, position.y as f64)
            })
            .resizable(true),
        "main" => builder
            .title("Isotope")
            .inner_size(LogicalSize::new(1180.0, 760.0))
            .min_inner_size(LogicalSize::new(860.0, 560.0))
            .resizable(true),
        other => return Err(format!("unknown window: {other}")),
    };

    builder.build().map_err(|error| error.to_string())
}

fn state_path(app: &tauri::AppHandle) -> Result<std::path::PathBuf, String> {
    let dir = app
        .path()
        .app_config_dir()
        .map_err(|error| error.to_string())?;
    Ok(dir.join("window-state.json"))
}
```

Create `apps/desktop/src-tauri/src/shortcuts.rs`:

```rust
use crate::window_commands::show_or_create_window;

pub fn register_global_shortcuts(app: &tauri::AppHandle) -> Result<(), String> {
    use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

    let shortcut = Shortcut::new(Some(Modifiers::ALT | Modifiers::SHIFT), Code::Space);
    app.global_shortcut()
        .on_shortcut(shortcut, move |app, _shortcut, event| {
            if event.state == ShortcutState::Pressed {
                let _ = show_or_create_window(app, "mini", true);
            }
        })
        .map_err(|error| error.to_string())?;
    Ok(())
}
```

Modify `apps/desktop/src-tauri/src/main.rs`:

```rust
mod shortcuts;
mod window_commands;
mod window_state;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            window_commands::show_window,
            window_commands::hide_window,
            window_commands::save_window_position
        ])
        .setup(|app| {
            if let Err(error) = shortcuts::register_global_shortcuts(&app.handle()) {
                eprintln!("failed to register global shortcuts: {error}");
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("failed to run Isotope desktop");
}
```

- [ ] **Step 4: Update frontend windowClient to use Tauri invoke when available**

Modify `windowClient.ts`:

```ts
import { invoke } from '@tauri-apps/api/core';

export type WindowKind = 'orb' | 'mini' | 'main';

export type WindowSettings = {
  orbOpacity: number;
  miniOpacity: number;
  quietMode: boolean;
  reducedMotion: boolean;
};

export type WindowClient = {
  open(kind: WindowKind, options?: { focus?: boolean }): Promise<void>;
  close(kind: WindowKind): Promise<void>;
  savePosition(kind: WindowKind, position: { x: number; y: number }): Promise<void>;
  loadSettings(): Promise<WindowSettings>;
};

async function tauriInvoke(command: string, args: Record<string, unknown>) {
  if (typeof window === 'undefined' || !('__TAURI_INTERNALS__' in window)) return;
  return invoke(command, args);
}

export function createWindowClient(): WindowClient {
  return {
    async open(kind, options) {
      await tauriInvoke('show_window', {
        request: {
          label: kind,
          focus: options?.focus ?? false
        }
      });
    },
    async close(kind) {
      await tauriInvoke('hide_window', { label: kind });
    },
    async savePosition(kind, position) {
      await tauriInvoke('save_window_position', {
        request: {
          label: kind,
          x: Math.round(position.x),
          y: Math.round(position.y)
        }
      });
    },
    async loadSettings() {
      return { orbOpacity: 0.92, miniOpacity: 0.96, quietMode: false, reducedMotion: false };
    }
  };
}
```

Only explicit user actions such as global shortcut open or composer activation
should pass `focus: true`; attention/approval state changes must not steal focus.

- [ ] **Step 5: Add window-specific frontend routing**

Modify `apps/desktop/src/routes/+page.svelte` so Tauri windows opened with
`index.html?window=orb`, `index.html?window=mini`, or `index.html?window=main`
render only their own surface. Add this state near the existing page state:

```svelte
<script lang="ts">
  type WindowSurface = 'dev' | 'orb' | 'mini' | 'main';
  let windowSurface = $state<WindowSurface>('dev');

  function readWindowSurface(): WindowSurface {
    const value = new URLSearchParams(window.location.search).get('window');
    if (value === 'orb' || value === 'mini' || value === 'main') return value;
    return 'dev';
  }

  onMount(() => {
    windowSurface = readWindowSurface();
    void initialize();
  });
</script>
```

Then guard the rendered surfaces:

```svelte
{#if $snapshot && (windowSurface === 'orb' || windowSurface === 'dev')}
  <FloatingOrb
    activeActivity={$snapshot.activeActivity}
    activeAgent={$snapshot.activeAgent}
    quietMode={$settings?.quietMode ?? false}
    needsAttention={$snapshot.counts.needsAttention}
    onOpenMini={() => {
      miniOpen = true;
      void isotopeClient.windowClient.open('mini', { focus: true });
    }}
  />
{/if}

{#if $snapshot && (windowSurface === 'mini' || (windowSurface === 'dev' && miniOpen))}
  <MiniWindow
    snapshot={$snapshot}
    {submitMode}
    onSubmit={submitMiniCommand}
    onOpenMain={() => {
      mainOpen = true;
      miniOpen = false;
      void isotopeClient.windowClient.open('main', { focus: true });
    }}
    onClose={() => {
      miniOpen = false;
      void isotopeClient.windowClient.close('mini');
    }}
  />
{/if}

{#if $snapshot && (windowSurface === 'main' || (windowSurface === 'dev' && mainOpen))}
  <MainWindow
    snapshot={$snapshot}
    events={$events}
    selectedActivityId={$selectedActivityId}
    onSelectActivity={(id) => selectedActivityId.set(id)}
    onSubmit={submitMiniCommand}
  />
{/if}
```

Do not let the `orb` Tauri window render the full dev page. Browser dev mode may
still render all surfaces through `windowSurface === 'dev'`.

- [ ] **Step 6: Verify custom invoke permissions in Tauri runtime**

Run:

```bash
cd apps/desktop
npm run tauri dev
```

Manual runtime checks:

```text
windowClient.open('mini', { focus: true }) creates or shows the mini window.
No "command not allowed" or "permission denied" error appears.
Alt+Shift+Space opens MiniWindow, not MainWindow.
The mini window URL includes ?window=mini and renders only MiniWindow.
The orb window URL includes ?window=orb and renders only FloatingOrb.
```

If custom invoke is denied, update `src-tauri/capabilities/default.json` or add
the generated custom command permission required by Tauri v2, then rerun this
manual check. Do not mark Task 9 done on `cargo test` / `npm build` alone.

- [ ] **Step 7: Run checks**

Run:

```bash
cd apps/desktop/src-tauri
cargo test
cd ..
npm run check
npm run build
```

Expected: PASS.

- [ ] **Step 8: Commit window commands**

Run:

```bash
git add apps/desktop/src-tauri apps/desktop/src/lib/client/windowClient.ts
git commit -m "feat(desktop): add Tauri window commands"
```

Expected: commit succeeds.

### Task 10: Backend Gap Report Pass

**Files:**
- Create: `docs/superpowers/plans/backend-gaps/2026-05-27-desktop-frontend-backend-gaps.md`

- [ ] **Step 1: Create Backend Gap report**

Create `docs/superpowers/plans/backend-gaps/2026-05-27-desktop-frontend-backend-gaps.md`:

```markdown
# Desktop Frontend Backend Gaps

Date: 2026-05-27

## Summary

This report lists backend contracts the desktop MVP needs that are not fully available yet.

## Gap 1: MiniWindow submit path

Frontend needs:
- A real MiniWindow -> Supervisor submit path with a low-sensitive response preview.

Current backend mismatch:
- The desktop MVP can load a real Supervisor snapshot, but the MiniWindow command submit path is still marked `mock` or `disabled`.

Proposed contract:
- `POST /desktop/supervisor/input` or Tauri invoke bridge returning `{ mode: "real", preview: string, activityRef?: ResourceRef }`.

Blocking level:
- partial for MVP, blocking for target real interaction acceptance.

Temporary mock boundary:
- UI may show mock submit preview, but mock reply cannot count as real interaction.

## Gap 2: General agent event stream

Frontend needs:
- `GET /desktop/events?cursor=&limit=` and `GET /desktop/events/stream?cursor=` using `IsotopeEvent`.

Current backend mismatch:
- Existing Supervisor `/events` is bell/refresh oriented and existing runtime SSE route is deferred for run events.

Proposed contract:
- Desktop event replay and SSE adapter with the cursor rules from the design spec.
- Do not cast existing bell `/events` responses as `EventReplayResponse`.

Blocking level:
- partial for MVP, blocking for real-time phase.

Temporary mock boundary:
- Use `derived` or `replay_mock` events only when source is visible.

## Gap 3: Desktop API base URL discovery

Frontend needs:
- A reliable desktop API base URL for `GET /desktop/snapshot`, `/desktop/events`, and `/desktop/events/stream`.

Current backend mismatch:
- The first implementation uses `VITE_ISOTOPE_DESKTOP_API_BASE`; Tauri/Rust does not yet start or discover the Supervisor dashboard server.

Proposed contract:
- Tauri invoke `get_desktop_api_base_url` or `ensure_supervisor_server` returns `{ baseUrl: "http://127.0.0.1:<port>" }`.

Blocking level:
- blocking for real snapshot MVP acceptance when the env var is absent.

Temporary mock boundary:
- If no base URL is configured, UI may show mock source but must mark real snapshot acceptance as failed.
```

- [ ] **Step 2: Add any gaps discovered during implementation**

Append concrete gaps for:

- Activity projection if only active goal can be real.
- Artifact summary if no Supervisor artifact summary is readable.
- Approval if decision request cannot be mapped cleanly.
- Window overlay if Tauri behavior differs on Windows.

Do not add vague items. Each gap must include needs, mismatch, proposed contract, blocking level, and mock boundary.

- [ ] **Step 3: Verify no mock is unlabeled**

Run:

```bash
rg -n "mock|replay_mock|derived" apps/desktop/src docs/superpowers/plans/backend-gaps/2026-05-27-desktop-frontend-backend-gaps.md
```

Expected: every mock/derived path has a visible source or gap entry.

- [ ] **Step 4: Commit gap report**

Run:

```bash
git add docs/superpowers/plans/backend-gaps/2026-05-27-desktop-frontend-backend-gaps.md
git commit -m "docs(desktop): record frontend backend gaps"
```

Expected: commit succeeds.

### Task 11: Verification Pass

**Files:**
- Modify only if verification finds small docs updates:
  - `docs/superpowers/plans/backend-gaps/2026-05-27-desktop-frontend-backend-gaps.md`

- [ ] **Step 1: Run frontend checks**

Run:

```bash
cd apps/desktop
npm run test
npm run check
npm run build
```

Expected:

```text
PASS
svelte-check found 0 errors and 0 warnings
build completed
```

- [ ] **Step 2: Run Rust checks**

Run:

```bash
cd apps/desktop/src-tauri
cargo test
cargo check
```

Expected: PASS.

- [ ] **Step 3: Run Python targeted checks**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/integration/supervisor/test_supervisor_desktop_snapshot.py tests/integration/supervisor/test_supervisor_state_projection.py -q
```

Expected: PASS.

- [ ] **Step 4: Run docs and repo sanity checks**

Run:

```bash
git diff --check
git status --short --branch
```

Expected:

```text
git diff --check exits 0
## feature/desktop-frontend
```

The worktree may show committed branch ahead of origin; there must be no unrelated dirty files.

- [ ] **Step 5: Write implementation summary**

Prepare a short summary with:

- What real backend data is connected.
- Which submit path mode is active: `real`, `mock`, or `disabled`.
- Which event stream mode is active: `real`, `derived`, or `replay_mock`.
- Backend gaps recorded.
- Verification commands and results.

- [ ] **Step 6: Commit any final docs-only adjustments**

If Task 11 produced only docs updates:

```bash
git add docs/superpowers/plans/backend-gaps/2026-05-27-desktop-frontend-backend-gaps.md
git commit -m "docs(desktop): update verification notes"
```

If no files changed, do not create an empty commit.

## Review Checklist

Before merging or asking for review:

- [ ] `apps/desktop` exists and builds.
- [ ] Components do not call raw `fetch()` or `invoke()` outside client adapters.
- [ ] `GET /desktop/snapshot` exists and returns `IsotopeSnapshot`.
- [ ] Snapshot includes real Supervisor basic info through `activeAgent`, `agents[0]`, and a supervisor/root `ActivityNode`.
- [ ] `+page.svelte` initializes through `createAppState(createIsotopeClient(desktopApiBaseUrl))`, not direct `mockSnapshot`.
- [ ] `VITE_ISOTOPE_DESKTOP_API_BASE` or a reviewed Tauri invoke supplies the real Supervisor API base URL.
- [ ] MiniWindow shows real Supervisor snapshot or clearly fails the MVP.
- [ ] MiniWindow submit mode is visible as `real`, `mock`, or `disabled`.
- [ ] MiniWindow starts with an enabled composer unless the submit path is explicitly disabled.
- [ ] Mock replies are not described as real interaction.
- [ ] EventStream renders only typed `IsotopeEvent`.
- [ ] Event replay uses `/desktop/events`, not existing bell `/events`.
- [ ] EventStream follow/latest pause and new-event hint behavior passes manual acceptance.
- [ ] `payloadPreview` is debug/detail only.
- [ ] `DataSourceInfo.kind` is present on mock, replay_mock, and derived data.
- [ ] Derived data has `backendRef` or `sourceRef`.
- [ ] ActivityTree uses ActivityTree / AgentTree language, not SessionTree as the contract.
- [ ] ActivityTree renders parent/child hierarchy from `parentId` / `childIds`, not a flat list.
- [ ] Tauri `orb`, `mini`, and `main` windows route to window-specific UI.
- [ ] Alt+Shift+Space opens MiniWindow.
- [ ] MiniWindow uses saved position and falls back near orb when the saved position is invalid.
- [ ] Tauri runtime verifies custom invoke permissions, not only Rust/frontend builds.
- [ ] Windows overlay spike results are recorded separately and do not block MVP.
- [ ] Backend gaps are concrete and actionable.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-27-desktop-frontend-implementation-plan.md`. Two execution options:

1. Subagent-Driven (recommended) - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. Inline Execution - execute tasks in this session using executing-plans, batch execution with checkpoints.

Recommended choice: Subagent-Driven, but do not execute the whole plan in one pass.
First dispatch only Task -1 through Task 2:

1. Persist reviewed docs.
2. Create the worktree and run toolchain preflight.
3. Build the corrected Tauri/Svelte scaffold.
4. Add the frontend contracts and cursor helper tests.

Review that checkpoint before assigning the snapshot adapter, UI, Tauri window,
and Backend Gap tasks. This keeps Node/Svelte, Rust/Tauri, Python/Supervisor,
and Windows overlay risks from mixing into one hard-to-review batch.
