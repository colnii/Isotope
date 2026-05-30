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
    void windowDragClient.startDragging();
  }
</script>

<section
  class={buildMiniWindowSurfaceClass(surface)}
  aria-label="Isotope MiniWindow preview"
>
  <header class="flex items-start justify-between gap-3">
    {#if surface === 'window'}
      <button
        type="button"
        class="min-w-0 flex-1 cursor-move select-none appearance-none border-0 bg-transparent p-0 text-left text-inherit focus:outline-none focus:ring-2 focus:ring-isotope-running"
        aria-label="Move MiniWindow"
        onpointerdown={startWindowDrag}
      >
        <div class="truncate text-sm font-semibold">{view.title}</div>
        <div class="mt-1 text-xs text-isotope-muted">submit: {view.submitMode}</div>
      </button>
    {:else}
      <div class="min-w-0 flex-1">
        <div class="truncate text-sm font-semibold">{view.title}</div>
        <div class="mt-1 text-xs text-isotope-muted">submit: {view.submitMode}</div>
      </div>
    {/if}
    <div class="flex items-center gap-2">
      <SourceBadge source={snapshot.source} />
      <button class="border border-isotope-line px-2 text-sm" type="button" onclick={onOpenMain}>
        Open Main
      </button>
      <button class="border border-isotope-line px-2 text-sm" type="button" aria-label="Close mini" onclick={onClose}>
        x
      </button>
    </div>
  </header>

  <div class="mt-3 grid grid-cols-3 gap-2 text-xs">
    <div class="bg-isotope-bg p-2">Running<br /><span class="font-semibold">{view.counts.runningAgents}</span></div>
    <div class="bg-isotope-bg p-2">Attention<br /><span class="font-semibold">{view.counts.needsAttention}</span></div>
    <div class="bg-isotope-bg p-2">Approvals<br /><span class="font-semibold">{view.counts.approvals}</span></div>
  </div>

  <div class="mt-3 border-t border-isotope-line pt-3">
    <div class="text-xs text-isotope-muted">Agent</div>
    <div class="truncate text-sm">{view.agentTitle}</div>
    <div class="mt-2 text-xs text-isotope-muted">Goal</div>
    <div class="truncate text-sm">{view.activeGoalTitle}</div>
  </div>

  <div class="mt-3">
    <CommandComposer disabled={submitMode === 'disabled'} onSubmit={submitMockCommand} />
  </div>

  <p class="mt-2 border border-isotope-line bg-isotope-panel px-2 py-1 text-xs text-isotope-muted">
    {submitPreview}
  </p>

  <div class="mt-3">
    <QuickActionArea />
  </div>
</section>
