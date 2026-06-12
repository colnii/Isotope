# Desktop Suprematist Main Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the approved Canvas Suprematist visual direction to the first-round Desktop main chat path.

**Architecture:** Keep the existing Svelte component and data flow contracts intact. Add shared visual tokens and lightweight component classes first, then restyle `ConversationWorkspace`, `CapacityCallCard`, `CapacityCallDetails`, and `CommandComposer` without changing backend, SSE, approval, or artifact behavior.

**Tech Stack:** Svelte 5, SvelteKit, Tailwind CSS, Vitest, Tauri desktop smoke scripts.

---

## File Structure

- Modify `apps/desktop/tailwind.config.ts`: define Canvas Suprematist design tokens while preserving existing `isotope` aliases used by other components.
- Modify `apps/desktop/src/app.css`: add shared `@layer components` classes for the chat shell, header geometry, cards, buttons, composer, and status accents.
- Modify `apps/desktop/src/lib/components/main/ConversationWorkspace.svelte`: apply the chat shell, top geometry, approval card, message bubbles, empty state, and error card visual language.
- Modify `apps/desktop/src/lib/components/main/CapacityCallCard.svelte`: apply status rail/dot classes, keep collapsed-by-default behavior, and restyle fullscreen/artifact controls.
- Modify `apps/desktop/src/lib/components/main/CapacityCallDetails.svelte`: align detail surfaces and bounded raw-result areas with the new token set.
- Modify `apps/desktop/src/lib/components/common/CommandComposer.svelte`: restyle the bottom composer with fixed dimensions, clear focus state, red send action, and readable disabled state.
- Modify `apps/desktop/src/lib/components/main/ConversationWorkspace.test.ts`: add source-level guards for the header/status/geometry separation.
- Create `apps/desktop/src/lib/components/main/visualStyle.test.ts`: source-level guards for token presence, shared class presence, and main-chat visual contract markers.

Do not touch `AgentWorkspaceShell.svelte` in this first round. It is over 500 lines and belongs to the follow-up visual expansion.

## Baseline

Already verified in `/home/lumber/Github/isotope/.worktrees/desktop-suprematist-main-chat`:

- `npm ci` in `apps/desktop` succeeds.
- `npm run check` succeeds with 0 errors and 0 warnings.
- `npm test` succeeds with 30 files and 114 tests.
- `npm run observe:desktop -- --plan` returns the CDP and screen observe recipes.

### Task 1: Visual Tokens And Shared Classes

**Files:**
- Modify: `apps/desktop/tailwind.config.ts`
- Modify: `apps/desktop/src/app.css`
- Create: `apps/desktop/src/lib/components/main/visualStyle.test.ts`

- [ ] **Step 1: Write the failing token/class guard test**

