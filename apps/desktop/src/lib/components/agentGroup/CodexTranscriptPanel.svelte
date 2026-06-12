<script lang="ts">
  import type { CodexTranscriptPage } from '../../contracts/agentGroup';
  import { formatTranscriptTimestamp, readableTranscriptEvents } from './transcriptView';

  let { transcript = null, showRaw = false, onToggleRaw } = $props<{
    transcript?: CodexTranscriptPage | null;
    showRaw?: boolean;
    onToggleRaw?: () => void;
  }>();

  const readableEvents = $derived(readableTranscriptEvents(transcript));
</script>

<section class="border-t border-isotope-line bg-white px-4 py-3" aria-label="Codex 会话记录">
  <div class="flex items-center justify-between gap-3">
    <div>
      <div class="text-xs font-semibold text-isotope-muted">
        {showRaw ? 'Codex 原始事件' : 'Codex 终端视图'}
      </div>
      <div class="mt-1 text-sm font-semibold text-isotope-text">
        {transcript?.session_id ?? '未选择会话'}
      </div>
      {#if transcript}
        <div class="mt-1 text-xs text-isotope-muted">
          {formatTranscriptTimestamp(transcript.last_event_at)} · #{transcript.offset} - #{Math.max(transcript.next_offset - 1, transcript.offset)}
        </div>
      {/if}
    </div>
    <button
      class="border border-isotope-line bg-isotope-panel px-3 py-1.5 text-xs font-semibold text-isotope-muted"
      type="button"
      onclick={() => onToggleRaw?.()}
    >
      {showRaw ? '可读视图' : '原始数据'}
    </button>
  </div>
  <div class="mt-3 max-h-96 overflow-auto border border-isotope-line bg-isotope-panel">
    {#if !transcript}
      <p class="px-3 py-2 text-sm text-isotope-muted">选择一个 Codex 成员查看会话记录。</p>
    {:else if showRaw}
      {#each transcript.events as event (event.event_index)}
        <article class="border-b border-isotope-line px-3 py-2">
          <div class="flex flex-wrap items-center gap-2 text-[11px] font-semibold text-isotope-muted">
            <span>#{event.event_index}</span>
            <span>{event.kind}</span>
            {#if event.timestamp}<span>{formatTranscriptTimestamp(event.timestamp)}</span>{/if}
          </div>
          <pre class="mt-1 whitespace-pre-wrap break-words text-xs leading-5 text-isotope-text">{JSON.stringify(event.raw ?? event, null, 2)}</pre>
        </article>
      {/each}
    {:else if readableEvents.length === 0}
      <p class="px-3 py-2 text-sm text-isotope-muted">这页没有可读终端事件，可切换到原始数据查看。</p>
    {:else}
      {#each readableEvents as event (event.event_index)}
        <article class="border-b border-isotope-line bg-[#111820] px-3 py-2 text-[#d6e0ea]">
          <div class="flex flex-wrap items-center gap-2 font-mono text-[11px] text-[#93a4b7]">
            <span>#{event.event_index}</span>
            <span>{event.role ?? event.title}</span>
            {#if event.timestamp}<span>{formatTranscriptTimestamp(event.timestamp)}</span>{/if}
          </div>
          <pre class="mt-1 whitespace-pre-wrap break-words font-mono text-xs leading-5">{event.text}</pre>
        </article>
      {/each}
    {/if}
  </div>
</section>
