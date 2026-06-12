<script lang="ts">
  import type { DesktopCapacityDetailSection } from '../../client/agentClient';
  import {
    capacityDetailLabel,
    formatCapacityDetailContent,
    researchSourcePreviewsForDetailSection
  } from '../../view/capacityCallView';

  let { details, fullscreen = false } = $props<{
    details: DesktopCapacityDetailSection[];
    fullscreen?: boolean;
  }>();
</script>

{#if details.length === 0}
  <p class="iso-card-raised px-3 py-2 text-sm text-isotope-muted">
    本次动作没有返回详情载荷。
  </p>
{:else}
  <div class="space-y-3">
    {#each details as section}
      {@const sourcePreviews = researchSourcePreviewsForDetailSection(section)}
      <section class="iso-card-raised overflow-hidden">
        <div class="border-b border-isotope-line bg-isotope-panel px-3 py-2 text-xs font-semibold uppercase text-isotope-muted">
          {capacityDetailLabel(section.label)}
        </div>
        {#if sourcePreviews.length}
          <ol class="divide-y divide-isotope-line bg-isotope-panel">
            {#each sourcePreviews as source, index}
              <li class="px-3 py-2.5">
                <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div class="min-w-0">
                    <div class="flex flex-wrap items-center gap-2 text-[11px] font-semibold uppercase text-isotope-muted">
                      <span>来源 {source.providerRank ?? index + 1}</span>
                      {#if source.sourceId}
                        <span>{source.sourceId}</span>
                      {/if}
                    </div>
                    <a
                      class="mt-1 block break-words text-sm font-semibold text-isotope-blue hover:underline"
                      href={source.url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {source.title}
                    </a>
                  </div>
                  <a
                    class="break-all text-xs leading-5 text-isotope-muted hover:text-isotope-blue"
                    href={source.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {source.url}
                  </a>
                </div>
                {#if source.snippet}
                  <p class="mt-2 text-xs leading-5 text-isotope-text">{source.snippet}</p>
                {/if}
                {#if source.whyUsed}
                  <p class="mt-1 text-[11px] leading-5 text-isotope-muted">{source.whyUsed}</p>
                {/if}
              </li>
            {/each}
          </ol>
          <details class="border-t border-isotope-line bg-isotope-panel px-3 py-2">
            <summary class="cursor-pointer text-xs font-semibold text-isotope-muted">结果原文</summary>
            <pre
              class={[
                'mt-2 overflow-auto whitespace-pre-wrap break-words rounded-panel bg-isotope-canvas p-3 text-xs leading-5 text-isotope-text',
                fullscreen ? 'max-h-[70vh]' : 'max-h-64'
              ]}
            >{formatCapacityDetailContent(section)}</pre>
          </details>
        {:else}
          <pre
            class={[
              'overflow-auto whitespace-pre-wrap break-words rounded-panel bg-isotope-canvas px-3 py-2 text-xs leading-5 text-isotope-text',
              fullscreen ? 'max-h-[70vh]' : 'max-h-64'
            ]}
          >{formatCapacityDetailContent(section)}</pre>
        {/if}
      </section>
    {/each}
  </div>
{/if}
