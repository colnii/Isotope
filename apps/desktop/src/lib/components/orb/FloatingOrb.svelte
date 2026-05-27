<script lang="ts">
  import type { IsotopeSnapshot } from '../../contracts/isotope';
  import { buildFloatingOrbView } from '../../view/orbView';
  import SourceBadge from '../common/SourceBadge.svelte';

  let { snapshot, quietMode = false, surface = 'dev', onOpenMini = () => {} } = $props<{
    snapshot: IsotopeSnapshot;
    quietMode?: boolean;
    surface?: 'dev' | 'window';
    onOpenMini?: () => void;
  }>();

  const view = $derived(buildFloatingOrbView(snapshot));
</script>

<div
  class={surface === 'dev'
    ? 'fixed bottom-5 right-5 z-20 flex flex-col items-end gap-2'
    : 'grid h-full min-h-[96px] w-full place-items-center gap-2 p-2'}
  aria-label="Isotope floating orb preview"
>
  <button
    type="button"
    class="relative grid h-16 w-16 place-items-center rounded-full border border-isotope-line bg-white text-sm font-semibold text-isotope-text shadow-lg transition hover:scale-[1.03] focus:outline-none focus:ring-2 focus:ring-isotope-running"
    class:animate-pulse={!quietMode && view.needsAttention > 0}
    aria-label={`Isotope orb: ${view.title}`}
    title={view.title}
    onclick={onOpenMini}
  >
    <span>Iso</span>
    {#if view.attentionText}
      <span class="absolute -right-1 -top-1 min-w-5 rounded-full bg-isotope-attention px-1 text-xs text-white">
        {view.attentionText}
      </span>
    {/if}
  </button>
  <div
    class={surface === 'dev'
      ? 'max-w-44 border border-isotope-line bg-white/95 px-2 py-1 text-right text-xs shadow-sm'
      : 'max-w-24 text-center text-[10px] leading-tight text-isotope-muted'}
  >
    <div class="truncate font-medium">{view.label}</div>
    <div class="mt-1 flex items-center justify-end gap-1 text-isotope-muted">
      <span>{view.status}</span>
      <SourceBadge source={view.source} />
    </div>
  </div>
</div>
