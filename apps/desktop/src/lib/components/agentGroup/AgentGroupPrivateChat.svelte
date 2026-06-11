<script lang="ts">
  import type { PrivateChatMessage } from '../../contracts/agentGroup';

  let { messages } = $props<{ messages: PrivateChatMessage[] }>();
</script>

<section class="border-l border-isotope-line bg-isotope-panel px-4 py-4" aria-label="AI human private chat">
  <div class="text-xs font-semibold uppercase text-isotope-muted">AI / 人</div>
  <div class="mt-3 space-y-3">
    {#if messages.length === 0}
      <div class="border border-isotope-line bg-white px-3 py-2 text-sm text-isotope-muted">
        暂无私聊消息。
      </div>
    {:else}
      {#each messages as message (message.message_id)}
        <article class="border border-isotope-line bg-white px-3 py-2">
          <div class="text-xs font-semibold text-isotope-muted">{message.role}</div>
          <p class="mt-1 whitespace-pre-wrap break-words text-sm leading-6 text-isotope-text">
            {message.content}
          </p>
        </article>
      {/each}
    {/if}
  </div>
</section>
