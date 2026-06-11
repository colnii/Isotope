<script lang="ts">
  import type { AgentGroupMessage } from '../../contracts/agentGroup';

  let { messages } = $props<{ messages: AgentGroupMessage[] }>();
</script>

<section class="min-h-0 flex-1 overflow-y-auto px-5 py-4" aria-label="Agent group public stream">
  {#if messages.length === 0}
    <div class="border border-isotope-line bg-isotope-panel px-4 py-3 text-sm text-isotope-muted">
      还没有公共群聊消息。
    </div>
  {:else}
    <div class="space-y-3">
      {#each messages as message (message.message_id)}
        <article class="border border-isotope-line bg-white px-4 py-3">
          <div class="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase text-isotope-muted">
            <span>{message.from_member}</span>
            <span>{message.message_type}</span>
            {#if message.to_member}<span>to {message.to_member}</span>{/if}
          </div>
          <p class="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-isotope-text">
            {message.summary}
          </p>
        </article>
      {/each}
    </div>
  {/if}
</section>
