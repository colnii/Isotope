<script lang="ts">
  import type { CodexTranscriptPage } from '../../contracts/agentGroup';

  let { transcript = null, showRaw = false, onToggleRaw } = $props<{
    transcript?: CodexTranscriptPage | null;
    showRaw?: boolean;
    onToggleRaw?: () => void;
  }>();
</script>

<section class="border-t border-isotope-line bg-white px-4 py-3" aria-label="Codex transcript">
  <div class="flex items-center justify-between gap-3">
    <div>
      <div class="text-xs font-semibold uppercase text-isotope-muted">Codex transcript</div>
      <div class="mt-1 text-sm font-semibold text-isotope-text">
        {transcript?.session_id ?? '未选择会话'}
      </div>
    </div>
    <button
      class="border border-isotope-line bg-isotope-panel px-3 py-1.5 text-xs font-semibold text-isotope-muted"
      type="button"
      onclick={() => onToggleRaw?.()}
    >
      {showRaw ? 'Readable' : 'Raw'}
    </button>
  </div>
  <div class="mt-3 max-h-80 overflow-auto border border-isotope-line bg-isotope-panel">
    {#if !transcript}
      <p class="px-3 py-2 text-sm text-isotope-muted">选择一个 Codex 成员查看 transcript。</p>
    {:else}
      {#each transcript.events as event (event.event_index)}
        <article class="border-b border-isotope-line px-3 py-2">
          <div class="flex flex-wrap items-center gap-2 text-[11px] font-semibold uppercase text-isotope-muted">
            <span>#{event.event_index}</span>
            <span>{event.kind}</span>
            {#if event.timestamp}<span>{event.timestamp}</span>{/if}
          </div>
          <pre class="mt-1 whitespace-pre-wrap break-words text-xs leading-5 text-isotope-text">{showRaw ? JSON.stringify(event.raw ?? event, null, 2) : event.text}</pre>
        </article>
      {/each}
    {/if}
  </div>
</section>
