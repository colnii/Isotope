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
  const orbButtonClass = $derived(
    surface === 'window'
      ? 'relative grid h-16 w-16 cursor-move select-none place-items-center rounded-full border border-white/30 bg-teal-600 text-lg font-bold text-white outline-none'
      : 'relative grid h-16 w-16 place-items-center rounded-full border border-isotope-line bg-white text-sm font-semibold text-isotope-text shadow-lg transition hover:scale-[1.03] focus:outline-none focus:ring-2 focus:ring-inset focus:ring-isotope-running'
  );
  const attentionClass = $derived(
    surface === 'window'
      ? 'absolute right-1 top-1 grid h-4 min-w-4 place-items-center rounded-full bg-isotope-attention px-1 text-[10px] leading-none text-white'
      : 'absolute -right-1 -top-1 min-w-5 rounded-full bg-isotope-attention px-1 text-xs text-white'
  );

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
    class={orbButtonClass}
    class:animate-pulse={!quietMode && view.needsAttention > 0}
    aria-label={`Isotope orb: ${view.title}`}
    title={view.title}
    onpointerdown={startWindowDrag}
    onclick={onOpenMini}
  >
    <span>{surface === 'window' ? 'I' : 'Iso'}</span>
    {#if view.attentionText}
      <span class={attentionClass}>
        {view.attentionText}
      </span>
    {/if}
  </button>
</div>
