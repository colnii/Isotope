# Desktop Suprematist Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first-round Desktop Suprematist visual slice for the `主管聊天` golden path without changing backend contracts or merging to `main`.

**Architecture:** Add a stable visual token layer in Tailwind/CSS while preserving existing `isotope-*` aliases, then restyle the main desktop chat components around a conversation-first layout. Keep capability cards, approval cards, screenshot artifact actions, SSE, and model-agency behavior unchanged; all implementation happens on an isolated feature branch that stops before merge.

**Tech Stack:** Svelte 5, TypeScript, Tailwind CSS 3.4, Vitest source/contract tests, Vite/SvelteKit desktop app, existing desktop observe/CDP scripts.

---

## Execution Setup

Run implementation in an isolated worktree because this is a non-trivial frontend redesign.

- [ ] **Step 1: Create the implementation worktree**

```bash
git fetch origin
git worktree add .worktrees/desktop-suprematist-chat -b feat/desktop-suprematist-chat origin/main
cd .worktrees/desktop-suprematist-chat
```

Expected: `git status --short --branch` shows `## feat/desktop-suprematist-chat...origin/main` with no file changes.

- [ ] **Step 2: Install desktop dependencies if missing**

```bash
cd apps/desktop
npm install
cd ../..
```

Expected: commands exit `0`. If `node_modules` already exists and is current, this may report everything up to date.

- [ ] **Step 3: Record the no-merge stop rule for this branch**

At the end of implementation, push the feature branch and stop. Do not merge, fast-forward, or cherry-pick into `main`.

```bash
git status --short --branch
git push -u origin feat/desktop-suprematist-chat
```

Expected final state before user review: feature branch pushed, `main` untouched by implementation changes.

## File Structure

Modify these first-round files:

- `apps/desktop/tailwind.config.ts`: extend the `isotope` color system with canvas/paper/ink/status tokens while keeping existing aliases.
- `apps/desktop/src/app.css`: set the warm canvas background, default text color, focus ring, and base control styling.
- `apps/desktop/src/lib/window/windowSurface.ts`: switch dev/main surfaces to the new canvas token while preserving transparent Tauri window behavior.
- `apps/desktop/src/routes/+page.svelte`: restyle the top desktop mode switch so it does not look detached from the new visual system.
- `apps/desktop/src/lib/components/main/MainWindowShell.svelte`: give the chat shell the new canvas frame.
- `apps/desktop/src/lib/components/main/ConversationWorkspace.svelte`: restyle header, empty state, messages, approvals, and composer area.
- `apps/desktop/src/lib/components/main/CapacityCallCard.svelte`: restyle capability cards, status marks, artifact actions, and modals.
- `apps/desktop/src/lib/components/main/CapacityCallDetails.svelte`: ensure long details remain bounded and readable.
- `apps/desktop/src/lib/components/common/CommandComposer.svelte`: restyle the bottom composer.

Modify or add these tests:

- `apps/desktop/src/lib/view/desktopVisualTokens.test.ts`: new source-level guard for required token names and legacy aliases.
- `apps/desktop/src/lib/window/windowSurface.test.ts`: update expected dev background token.
- `apps/desktop/src/lib/components/main/ConversationWorkspace.test.ts`: add source guards for approval actions, visual status marks, and message ordering.
- `apps/desktop/src/lib/components/main/CapacityCallCard.test.ts`: new source guard for folded capability card affordances and preserved artifact actions.

Do not modify backend Python files in this first slice.

## Task 1: Visual Token Foundation

**Files:**
- Modify: `apps/desktop/tailwind.config.ts`
- Modify: `apps/desktop/src/app.css`
- Create: `apps/desktop/src/lib/view/desktopVisualTokens.test.ts`

- [ ] **Step 1: Write token guard tests**

Create `apps/desktop/src/lib/view/desktopVisualTokens.test.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

describe('desktop suprematist visual tokens', () => {
  test('defines warm canvas, ink, and primary suprematist accents', () => {
    const source = readFileSync(join(process.cwd(), 'tailwind.config.ts'), 'utf8');

    for (const token of [
      'canvas',
      'paper',
      'ink',
      'muted',
      'line',
      'red',
      'yellow',
      'blue',
      'green'
    ]) {
      expect(source).toContain(`${token}:`);
    }
  });

  test('keeps legacy aliases so existing components can migrate incrementally', () => {
    const source = readFileSync(join(process.cwd(), 'tailwind.config.ts'), 'utf8');

    for (const legacyAlias of ['bg:', 'panel:', 'text:', 'attention:', 'running:', 'done:']) {
      expect(source).toContain(legacyAlias);
    }
  });

  test('keeps global CSS free of gradients and texture backgrounds', () => {
    const source = readFileSync(join(process.cwd(), 'src/app.css'), 'utf8');

    expect(source).not.toContain('linear-gradient');
    expect(source).not.toContain('radial-gradient');
    expect(source).not.toContain('background-image');
  });
});
```

