<script lang="ts">
  import type { DataSourceInfo, IsotopeEvent } from '../../contracts/isotope';
  import EventStream from '../events/EventStream.svelte';
  import DebugSourceBadge from '../dev/DebugSourceBadge.svelte';

  let { title, summary, source, events } = $props<{
    title: string;
    summary: string;
    source: DataSourceInfo;
    events: IsotopeEvent[];
  }>();
</script>

<aside class="h-full border-l border-isotope-line bg-white/75 px-4 py-5" aria-label="Inspector dock">
  <div class="flex items-center justify-between gap-3">
    <h2 class="text-sm font-semibold">{title}</h2>
    <DebugSourceBadge {source} />
  </div>
  <p class="mt-3 text-sm leading-5 text-isotope-muted">{summary}</p>
  <div class="mt-5">
    <EventStream {events} />
  </div>
</aside>
