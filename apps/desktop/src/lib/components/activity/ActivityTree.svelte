<script lang="ts">
  import type { ActivityNode } from '../../contracts/isotope';
  import SourceBadge from '../common/SourceBadge.svelte';
  import { buildActivityTreeRows } from './tree';

  let {
    nodes,
    selectedId = null,
    onSelect
  } = $props<{
    nodes: ActivityNode[];
    selectedId?: string | null;
    onSelect: (id: string) => void;
  }>();

  const rows = $derived(buildActivityTreeRows(nodes, selectedId));
</script>

<nav class="space-y-1" aria-label="Activity tree">
  {#each rows as row (row.node.id)}
    <button
      type="button"
      class="flex w-full items-center justify-between gap-2 border border-transparent px-2 py-1.5 text-left text-sm hover:border-isotope-line hover:bg-isotope-panel"
      class:border-isotope-line={row.selected}
      class:bg-isotope-panel={row.selected}
      style={`padding-left: ${8 + row.depth * 14}px`}
      onclick={() => onSelect(row.node.id)}
    >
      <span class="min-w-0">
        <span class="block truncate font-medium">{row.node.title}</span>
        <span class="block text-xs text-isotope-muted">{row.node.kind} · {row.node.status}</span>
      </span>
      <SourceBadge source={row.node.source} />
    </button>
  {/each}
</nav>