Create `apps/desktop/src/lib/components/main/visualStyle.test.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

function read(relativePath: string): string {
  return readFileSync(join(process.cwd(), relativePath), 'utf8');
}

describe('desktop Canvas Suprematist visual system', () => {
  test('defines the first-round design tokens', () => {
    const source = read('tailwind.config.ts');

    expect(source).toContain("canvas: '#f7f1e3'");
    expect(source).toContain("panel: '#fffcf4'");
    expect(source).toContain("'panel-raised': '#fff8ec'");
    expect(source).toContain("ink: '#202020'");
    expect(source).toContain("red: '#c9342c'");
    expect(source).toContain("blue: '#1d58a8'");
    expect(source).toContain("yellow: '#e2b631'");
    expect(source).toContain("line: '#d6cdbd'");
    expect(source).toContain("'line-strong': '#bdb4a4'");
  });

  test('registers shared main-chat component classes', () => {
    const source = read('src/app.css');

    expect(source).toContain('.iso-chat-shell');
    expect(source).toContain('.iso-chat-header');
    expect(source).toContain('.iso-chat-header-copy');
    expect(source).toContain('max-width: calc(100% - 11rem)');
    expect(source).toContain('.iso-suprematist-mark');
    expect(source).toContain('.iso-message-bubble-user');
    expect(source).toContain('.iso-capacity-card');
    expect(source).toContain('.iso-command-composer');
  });
});
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```bash
cd apps/desktop
npm test -- src/lib/components/main/visualStyle.test.ts
```

Expected: fail because `visualStyle.test.ts` refers to tokens and classes that do not exist yet.

- [ ] **Step 3: Replace the Tailwind isotope palette**

Edit `apps/desktop/tailwind.config.ts` so the `colors.isotope` object is:

```ts
        isotope: {
          bg: '#f7f1e3',
          canvas: '#f7f1e3',
          panel: '#fffcf4',
          'panel-raised': '#fff8ec',
          text: '#202020',
          ink: '#202020',
          muted: '#7d7467',
          line: '#d6cdbd',
          'line-strong': '#bdb4a4',
          red: '#c9342c',
          'red-dark': '#8f1512',
          yellow: '#e2b631',
          'yellow-surface': '#fff2c8',
          blue: '#1d58a8',
          'blue-surface': '#edf3f9',
          green: '#26734d',
          'green-surface': '#e8f3ea',
          attention: '#c9342c',
          running: '#1d58a8',
          warning: '#e2b631',
          done: '#26734d',
          error: '#c9342c'
        }
```

Keep the rest of the file unchanged.

- [ ] **Step 4: Add shared component classes**

Append this to `apps/desktop/src/app.css` after the existing base element rules:

```css

@layer components {
  .iso-chat-shell {
    @apply relative flex min-h-screen min-w-0 flex-col overflow-hidden bg-isotope-canvas text-isotope-text;
  }

  .iso-chat-header {
    @apply relative border-b border-isotope-line bg-isotope-panel px-7 py-5;
  }

  .iso-chat-header-copy {
    max-width: calc(100% - 11rem);
  }

  .iso-chat-eyebrow {
    @apply text-xs font-bold uppercase text-isotope-red;
  }

  .iso-chat-title {
    @apply mt-1 truncate text-xl font-semibold text-isotope-text;
  }

  .iso-chat-subtitle {
    @apply mt-2 inline-flex w-fit max-w-full items-center rounded-full border border-isotope-line bg-isotope-canvas px-2.5 py-1 text-xs font-medium text-isotope-muted;
  }

  .iso-suprematist-mark {
    @apply pointer-events-none absolute right-7 top-4 h-14 w-36;
  }

  .iso-suprematist-red {
    @apply absolute right-3 top-1 h-4 w-12 bg-isotope-red;
    transform: rotate(-12deg);
  }

  .iso-suprematist-blue {
    @apply absolute right-16 top-7 h-7 w-7 bg-isotope-blue;
  }

  .iso-suprematist-yellow {
    @apply absolute right-28 top-2 h-6 w-6 bg-isotope-yellow;
  }

  .iso-suprematist-ink {
    @apply absolute bottom-1 right-0 h-9 w-2.5 bg-isotope-ink;
  }

  .iso-chat-scroll {
    @apply min-h-0 flex flex-1 flex-col overflow-y-auto bg-isotope-canvas px-7 py-6;
  }

  .iso-card {
    @apply rounded-panel border border-isotope-line bg-isotope-panel shadow-sm;
  }

  .iso-card-raised {
    @apply rounded-panel border border-isotope-line bg-isotope-panel-raised shadow-sm;
  }

  .iso-status-chip {
    @apply inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase;
  }

  .iso-approval-card {
    @apply mx-auto mb-5 w-full max-w-3xl overflow-hidden rounded-panel border border-isotope-yellow bg-isotope-yellow-surface text-isotope-text;
  }

  .iso-message-avatar {
    @apply grid h-8 w-8 shrink-0 place-items-center rounded-panel border border-isotope-line bg-isotope-panel-raised text-xs font-bold text-isotope-red;
  }

  .iso-message-bubble {
    @apply min-w-0 rounded-panel border border-isotope-line bg-isotope-panel px-4 py-3 text-sm leading-6 shadow-sm;
  }

  .iso-message-bubble-user {
    @apply max-w-[min(72%,32rem)] rounded-full border-0 bg-isotope-blue px-4 py-3 text-sm font-medium leading-6 text-white shadow-sm;
  }

  .iso-message-bubble-assistant {
    @apply max-w-[min(82%,40rem)] text-isotope-text;
  }

  .iso-error-card {
    @apply mb-3 rounded-panel border border-isotope-error bg-isotope-panel px-3 py-2 text-xs text-isotope-error;
  }

  .iso-capacity-card {
    @apply relative overflow-hidden rounded-panel border border-isotope-line bg-isotope-panel text-isotope-text shadow-sm;
  }

  .iso-capacity-status-dot {
    @apply inline-block h-2 w-2 rounded-full;
  }

  .iso-capacity-actions {
    @apply grid h-7 w-7 place-items-center rounded-panel border border-isotope-line bg-isotope-panel-raised text-xs text-isotope-muted;
  }

  .iso-command-composer {
    @apply flex min-h-12 items-center gap-2 rounded-panel border border-isotope-line bg-isotope-panel px-2 py-2 shadow-sm transition-colors focus-within:border-isotope-red focus-within:ring-2 focus-within:ring-isotope-red/15;
  }

  .iso-command-input {
    @apply min-w-0 flex-1 bg-transparent px-2 py-1.5 text-sm text-isotope-text outline-none placeholder:text-isotope-muted disabled:cursor-not-allowed disabled:text-isotope-muted;
  }

  .iso-button-primary {
    @apply rounded-full bg-isotope-red px-4 py-1.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-isotope-red-dark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-isotope-red focus-visible:ring-offset-2 focus-visible:ring-offset-isotope-panel disabled:cursor-not-allowed disabled:bg-isotope-line disabled:text-isotope-muted disabled:shadow-none;
  }

  .iso-button-muted {
    @apply rounded-full border border-isotope-line bg-isotope-panel px-3 py-1.5 text-xs font-semibold text-isotope-muted transition-colors hover:border-isotope-line-strong hover:text-isotope-text disabled:cursor-not-allowed disabled:opacity-60;
  }
}