- [ ] **Step 2: Run the token test and confirm it fails**

```bash
cd apps/desktop
npm run test -- src/lib/view/desktopVisualTokens.test.ts
```

Expected: FAIL because `desktopVisualTokens.test.ts` expects tokens that are not all present yet.

- [ ] **Step 3: Extend Tailwind tokens**

Modify `apps/desktop/tailwind.config.ts` so the `isotope` color object has this shape:

```ts
colors: {
  isotope: {
    canvas: '#f6f1e7',
    paper: '#fffaf0',
    panel: '#fffdf7',
    ink: '#171717',
    text: '#171717',
    muted: '#706a5f',
    line: '#d8ccba',
    lineStrong: '#171717',
    red: '#d7261f',
    yellow: '#edc531',
    blue: '#1657d6',
    green: '#16784b',
    bg: '#f6f1e7',
    attention: '#d7261f',
    running: '#1657d6',
    done: '#16784b',
    warning: '#b7791f',
    error: '#b42318'
  }
},
borderRadius: {
  panel: '6px',
  tool: '8px'
}
```

Keep the existing `content` and `plugins` entries unchanged.

- [ ] **Step 4: Update global CSS**

Modify `apps/desktop/src/app.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  color-scheme: light;
  font-family:
    "Aptos",
    "Segoe UI",
    ui-sans-serif,
    system-ui,
    -apple-system,
    BlinkMacSystemFont,
    sans-serif;
  background: #f6f1e7;
}

body {
  margin: 0;
  background: transparent;
  color: #171717;
}

button,
input,
textarea {
  font: inherit;
}

button:focus-visible,
input:focus-visible,
textarea:focus-visible {
  outline: 2px solid #1657d6;
  outline-offset: 2px;
}
```

- [ ] **Step 5: Run token tests**

```bash
cd apps/desktop
npm run test -- src/lib/view/desktopVisualTokens.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit token foundation**

```bash
git add apps/desktop/tailwind.config.ts apps/desktop/src/app.css apps/desktop/src/lib/view/desktopVisualTokens.test.ts
git commit -m "style(desktop): add suprematist visual tokens"
```

## Task 2: Desktop Surface And Mode Switch

**Files:**
- Modify: `apps/desktop/src/lib/window/windowSurface.ts`
- Modify: `apps/desktop/src/lib/window/windowSurface.test.ts`
- Modify: `apps/desktop/src/routes/+page.svelte`
- Test: `apps/desktop/src/routes/pageAgentWorkspace.test.ts`

- [ ] **Step 1: Update surface tests**

Modify `apps/desktop/src/lib/window/windowSurface.test.ts`:

```ts
test('keeps the browser dev shell padded and on the warm canvas', () => {
  expect(buildPageSurfaceClass('dev')).toContain('p-6');
  expect(buildPageSurfaceClass('dev')).toContain('bg-isotope-canvas');
});
```

Keep the other tests in the file unchanged.

- [ ] **Step 2: Run the surface test and confirm it fails**

```bash
cd apps/desktop
npm run test -- src/lib/window/windowSurface.test.ts
```

Expected: FAIL because `buildPageSurfaceClass('dev')` still contains `bg-isotope-bg`.

- [ ] **Step 3: Update surface classes**

Modify `apps/desktop/src/lib/window/windowSurface.ts`:

```ts
export function buildPageSurfaceClass(surface: DesktopWindowSurface): string {
  const base = 'text-isotope-text';
  if (surface === 'dev') return `${base} min-h-screen bg-isotope-canvas p-6`;
  if (surface === 'main') return `${base} min-h-screen bg-transparent p-0`;
  return `${base} h-screen w-screen overflow-hidden bg-transparent p-0`;
}

