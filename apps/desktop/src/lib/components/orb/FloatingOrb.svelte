<script lang="ts">
  import type { IsotopeSnapshot } from '../../contracts/isotope';
  import { buildFloatingOrbView } from '../../view/orbView';
  import { windowDragClient } from '../../window/windowDragClient';

  let { snapshot, quietMode = false, surface = 'dev', onOpenMini = () => {} } = $props<{
    snapshot: IsotopeSnapshot;
    quietMode?: boolean;
    surface?: 'dev' | 'window';
    onOpenMini?: () => void;
  }>();

  const view = $derived(buildFloatingOrbView(snapshot));

  function startWindowDrag(event: PointerEvent) {
    if (surface !== 'window' || event.button !== 0) return;
    void windowDragClient.startDragging();
  }
</script>

<div
  class={surface === 'dev'
    ? 'fixed bottom-5 right-5 z-20 flex flex-col items-end gap-2'
    : 'grid h-screen w-screen place-items-center bg-transparent p-0'}
  aria-label="Isotope floating orb preview"
>
  <button
    type="button"
    class="relative grid h-16 w-16 place-items-center rounded-full border border-isotope-line bg-white text-sm font-semibold text-isotope-text shadow-lg transition hover:scale-[1.03] focus:outline-none focus:ring-2 focus:ring-isotope-running"
    class:cursor-move={surface === 'window'}
    class:animate-pulse={!quietMode && view.needsAttention > 0}
    aria-label={`Isotope orb: ${view.title}`}
    title={view.title}
    onpointerdown={startWindowDrag}
    onclick={onOpenMini}
  >
    <span>Iso</span>
    {#if view.attentionText}
      <span class="absolute -right-1 -top-1 min-w-5 rounded-full bg-isotope-attention px-1 text-xs text-white">
        {view.attentionText}
      </span>
    {/if}
  </button>
</div>
