<script lang="ts">
  import type { DesktopCapacityCall } from '../../client/agentClient';
  import {
    capacityCallStatusLabel,
    capacityCallSummary
  } from '../../view/capacityCallView';
  import CapacityCallDetails from './CapacityCallDetails.svelte';

  let { call } = $props<{
    call: DesktopCapacityCall;
  }>();

  let expanded = $state(false);
  let fullscreen = $state(false);

  const statusLabel = $derived(capacityCallStatusLabel(call));
  const summary = $derived(capacityCallSummary(call));
  const statusClass = $derived(
    call.status === 'ok'
      ? 'border-isotope-done text-isotope-done'
      : call.status === 'running'
        ? 'border-isotope-running text-isotope-running'
        : call.status === 'error'
          ? 'border-isotope-attention text-isotope-attention'
          : 'border-isotope-line text-isotope-muted'
  );

  function closeFullscreen() {
    fullscreen = false;
  }

  function toggleExpanded() {
    expanded = !expanded;
  }

  function openFullscreen() {
    fullscreen = true;
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') closeFullscreen();
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<section class="border border-isotope-line bg-white text-isotope-text shadow-sm" aria-label={`Capacity call ${call.capacityId}`}>
  <div class="flex items-start justify-between gap-3 px-3 py-2">
    <div class="min-w-0">
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-xs font-semibold uppercase text-isotope-muted">Capacity</span>
        <span class={`border px-1.5 py-0.5 text-[11px] font-semibold uppercase ${statusClass}`}>{statusLabel}</span>
      </div>
      <div class="mt-1 truncate text-sm font-semibold">{call.title}</div>
      <div class="mt-1 break-words text-xs leading-5 text-isotope-muted">{summary}</div>
    </div>
    <div class="flex shrink-0 items-center gap-1">
      <button
        class="grid h-7 w-7 place-items-center border border-isotope-line bg-isotope-panel text-xs"
        type="button"
        title={expanded ? 'Collapse' : 'Expand'}
        aria-label={expanded ? 'Collapse capacity details' : 'Expand capacity details'}
        onclick={toggleExpanded}
      >
        {expanded ? '-' : '+'}
      </button>
      <button
        class="grid h-7 w-7 place-items-center border border-isotope-line bg-isotope-panel text-xs"
        type="button"
        title="Fullscreen"
        aria-label="Open capacity details fullscreen"
        onclick={openFullscreen}
      >
        []
      </button>
    </div>
  </div>

  {#if expanded}
    <div class="border-t border-isotope-line px-3 py-3">
      <CapacityCallDetails details={call.details} />
    </div>
  {/if}
</section>

{#if fullscreen}
  <div class="fixed inset-0 z-50 bg-isotope-text/35 p-4" role="dialog" aria-modal="true" aria-label={`Capacity details ${call.capacityId}`}>
    <section class="mx-auto flex h-full max-w-5xl flex-col border border-isotope-line bg-white shadow-xl">
      <header class="flex items-start justify-between gap-3 border-b border-isotope-line px-4 py-3">
        <div class="min-w-0">
          <div class="text-xs font-semibold uppercase text-isotope-muted">Capacity detail</div>
          <h2 class="mt-1 truncate text-lg font-semibold">{call.title}</h2>
          <p class="mt-1 text-sm text-isotope-muted">{summary}</p>
        </div>
        <button
          class="grid h-8 w-8 place-items-center border border-isotope-line bg-isotope-panel text-sm"
          type="button"
          aria-label="Close fullscreen capacity details"
          onclick={closeFullscreen}
        >
          x
        </button>
      </header>
      <div class="min-h-0 flex-1 overflow-auto p-4">
        <CapacityCallDetails details={call.details} fullscreen />
      </div>
    </section>
  </div>
{/if}