export function buildMiniWindowSurfaceClass(surface: ComponentSurface): string {
  const base = 'z-20 border border-isotope-line bg-isotope-panel p-3 shadow-xl';
  return surface === 'dev'
    ? `${base} fixed bottom-28 right-5 w-[min(360px,calc(100vw-2.5rem))]`
    : `${base} box-border h-screen w-screen overflow-hidden`;
}
```

- [ ] **Step 4: Restyle the mode switch without changing behavior**

In `apps/desktop/src/routes/+page.svelte`, replace both duplicated fixed mode switch button groups with this class pattern:

```svelte
<div class="fixed right-4 top-4 z-10 flex overflow-hidden border border-isotope-line bg-isotope-panel shadow-[4px_4px_0_#171717]">
  <button
    class={[
      'px-3 py-1.5 text-xs font-semibold',
      desktopMode === 'chat'
        ? 'bg-isotope-red text-white'
        : 'bg-isotope-panel text-isotope-muted hover:text-isotope-ink'
    ]}
    type="button"
    onclick={() => (desktopMode = 'chat')}
  >
    主管聊天
  </button>
  <button
    class={[
      'border-l border-isotope-line px-3 py-1.5 text-xs font-semibold',
      desktopMode === 'agent-workspace'
        ? 'bg-isotope-blue text-white'
        : 'bg-isotope-panel text-isotope-muted hover:text-isotope-ink'
    ]}
    type="button"
    onclick={() => (desktopMode = 'agent-workspace')}
  >
    智能体群聊
  </button>
</div>
```

Do not change the `desktopMode` state, `AgentWorkspaceShell` wiring, or snapshot loading branches.

- [ ] **Step 5: Run route and surface tests**

```bash
cd apps/desktop
npm run test -- src/lib/window/windowSurface.test.ts src/routes/pageAgentWorkspace.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit surface changes**

```bash
git add apps/desktop/src/lib/window/windowSurface.ts apps/desktop/src/lib/window/windowSurface.test.ts apps/desktop/src/routes/+page.svelte
git commit -m "style(desktop): update desktop surfaces"
```

## Task 3: Conversation Workspace Shell

**Files:**
- Modify: `apps/desktop/src/lib/components/main/MainWindowShell.svelte`
- Modify: `apps/desktop/src/lib/components/main/ConversationWorkspace.svelte`
- Modify: `apps/desktop/src/lib/components/main/ConversationWorkspace.test.ts`

- [ ] **Step 1: Add source guards for conversation visual structure**

Append this test to `apps/desktop/src/lib/components/main/ConversationWorkspace.test.ts`:

```ts
test('keeps the suprematist conversation structure without hiding approvals', () => {
  const path = join(process.cwd(), 'src/lib/components/main/ConversationWorkspace.svelte');
  const source = readFileSync(path, 'utf8');

  expect(source).toContain('isotope-composition-mark');
  expect(source).toContain('bg-isotope-canvas');
  expect(source).toContain('bg-isotope-paper');
  expect(source).toContain('border-isotope-line');
  expect(source).toContain('批准');
  expect(source).toContain('拒绝');
  expect(source).toContain('onResolveApproval');
});
```

- [ ] **Step 2: Run the conversation test and confirm it fails**

```bash
cd apps/desktop
npm run test -- src/lib/components/main/ConversationWorkspace.test.ts
```

Expected: FAIL because the current component does not contain `isotope-composition-mark` or the new canvas/paper tokens.

- [ ] **Step 3: Update the main shell background**

Modify `apps/desktop/src/lib/components/main/MainWindowShell.svelte` section class:

```svelte
<section
  class="min-h-screen bg-isotope-canvas text-isotope-text"
  aria-label="Isotope AI 对话"
>
```

Do not change props or derived values.

- [ ] **Step 4: Restyle `ConversationWorkspace` outer frame and header**

In `apps/desktop/src/lib/components/main/ConversationWorkspace.svelte`, change the outer section and header to this structure:

```svelte
<section class="flex min-h-screen min-w-0 flex-col bg-isotope-canvas" aria-label="Conversation workspace">
  <header class="relative overflow-hidden border-b border-isotope-line bg-isotope-panel px-7 py-5">
    <div class="pointer-events-none absolute right-7 top-4 isotope-composition-mark h-12 w-24" aria-hidden="true">
      <span class="absolute right-0 top-0 h-3 w-12 bg-isotope-ink"></span>
      <span class="absolute right-14 top-2 h-8 w-8 rotate-[-8deg] bg-isotope-red"></span>
      <span class="absolute right-9 top-8 h-3 w-12 bg-isotope-blue"></span>
      <span class="absolute right-2 top-7 h-5 w-5 bg-isotope-yellow"></span>
    </div>
    <div class="relative flex items-center justify-between gap-4 pr-28">
      <div class="min-w-0">
        <div class="text-xs font-semibold uppercase text-isotope-muted">{eyebrow}</div>
        <h1 class="mt-1 truncate text-xl font-semibold text-isotope-ink">{title}</h1>
      </div>
      {#if subtitle}
        <div class="shrink-0 border border-isotope-line bg-isotope-paper px-2 py-1 text-xs text-isotope-muted">
          {subtitle}
        </div>
      {/if}
    </div>
  </header>
```

