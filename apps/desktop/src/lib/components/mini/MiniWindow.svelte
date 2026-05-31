<script lang="ts">
  import type { IsotopeSnapshot } from '../../contracts/isotope';
  import { buildMiniWindowSurfaceClass, type ComponentSurface } from '../../window/windowSurface';
  import {
    buildMiniWindowView,
    buildMockSubmitPreview,
    type MiniSubmitMode
  } from '../../view/miniWindowView';
  import { windowDragClient } from '../../window/windowDragClient';
  import CommandComposer from '../common/CommandComposer.svelte';
  import QuickActionArea from '../common/QuickActionArea.svelte';
  import SourceBadge from '../common/SourceBadge.svelte';

  let { snapshot, surface = 'dev', onOpenMain, onClose } = $props<{
    snapshot: IsotopeSnapshot;
    surface?: ComponentSurface;
    onOpenMain: () => void;
    onClose: () => void;
  }>();

  let submitMode = $state<MiniSubmitMode>('mock');
  let submitPreview = $state('No command submitted yet.');
  const view = $derived(buildMiniWindowView(snapshot, submitMode));

  function submitMockCommand(text: string) {
    const result = buildMockSubmitPreview(text);
    submitMode = result.mode;
    submitPreview = result.preview;
  }

  function startWindowDrag(event: PointerEvent) {
    if (surface !== 'window' || event.button !== 0) return;
    if (event.target instanceof Element && event.target.closest('button')) return;
    void windowDragClient.startDragging();
  }
</script>

<section
  class={`${buildMiniWindowSurfaceClass(surface)} flex flex-col`}
  aria-label="Isotope MiniWindow preview"
>
  <header
    class={surface === 'window'
      ? 'flex cursor-move select-none items-start justify-between gap-3 border-b border-isotope-line pb-3'
      : 'flex items-start justify-between gap-3 border-b border-isotope-line pb-3'}
    role="presentation"
    aria-label="MiniWindow header"
    onpointerdown={startWindowDrag}
  >
    <div class="min-w-0 flex-1">
      <div class="flex items-center gap-2">
        <span class="h-2 w-2 bg-isotope-done" aria-hidden="true"></span>
        <div class="truncate text-sm font-semibold">{view.title}</div>
      </div>
      <div class="mt-1 text-xs leading-4 text-isotope-muted">{view.conversationLabel} · {view.statusLine}</div>
    </div>
    <div class="flex items-center gap-2">
      <SourceBadge source={snapshot.source} />
      <button class="cursor-pointer border border-isotope-line bg-white px-2 py-1 text-xs font-medium" type="button" onclick={onOpenMain}>
        Main
      </button>
      <button class="cursor-pointer border border-isotope-line bg-white px-2 py-1 text-xs" type="button" aria-label="Close mini" onclick={onClose}>
        x
      </button>
    </div>
  </header>

  <div class="mt-3 min-h-0 flex-1 overflow-y-auto">
    <div class="flex items-start gap-2">
      <div class="grid h-7 w-7 shrink-0 place-items-center border border-isotope-line bg-isotope-bg text-xs font-semibold text-isotope-running">
        AI
      </div>
      <div class="min-w-0 flex-1 border border-isotope-line bg-isotope-bg px-3 py-2">
        <div class="text-xs font-semibold uppercase text-isotope-muted">{view.agentTitle}</div>
        <p class="mt-1 text-sm leading-5 text-isotope-text">
          I am tracking <span class="font-medium">{view.activeGoalTitle}</span>.
        </p>
        <div class="mt-2 grid grid-cols-3 gap-2 text-xs">
          <div class="border border-isotope-line bg-white px-2 py-1">
            <span class="block text-isotope-muted">Running</span>
            <span class="font-semibold">{view.counts.runningAgents}</span>
          </div>
          <div class="border border-isotope-line bg-white px-2 py-1">
            <span class="block text-isotope-muted">Attention</span>
            <span class="font-semibold">{view.counts.needsAttention}</span>
          </div>
          <div class="border border-isotope-line bg-white px-2 py-1">
            <span class="block text-isotope-muted">Approvals</span>
            <span class="font-semibold">{view.counts.approvals}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="mt-3 flex flex-wrap gap-2">
      {#each view.suggestedPrompts as prompt}
        <button
          class="border border-isotope-line bg-white px-2 py-1 text-left text-xs text-isotope-muted hover:border-isotope-running hover:text-isotope-text"
          type="button"
          onclick={() => submitMockCommand(prompt)}
        >
          {prompt}
        </button>
      {/each}
    </div>
  </div>

  <div class="mt-3">
    <CommandComposer placeholder="Message Isotope" disabled={submitMode === 'disabled'} onSubmit={submitMockCommand} />
  </div>

  {#if submitPreview !== 'No command submitted yet.'}
    <p class="mt-2 border border-isotope-line bg-isotope-panel px-2 py-1 text-xs text-isotope-muted">
      {submitPreview}
    </p>
  {/if}

  <div class="mt-3">
    <QuickActionArea />
  </div>
</section>