@media (max-width: 640px) {
  .iso-chat-header-copy {
    max-width: 100%;
    padding-right: 4rem;
  }

  .iso-suprematist-mark {
    @apply right-4 top-4 opacity-30;
  }
}
```

- [ ] **Step 5: Run the guard test**

Run:

```bash
cd apps/desktop
npm test -- src/lib/components/main/visualStyle.test.ts
```

Expected: pass.

- [ ] **Step 6: Run type check**

Run:

```bash
cd apps/desktop
npm run check
```

Expected: `svelte-check found 0 errors and 0 warnings`.

- [ ] **Step 7: Commit**

Run:

```bash
git add apps/desktop/tailwind.config.ts apps/desktop/src/app.css apps/desktop/src/lib/components/main/visualStyle.test.ts
git commit -m "feat(desktop): add suprematist chat visual tokens"
```

### Task 2: Conversation Workspace Shell And Message Flow

**Files:**
- Modify: `apps/desktop/src/lib/components/main/ConversationWorkspace.svelte`
- Modify: `apps/desktop/src/lib/components/main/ConversationWorkspace.test.ts`
- Modify: `apps/desktop/src/lib/components/main/visualStyle.test.ts`

- [ ] **Step 1: Add source guards for header geometry and message classes**

Append this test to `apps/desktop/src/lib/components/main/ConversationWorkspace.test.ts`:

```ts

  test('separates status chip from suprematist header marks', () => {
    const path = join(process.cwd(), 'src/lib/components/main/ConversationWorkspace.svelte');
    const source = readFileSync(path, 'utf8');

    expect(source).toContain('class="iso-chat-header"');
    expect(source).toContain('class="iso-chat-subtitle"');
    expect(source).toContain('class="iso-suprematist-mark"');
    expect(source).toContain('aria-hidden="true"');
    expect(source.indexOf('class="iso-chat-subtitle"')).toBeLessThan(
      source.indexOf('class="iso-suprematist-mark"')
    );
  });
