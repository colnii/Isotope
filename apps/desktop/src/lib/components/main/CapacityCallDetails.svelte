<script lang="ts">
  import type { DesktopCapacityDetailSection } from '../../client/agentClient';
  import { capacityDetailLabel, formatCapacityDetailContent } from '../../view/capacityCallView';

  let { details, fullscreen = false } = $props<{
    details: DesktopCapacityDetailSection[];
    fullscreen?: boolean;
  }>();
</script>

{#if details.length === 0}
  <p class="border border-isotope-line bg-isotope-panel px-3 py-2 text-sm text-isotope-muted">
    本次动作没有返回详情载荷。
  </p>
{:else}
  <div class="space-y-3">
    {#each details as section}
      <section class="border border-isotope-line bg-isotope-panel">
        <div class="border-b border-isotope-line px-3 py-2 text-xs font-semibold uppercase text-isotope-muted">
          {capacityDetailLabel(section.label)}
        </div>
        <pre
          class={[
            'overflow-auto whitespace-pre-wrap break-words px-3 py-2 text-xs leading-5 text-isotope-text',
            fullscreen ? 'max-h-[70vh]' : 'max-h-64'
          ]}
        >{formatCapacityDetailContent(section)}</pre>
      </section>
    {/each}
  </div>
{/if}