The `pr-28` prevents status text from overlapping the geometric mark.

- [ ] **Step 5: Restyle empty state, message stream, and footer**

Keep the existing Svelte conditions and loops. Change class groups to use:

```svelte
<div class="min-h-0 flex flex-1 flex-col overflow-y-auto px-7 py-6" aria-live="polite">
```

For the assistant avatar:

```svelte
<div class="grid h-8 w-8 shrink-0 place-items-center border border-isotope-line bg-isotope-yellow text-xs font-semibold text-isotope-ink">
  AI
</div>
```

For assistant message containers:

```ts
'max-w-[min(82%,40rem)] border-isotope-line bg-isotope-paper text-isotope-text shadow-[4px_4px_0_rgba(23,23,23,0.08)]'
```

For user message containers:

```ts
'max-w-[min(72%,32rem)] border-isotope-blue bg-isotope-blue text-white shadow-[4px_4px_0_rgba(23,23,23,0.18)]'
```

For the footer:

```svelte
<div class="border-t border-isotope-line bg-isotope-panel px-7 py-4">
```

- [ ] **Step 6: Restyle approval cards while preserving actions**

Change the approval card wrapper to:

```svelte
<div class="mx-auto mb-5 w-full max-w-3xl border border-isotope-yellow bg-isotope-paper shadow-[6px_6px_0_#edc531]">
```

Keep both approval buttons and their `onclick={() => onResolveApproval(...)}` calls unchanged.

- [ ] **Step 7: Run conversation test**

```bash
cd apps/desktop
npm run test -- src/lib/components/main/ConversationWorkspace.test.ts
```

Expected: PASS.

- [ ] **Step 8: Commit conversation shell**

```bash
git add apps/desktop/src/lib/components/main/MainWindowShell.svelte apps/desktop/src/lib/components/main/ConversationWorkspace.svelte apps/desktop/src/lib/components/main/ConversationWorkspace.test.ts
git commit -m "style(desktop): restyle conversation workspace"
```

## Task 4: Capability Card And Details

**Files:**
- Modify: `apps/desktop/src/lib/components/main/CapacityCallCard.svelte`
- Modify: `apps/desktop/src/lib/components/main/CapacityCallDetails.svelte`
- Create: `apps/desktop/src/lib/components/main/CapacityCallCard.test.ts`
- Test: `apps/desktop/src/lib/view/capacityCallView.test.ts`

- [ ] **Step 1: Add source guard for card affordances**

Create `apps/desktop/src/lib/components/main/CapacityCallCard.test.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

describe('CapacityCallCard visual structure', () => {
  test('keeps folded details, fullscreen details, and artifact actions visible', () => {
    const source = readFileSync(join(process.cwd(), 'src/lib/components/main/CapacityCallCard.svelte'), 'utf8');

    expect(source).toContain('capacity-status-mark');
    expect(source).toContain('toggleExpanded');
    expect(source).toContain('openFullscreen');
    expect(source).toContain('viewOriginal');
    expect(source).toContain('openArtifactFolder');
    expect(source).toContain('downloadArtifact');
    expect(source).toContain('原图');
    expect(source).toContain('文件夹');
    expect(source).toContain('下载');
  });
});
```

- [ ] **Step 2: Run the new test and confirm it fails**

```bash
cd apps/desktop
npm run test -- src/lib/components/main/CapacityCallCard.test.ts
```

Expected: FAIL because `capacity-status-mark` is not present yet.

- [ ] **Step 3: Add status mark classes**

In `CapacityCallCard.svelte`, keep the existing `statusClass` derived value and add:

```ts
  const statusMarkClass = $derived(
    call.status === 'ok'
      ? 'bg-isotope-green'
      : call.status === 'running'
        ? 'bg-isotope-blue'
        : call.status === 'error'
          ? 'bg-isotope-red'
          : call.status === 'blocked'
            ? 'bg-isotope-yellow'
            : 'bg-isotope-muted'
  );
```