```

Add this test to `apps/desktop/src/lib/components/main/visualStyle.test.ts` inside the existing `describe` block:

```ts
  test('conversation workspace uses first-round main-chat classes', () => {
    const source = read('src/lib/components/main/ConversationWorkspace.svelte');

    expect(source).toContain('class="iso-chat-shell"');
    expect(source).toContain('class="iso-chat-scroll"');
    expect(source).toContain('iso-approval-card');
    expect(source).toContain('iso-message-bubble-user');
    expect(source).toContain('iso-message-bubble-assistant');
    expect(source).toContain('iso-error-card');
  });
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
cd apps/desktop
npm test -- src/lib/components/main/ConversationWorkspace.test.ts src/lib/components/main/visualStyle.test.ts
```

Expected: fail because `ConversationWorkspace.svelte` still uses the old white/gray layout classes.

- [ ] **Step 3: Replace the outer shell and header**

In `ConversationWorkspace.svelte`, replace:

```svelte
<section class="flex min-h-screen min-w-0 flex-col bg-white" aria-label="Conversation workspace">
  <header class="border-b border-isotope-line px-7 py-5">
    <div class="flex items-center justify-between gap-4">
      <div class="min-w-0">
        <div class="text-xs font-semibold uppercase text-isotope-muted">{eyebrow}</div>
        <h1 class="mt-1 truncate text-xl font-semibold text-isotope-text">{title}</h1>
      </div>
      {#if subtitle}
        <div class="shrink-0 border border-isotope-line bg-isotope-panel px-2 py-1 text-xs text-isotope-muted">
          {subtitle}
        </div>
      {/if}
    </div>
  </header>
```

with:

```svelte
<section class="iso-chat-shell" aria-label="Conversation workspace">
  <header class="iso-chat-header">
    <div class="iso-chat-header-copy">
      <div class="iso-chat-eyebrow">{eyebrow}</div>
      <h1 class="iso-chat-title">{title}</h1>
      {#if subtitle}
        <div class="iso-chat-subtitle">
          {subtitle}
        </div>
      {/if}
    </div>
    <div class="iso-suprematist-mark" aria-hidden="true">
      <span class="iso-suprematist-red"></span>
      <span class="iso-suprematist-blue"></span>
      <span class="iso-suprematist-yellow"></span>
      <span class="iso-suprematist-ink"></span>
    </div>
  </header>
```

Replace the chat scroll wrapper:

```svelte
  <div class="min-h-0 flex flex-1 flex-col overflow-y-auto px-7 py-6" aria-live="polite">
```

with:

```svelte
  <div class="iso-chat-scroll" aria-live="polite">
```

- [ ] **Step 4: Restyle approval cards**

Replace the approvals block wrapper:

```svelte
      <div class="mx-auto mb-5 w-full max-w-3xl border border-isotope-warning/50 bg-isotope-warning/10">
        <div class="flex items-center justify-between gap-3 border-b border-isotope-warning/30 px-4 py-3">
```

with:

```svelte
      <div class="iso-approval-card">
        <div class="flex items-center justify-between gap-3 border-b border-isotope-yellow px-4 py-3">
```

Replace the source label class:

```svelte
                  <span class="border border-isotope-warning/40 bg-white px-2 py-0.5 text-[11px] uppercase text-isotope-warning">
```

with:

```svelte
                  <span class="iso-status-chip border-isotope-yellow bg-isotope-panel text-isotope-text">
```

Replace the approval action button classes:

```svelte
                  class="border border-isotope-line bg-white px-3 py-1.5 text-xs font-semibold text-isotope-muted disabled:cursor-not-allowed disabled:opacity-50"
```

with:

```svelte
                  class="iso-button-muted"
```

and:

```svelte
                  class="border border-isotope-running bg-isotope-running px-3 py-1.5 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
```

with:

```svelte
                  class="iso-button-primary"
```

- [ ] **Step 5: Restyle empty state and message bubbles**

Replace the empty-state avatar:

```svelte
          <div class="grid h-9 w-9 shrink-0 place-items-center border border-isotope-line bg-isotope-bg text-xs font-semibold text-isotope-running">
```

with:

```svelte
          <div class="iso-message-avatar h-9 w-9">
```

Replace the empty-state body card:

```svelte
          <div class="min-w-0 flex-1 border border-isotope-line bg-isotope-bg px-4 py-3">
```

with:

```svelte
          <div class="iso-card-raised min-w-0 flex-1 px-4 py-3">
```

Replace the assistant message avatar:

```svelte
              <div class="grid h-8 w-8 shrink-0 place-items-center border border-isotope-line bg-isotope-bg text-xs font-semibold text-isotope-running">
```

with:

```svelte
              <div class="iso-message-avatar">
```

Replace the message bubble class expression:

```svelte
              class={[
                'min-w-0 border px-4 py-3 text-sm leading-6 shadow-sm',
                message.role === 'user'
                  ? 'max-w-[min(72%,32rem)] border-isotope-running bg-isotope-running text-white'
                  : 'max-w-[min(82%,40rem)] border-isotope-line bg-isotope-bg text-isotope-text'
              ]}
```

with:

```svelte
              class={[
                'min-w-0',
                message.role === 'user'
                  ? 'iso-message-bubble-user'
                  : 'iso-message-bubble iso-message-bubble-assistant'
              ]}
```

- [ ] **Step 6: Restyle footer and errors**

Replace:

```svelte
  <div class="border-t border-isotope-line bg-white px-7 py-4">
```

with:

```svelte
  <div class="border-t border-isotope-line bg-isotope-panel px-7 py-4">
```

Replace both error alert class strings:

```svelte
      <div class="mb-3 border border-isotope-error/40 bg-white px-3 py-2 text-xs text-isotope-error" role="alert">
```

with:

```svelte
      <div class="iso-error-card" role="alert">
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
cd apps/desktop
npm test -- src/lib/components/main/ConversationWorkspace.test.ts src/lib/components/main/visualStyle.test.ts
```

Expected: pass.

- [ ] **Step 8: Run type check**

Run:

```bash
cd apps/desktop
npm run check
```

Expected: `svelte-check found 0 errors and 0 warnings`.

- [ ] **Step 9: Commit**

Run:

```bash
git add apps/desktop/src/lib/components/main/ConversationWorkspace.svelte apps/desktop/src/lib/components/main/ConversationWorkspace.test.ts apps/desktop/src/lib/components/main/visualStyle.test.ts
git commit -m "feat(desktop): apply suprematist main chat shell"
```

### Task 3: Capacity Card Visual Contract

**Files:**
- Modify: `apps/desktop/src/lib/components/main/CapacityCallCard.svelte`
- Modify: `apps/desktop/src/lib/components/main/CapacityCallDetails.svelte`
- Modify: `apps/desktop/src/lib/components/main/visualStyle.test.ts`

- [ ] **Step 1: Add source guards for capacity card classes**

Add this test to `apps/desktop/src/lib/components/main/visualStyle.test.ts` inside the existing `describe` block:

```ts
  test('capacity card keeps status visible without expanding details', () => {
    const source = read('src/lib/components/main/CapacityCallCard.svelte');

    expect(source).toContain('capacityToneClass');
    expect(source).toContain('capacityStatusDotClass');
    expect(source).toContain('iso-capacity-card');
    expect(source).toContain('iso-capacity-status-dot');
    expect(source).toContain('iso-capacity-actions');
    expect(source).toContain('aria-label={`能力动作 ${productTitle}`}');
  });
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
cd apps/desktop
npm test -- src/lib/components/main/visualStyle.test.ts
```

Expected: fail because `CapacityCallCard.svelte` has not been restyled yet.

- [ ] **Step 3: Add status tone derivations**

In `CapacityCallCard.svelte`, replace the `statusClass` derived block with:

```svelte
  const statusClass = $derived(
    call.status === 'ok'
      ? 'border-isotope-done bg-isotope-green-surface text-isotope-done'
      : call.status === 'running'
        ? 'border-isotope-blue bg-isotope-blue-surface text-isotope-blue'
        : call.status === 'error'
          ? 'border-isotope-error bg-isotope-panel text-isotope-error'
          : 'border-isotope-line bg-isotope-panel text-isotope-muted'
  );
  const capacityToneClass = $derived(
    call.status === 'ok'
      ? 'before:bg-isotope-done'
      : call.status === 'running'
        ? 'before:bg-isotope-blue'
        : call.status === 'error'
          ? 'before:bg-isotope-error'
          : 'before:bg-isotope-line-strong'
  );
  const capacityStatusDotClass = $derived(
    call.status === 'ok'
      ? 'bg-isotope-done'
      : call.status === 'running'
        ? 'bg-isotope-blue'
        : call.status === 'error'
          ? 'bg-isotope-error'
          : 'bg-isotope-muted'
  );
```

- [ ] **Step 4: Restyle the collapsed card header**

Replace the opening capacity card section:

```svelte
<section class="border border-isotope-line bg-white text-isotope-text shadow-sm" aria-label={`能力动作 ${productTitle}`}>
  <div class="flex items-start justify-between gap-3 px-3 py-2">
```

with:

```svelte
<section
  class={`iso-capacity-card before:absolute before:inset-y-0 before:left-0 before:w-1.5 ${capacityToneClass}`}
  aria-label={`能力动作 ${productTitle}`}
>
  <div class="flex items-start justify-between gap-3 px-4 py-3 pl-5">
```

Replace the status row:

```svelte
        <span class="text-xs font-semibold uppercase text-isotope-muted">action</span>
        <span class={`border px-1.5 py-0.5 text-[11px] font-semibold uppercase ${statusClass}`}>{statusLabel}</span>
```

with:

```svelte
        <span class={`iso-capacity-status-dot ${capacityStatusDotClass}`}></span>
        <span class="text-xs font-semibold uppercase text-isotope-muted">capacity</span>
        <span class={`iso-status-chip ${statusClass}`}>{statusLabel}</span>
```

Replace both action button class strings:

```svelte
        class="grid h-7 w-7 place-items-center border border-isotope-line bg-isotope-panel text-xs"
```

with:

```svelte
        class="iso-capacity-actions"
```

- [ ] **Step 5: Restyle expanded details and artifact actions**

Replace:

```svelte
    <div class="space-y-3 border-t border-isotope-line px-3 py-3">
```

with:

```svelte
    <div class="space-y-3 border-t border-isotope-line bg-isotope-panel-raised px-4 py-3">
```

Replace the screen artifact container:

```svelte
        <div class="border border-isotope-line bg-isotope-panel px-3 py-2">
```

with:

```svelte
        <div class="iso-card bg-isotope-panel px-3 py-2">
```

Replace the `原图` button class:

```svelte
                class="border border-isotope-running bg-white px-2.5 py-1.5 text-xs font-semibold text-isotope-running disabled:opacity-50"
```

with:

```svelte
                class="iso-button-primary text-xs disabled:opacity-60"
```

Replace the `文件夹` and `下载` button class strings:

```svelte
                class="border border-isotope-line bg-white px-2.5 py-1.5 text-xs font-semibold text-isotope-muted disabled:opacity-50"
```

with:

```svelte
                class="iso-button-muted disabled:opacity-60"
```

- [ ] **Step 6: Restyle fullscreen overlays**

Replace the detail fullscreen panel class:

```svelte
    <section class="mx-auto flex h-full max-w-5xl flex-col border border-isotope-line bg-white shadow-xl">
```

with:

```svelte
    <section class="mx-auto flex h-full max-w-5xl flex-col rounded-panel border border-isotope-line bg-isotope-panel shadow-xl">
```

Replace the detail fullscreen header class:

```svelte
      <header class="flex items-start justify-between gap-3 border-b border-isotope-line px-4 py-3">
```

with:

```svelte
      <header class="flex items-start justify-between gap-3 border-b border-isotope-line bg-isotope-panel-raised px-4 py-3">
```

Replace the close button class in both fullscreen dialogs:

```svelte
          class="grid h-8 w-8 place-items-center border border-isotope-line bg-isotope-panel text-sm"
```

with:

```svelte
          class="iso-capacity-actions h-8 w-8 text-sm"
```

- [ ] **Step 7: Align capacity details surface**

In `CapacityCallDetails.svelte`, replace old `bg-isotope-panel`, `bg-white`, and raw result containers with Canvas Suprematist surfaces:

```svelte
<p class="iso-card bg-isotope-panel-raised px-3 py-2 text-sm text-isotope-muted">
```

for empty details, use:

```svelte
<section class="iso-card bg-isotope-panel-raised">
```

for detail sections, and keep raw text areas as:

```svelte
class={[
  'mt-2 max-h-[min(68vh,34rem)] overflow-auto whitespace-pre-wrap break-words rounded-panel bg-isotope-canvas px-3 py-2 text-xs leading-5 text-isotope-text',
  fullscreen ? 'max-h-none' : ''
]}
```

Do not remove existing source links, raw result details, or bounded scroll behavior.

- [ ] **Step 8: Run focused tests**

Run:

```bash
cd apps/desktop
npm test -- src/lib/components/main/visualStyle.test.ts src/lib/view/capacityCallView.test.ts
```

Expected: pass.

- [ ] **Step 9: Run type check**

Run:

```bash
cd apps/desktop
npm run check
```

Expected: `svelte-check found 0 errors and 0 warnings`.

- [ ] **Step 10: Commit**

Run:

```bash
git add apps/desktop/src/lib/components/main/CapacityCallCard.svelte apps/desktop/src/lib/components/main/CapacityCallDetails.svelte apps/desktop/src/lib/components/main/visualStyle.test.ts
git commit -m "feat(desktop): restyle capacity result cards"
```

### Task 4: Composer And Error Surface Polish

**Files:**
- Modify: `apps/desktop/src/lib/components/common/CommandComposer.svelte`
- Modify: `apps/desktop/src/lib/components/main/visualStyle.test.ts`

- [ ] **Step 1: Add source guards for composer classes**

Add this test to `apps/desktop/src/lib/components/main/visualStyle.test.ts` inside the existing `describe` block:

```ts
  test('command composer uses fixed visual shell and primary action', () => {
    const source = read('src/lib/components/common/CommandComposer.svelte');

    expect(source).toContain('class="iso-command-composer"');
    expect(source).toContain('class="iso-command-input"');
    expect(source).toContain('class="iso-button-primary"');
  });
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
cd apps/desktop
npm test -- src/lib/components/main/visualStyle.test.ts
```

Expected: fail because `CommandComposer.svelte` still uses old inline Tailwind classes.

- [ ] **Step 3: Replace the form markup**

In `CommandComposer.svelte`, replace the form and its children with:

```svelte
<form
  class="iso-command-composer"
  onsubmit={(event) => {
    event.preventDefault();
    submit();
  }}
>
  <input
    class="iso-command-input"
    {placeholder}
    bind:value
    {disabled}
  />
  <button
    class="iso-button-primary"
    type="submit"
    {disabled}
  >
    发送
  </button>
</form>
```

Keep the `<script>` block unchanged.

- [ ] **Step 4: Run composer and chat tests**

Run:

```bash
cd apps/desktop
npm test -- src/lib/components/main/visualStyle.test.ts src/lib/components/main/ConversationWorkspace.test.ts
```

Expected: pass.

- [ ] **Step 5: Run type check**

Run:

```bash
cd apps/desktop
npm run check
```

Expected: `svelte-check found 0 errors and 0 warnings`.

- [ ] **Step 6: Commit**

Run:

```bash
git add apps/desktop/src/lib/components/common/CommandComposer.svelte apps/desktop/src/lib/components/main/visualStyle.test.ts
git commit -m "feat(desktop): polish chat composer controls"
```

### Task 5: Build And Visual Verification

**Files:**
- Verify and, only if inspection exposes overlap or contrast defects, modify one of the files already touched in Tasks 1-4.

- [ ] **Step 1: Run all desktop tests**

Run:

```bash
cd apps/desktop
npm test
```

Expected: all 30+ test files pass.

- [ ] **Step 2: Run Svelte type check**

Run:

```bash
cd apps/desktop
npm run check
```

Expected: `svelte-check found 0 errors and 0 warnings`.

- [ ] **Step 3: Run production build**

Run:

```bash
cd apps/desktop
npm run build
```

Expected: Vite/SvelteKit build succeeds and emits the static client bundle.

- [ ] **Step 4: Print desktop observe plan**

Run:

```bash
cd apps/desktop
npm run observe:desktop -- --plan
```

Expected: JSON output with `cdp` and `screen` modes.

- [ ] **Step 5: Start local app for visual inspection**

Run:

```bash
cd apps/desktop
npm run dev -- --port 5175
```

Expected: Vite prints a local URL on `127.0.0.1:5175`. Keep this process running while inspecting the browser.

- [ ] **Step 6: Inspect main chat in a browser**

Open:

```text
http://127.0.0.1:5175/?window=main
```

Check these visible conditions:

- The header has canvas-warm background and small red/blue/yellow/black geometric marks.
- The status/subtitle chip does not cover the geometric marks.
- The main chat background has no gradient, texture, or heavy black outline.
- Empty state, user message, assistant message, approval card, and capacity card are visually distinct.
- Capacity details remain collapsed by default.
- Fullscreen detail and screenshot dialogs still have close controls.
- No text overlaps or spills outside buttons/cards at desktop width.

- [ ] **Step 7: Stop the dev server**

Stop the `npm run dev -- --port 5175` process with `Ctrl-C`.

Expected: no long-running shell session remains.

- [ ] **Step 8: Commit any verification fixes**

If Step 6 required code fixes, commit only those files:

```bash
git add apps/desktop/src/app.css apps/desktop/src/lib/components/main/ConversationWorkspace.svelte apps/desktop/src/lib/components/main/CapacityCallCard.svelte apps/desktop/src/lib/components/main/CapacityCallDetails.svelte apps/desktop/src/lib/components/common/CommandComposer.svelte apps/desktop/src/lib/components/main/visualStyle.test.ts
git commit -m "fix(desktop): resolve main chat visual inspection issues"
```

If Step 6 required no code fixes, skip this commit.

- [ ] **Step 9: Final branch status**

Run:

```bash
git status --short --branch
git log --oneline --decorate -n 6
```

Expected: worktree is clean, branch is `feature/desktop-suprematist-main-chat`, and the task commits are visible on top of `main`.

## Self-Review

- Spec coverage: Tasks 1-4 cover the first-round scope: tokens, global classes, `ConversationWorkspace`, `CapacityCallCard`, `CapacityCallDetails`, and `CommandComposer`. Task 5 covers visual inspection, build, and desktop observe plan.
- Explicit overlap guard: Task 2 adds a test and CSS rule so the `turns`/status chip stays separate from the top-right geometric marks.
- Scope control: `AgentWorkspaceShell`, `MiniWindow`, `AgentGroupWorkspace`, and dev/snapshot surfaces are intentionally excluded from first-round implementation.
- Contract safety: No task changes chat data, SSE handling, approval resolution, capacity execution, or artifact loading.
- Verification: Each implementation task has a focused test, `npm run check`, and a commit. The final task runs full `npm test`, `npm run check`, `npm run build`, and browser inspection.
