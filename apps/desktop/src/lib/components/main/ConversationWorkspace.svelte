<script lang="ts">
  import CommandComposer from '../common/CommandComposer.svelte';
  import type { DesktopChatMessage } from '../../stores/appState';

  let {
    title,
    subtitle,
    body,
    chatMessages = [],
    chatError = null,
    isAsking = false,
    onAsk
  } = $props<{
    title: string;
    subtitle: string;
    body: string;
    chatMessages?: DesktopChatMessage[];
    chatError?: string | null;
    isAsking?: boolean;
    onAsk: (question: string) => void;
  }>();
</script>

<section class="flex min-h-screen min-w-0 flex-col px-8 py-6" aria-label="Conversation workspace">
  <div class="text-xs uppercase text-isotope-muted">{subtitle}</div>
  <h1 class="mt-2 max-w-3xl text-2xl font-semibold text-isotope-text">{title}</h1>

  <div class="mt-6 min-h-0 flex-1 overflow-y-auto pr-2" aria-live="polite">
    {#if chatMessages.length === 0}
      <div class="max-w-3xl border-l-2 border-isotope-line pl-4 text-sm leading-6 text-isotope-muted">
        {body}
      </div>
    {:else}
      <div class="flex max-w-3xl flex-col gap-4">
        {#each chatMessages as message (message.id)}
          <article class:flex-row-reverse={message.role === 'user'} class="flex">
            <div
              class={[
                'max-w-[78%] border px-4 py-3 text-sm leading-6 shadow-sm',
                message.role === 'user'
                  ? 'border-isotope-running bg-isotope-running text-white'
                  : 'border-isotope-line bg-white text-isotope-text'
              ]}
            >
              {#if message.content}
                <p>{message.content}</p>
              {:else}
                <p class="text-isotope-muted">...</p>
              {/if}
              {#if message.role === 'assistant' && (message.provider || message.model)}
                <div class="mt-2 text-[11px] uppercase text-isotope-muted">
                  {[message.provider, message.model].filter(Boolean).join(' / ')}
                </div>
              {/if}
            </div>
          </article>
        {/each}
      </div>
    {/if}
  </div>

  <div class="mt-5 max-w-3xl border-t border-isotope-line pt-4">
    {#if chatError}
      <div class="mb-3 border border-isotope-error/40 bg-white px-3 py-2 text-xs text-isotope-error" role="alert">
        {chatError}
      </div>
    {/if}
    <CommandComposer placeholder="问当前 loop 状态" disabled={isAsking} onSubmit={onAsk} />
  </div>
</section>
