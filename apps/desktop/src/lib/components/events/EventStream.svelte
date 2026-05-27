<script lang="ts">
  import type { IsotopeEvent } from '../../contracts/isotope';
  import { buildEventStreamView } from '../../view/eventStreamView';
  import SourceBadge from '../common/SourceBadge.svelte';

  let { events } = $props<{
    events: IsotopeEvent[];
  }>();

  const view = $derived(buildEventStreamView(events));
</script>

<section class="border-t border-isotope-line pt-4" aria-label="EventStream static contract shell">
  <div class="flex items-center justify-between gap-3">
    <h3 class="text-xs font-semibold uppercase text-isotope-muted">Event stream</h3>
    <span class="text-xs text-isotope-muted">static contract</span>
  </div>

  {#if view.empty}
    <p class="mt-2 border border-isotope-line bg-isotope-panel p-2 text-sm text-isotope-muted">
      {view.emptyMessage}
    </p>
  {:else}
    <ol class="mt-2 space-y-2">
      {#each view.items as event (event.id)}
        <li class="border border-isotope-line p-2 text-sm">
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <div class="truncate font-medium">{event.title}</div>
              <div class="mt-1 text-xs text-isotope-muted">{event.type} · {event.createdAt}</div>
            </div>
            <SourceBadge source={event.source} />
          </div>
          {#if event.summary}
            <p class="mt-2 text-xs text-isotope-muted">{event.summary}</p>
          {/if}
        </li>
      {/each}
    </ol>
  {/if}
</section>
