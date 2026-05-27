<script lang="ts">
  import type { ActivityNode } from '../../contracts/isotope';

  let { activities, selectedId = null, onSelect } = $props<{
    activities: ActivityNode[];
    selectedId?: string | null;
    onSelect: (activityId: string) => void;
  }>();
</script>

<nav class="h-full border-r border-isotope-line bg-white/80 px-3 py-4" aria-label="Activity rail">
  <div class="text-xs font-semibold uppercase text-isotope-muted">Activities</div>
  <div class="mt-3 space-y-1">
    {#each activities as activity (activity.id)}
      <button
        class="block w-full truncate px-2 py-1.5 text-left text-sm text-isotope-muted hover:bg-isotope-panel hover:text-isotope-text"
        class:bg-isotope-panel={selectedId === activity.id}
        class:text-isotope-text={selectedId === activity.id}
        type="button"
        onclick={() => onSelect(activity.id)}
      >
        {activity.title}
      </button>
    {/each}
  </div>
</nav>