- [ ] **Step 4: Restyle the card header without changing actions**

Change the card opening and header mark to:

```svelte
<section class="border border-isotope-line bg-isotope-panel text-isotope-text shadow-[4px_4px_0_rgba(23,23,23,0.12)]" aria-label={`能力动作 ${productTitle}`}>
  <div class="flex items-start justify-between gap-3 px-3 py-2">
    <div class="min-w-0">
      <div class="flex flex-wrap items-center gap-2">
        <span class={`capacity-status-mark h-3 w-3 shrink-0 ${statusMarkClass}`} aria-hidden="true"></span>
        <span class="text-xs font-semibold uppercase text-isotope-muted">capacity</span>
        <span class={`border px-1.5 py-0.5 text-[11px] font-semibold uppercase ${statusClass}`}>{statusLabel}</span>
      </div>
```

Keep `expanded`, `fullscreen`, screenshot artifact handlers, and buttons unchanged.

- [ ] **Step 5: Restyle details and modals**

Use these class replacements:

```svelte
<div class="space-y-3 border-t border-isotope-line bg-isotope-paper px-3 py-3">
```

For fullscreen overlay:

```svelte
<div class="fixed inset-0 z-50 bg-isotope-ink/45 p-4" role="dialog" aria-modal="true" aria-label={`动作详情 ${productTitle}`}>
```

For fullscreen section:

```svelte
<section class="mx-auto flex h-full max-w-5xl flex-col border border-isotope-line bg-isotope-panel shadow-[8px_8px_0_#171717]">
```

In `CapacityCallDetails.svelte`, keep the two existing `<pre>` render paths. Replace their shared base classes with these values so fullscreen mode is bounded to the viewport and inline mode remains compact.

For the `details` branch inside the `sourcePreviews.length` block:

```svelte
<pre
  class={[
    'mt-2 overflow-auto whitespace-pre-wrap break-words text-xs leading-5 text-isotope-text',
    fullscreen ? 'max-h-[70vh]' : 'max-h-64'
  ]}
>{formatCapacityDetailContent(section)}</pre>
```

For the normal detail body:

```svelte
<pre
  class={[
    'overflow-auto whitespace-pre-wrap break-words px-3 py-2 text-xs leading-5 text-isotope-text',
    fullscreen ? 'max-h-[70vh]' : 'max-h-64'
  ]}
>{formatCapacityDetailContent(section)}</pre>
```

- [ ] **Step 6: Run card and view tests**

```bash
cd apps/desktop
npm run test -- src/lib/components/main/CapacityCallCard.test.ts src/lib/view/capacityCallView.test.ts
```

Expected: PASS.

- [ ] **Step 7: Commit capability cards**

```bash
git add apps/desktop/src/lib/components/main/CapacityCallCard.svelte apps/desktop/src/lib/components/main/CapacityCallDetails.svelte apps/desktop/src/lib/components/main/CapacityCallCard.test.ts
git commit -m "style(desktop): restyle capability cards"
```

## Task 5: Composer And Error States

**Files:**
- Modify: `apps/desktop/src/lib/components/common/CommandComposer.svelte`
- Modify: `apps/desktop/src/lib/components/main/ConversationWorkspace.svelte`
- Test: `apps/desktop/src/lib/components/main/ConversationWorkspace.test.ts`

- [ ] **Step 1: Add composer source guard**

Append this test to `ConversationWorkspace.test.ts`:

```ts
test('keeps composer and error regions visually distinct', () => {
  const workspace = readFileSync(join(process.cwd(), 'src/lib/components/main/ConversationWorkspace.svelte'), 'utf8');
  const composer = readFileSync(join(process.cwd(), 'src/lib/components/common/CommandComposer.svelte'), 'utf8');

  expect(workspace).toContain('role="alert"');
  expect(workspace).toContain('border-isotope-red');
  expect(composer).toContain('bg-isotope-panel');
  expect(composer).toContain('bg-isotope-red');
  expect(composer).toContain('focus-within:border-isotope-blue');
});
```

- [ ] **Step 2: Run the test and confirm it fails**

```bash
cd apps/desktop
npm run test -- src/lib/components/main/ConversationWorkspace.test.ts
```

Expected: FAIL until error and composer classes are updated.

- [ ] **Step 3: Restyle `CommandComposer`**

Modify the form and button classes in `CommandComposer.svelte`:

```svelte
<form
  class="flex items-center gap-2 border border-isotope-line bg-isotope-panel px-2 py-2 shadow-[4px_4px_0_rgba(23,23,23,0.12)] focus-within:border-isotope-blue focus-within:ring-2 focus-within:ring-isotope-blue/15"
  onsubmit={(event) => {
    event.preventDefault();
    submit();
  }}
>
```

```svelte
<button
  class="border border-isotope-red bg-isotope-red px-3 py-1.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:border-isotope-line disabled:bg-isotope-paper disabled:text-isotope-muted"
  type="submit"
  {disabled}
>
  发送
</button>
```

Keep the `submit()` behavior unchanged.

- [ ] **Step 4: Restyle error alerts**

In `ConversationWorkspace.svelte`, change both error alert wrappers to:

```svelte
<div class="mb-3 border border-isotope-red bg-isotope-paper px-3 py-2 text-xs text-isotope-red" role="alert">
```

Keep `chatError` and `approvalError` logic unchanged.

- [ ] **Step 5: Run conversation tests**

```bash
cd apps/desktop
npm run test -- src/lib/components/main/ConversationWorkspace.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit composer and error states**

```bash
git add apps/desktop/src/lib/components/common/CommandComposer.svelte apps/desktop/src/lib/components/main/ConversationWorkspace.svelte apps/desktop/src/lib/components/main/ConversationWorkspace.test.ts
git commit -m "style(desktop): restyle composer states"
```

## Task 6: Full Desktop Verification

**Files:**
- No source files expected unless verification exposes visual overlap or type errors.

- [ ] **Step 1: Run targeted desktop tests**

```bash
cd apps/desktop
npm run test -- \
  src/lib/view/desktopVisualTokens.test.ts \
  src/lib/window/windowSurface.test.ts \
  src/lib/components/main/ConversationWorkspace.test.ts \
  src/lib/components/main/CapacityCallCard.test.ts \
  src/lib/view/capacityCallView.test.ts \
  src/routes/pageAgentWorkspace.test.ts
```

Expected: PASS.

- [ ] **Step 2: Run full desktop type check**

```bash
cd apps/desktop
npm run check
```

Expected: PASS. If Svelte reports a class array/type issue, fix the exact component and rerun this command.

- [ ] **Step 3: Run full desktop unit test suite**

```bash
cd apps/desktop
npm run test
```

Expected: PASS.

- [ ] **Step 4: Run desktop production build**

```bash
cd apps/desktop
npm run build
```

Expected: PASS.

- [ ] **Step 5: Check observe plan**

```bash
cd apps/desktop
npm run observe:desktop -- --plan
```

Expected: command prints the available observe/CDP plan as JSON. If it fails because local desktop prerequisites are missing, record the exact output in the final report.

- [ ] **Step 6: Visual smoke if environment supports it**

Start the full desktop stack:

```bash
cd apps/desktop
npm run dev:full
```

In a second shell, run the desktop observe command recommended by `--plan`. Verify at minimum:

- main chat empty state uses warm canvas and visible composition mark;
- user and assistant messages remain readable;
- capability card has a visible status mark and still expands;
- approval card still shows `批准` and `拒绝`;
- no header text overlaps the geometric mark.

If `dev:full` or CDP is blocked by local environment, stop after recording the command and output.

- [ ] **Step 7: Commit verification-only fixes if needed**

If Step 2-6 required source fixes:

```bash
git add apps/desktop
git commit -m "fix(desktop): polish suprematist chat visual QA"
```

If no fixes were needed, do not create an empty commit.

- [ ] **Step 8: Push branch and stop before merge**

```bash
git status --short --branch
git log --oneline origin/main..HEAD
git push -u origin feat/desktop-suprematist-chat
```

Expected: branch is pushed. Do not run `git checkout main`, `git merge`, `git rebase main && git merge --ff-only`, or `gh pr merge`. Final report should say implementation is ready for user review and not merged to `main`.

## Future Follow-Up Plan Boundary

Do not include these in the first implementation branch unless the user explicitly expands scope again after reviewing the first slice:

- `AgentWorkspaceShell` state-responsive sidebars.
- `AgentWorkspaceSidebar`, `AgentConversationPane`, `AgentConversationComposer`, `AgentChannelInspector`, and `CodexSessionPicker` visual migration.
- `MiniWindow`.
- `AgentGroupWorkspace` and related agent group components.
- `DevDiagnosticShell`, snapshot shell, event stream, activity rail, and inspector dock.

Those follow-up surfaces should reuse the tokens and class patterns from this first branch.
