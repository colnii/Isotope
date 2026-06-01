<script lang="ts">
  import CommandComposer from '../common/CommandComposer.svelte';
  import type { DesktopChatMessage } from '../../stores/appState';
  import CapacityCallCard from './CapacityCallCard.svelte';

  let {
    eyebrow,
    title,
    subtitle,
    body,
    emptyTitle,
    emptyBody,
    composerPlaceholder,
    chatMessages = [],
    chatError = null,
    isAsking = false,
    onAsk
  } = $props<{
    eyebrow: string;
    title: string;
    subtitle: string;
    body: string;
    emptyTitle: string;
    emptyBody: string;
    composerPlaceholder: string;
    chatMessages?: DesktopChatMessage[];
    chatError?: string | null;
    isAsking?: boolean;
    onAsk: (question: string) => void;
  }>();
</script>

<section class="flex min-h-screen min-w-0 flex-col bg-white" aria-label="Conversation workspace">
  <header class="border-b border-isotope-line px-7 py-5">
    <div class="flex items-center justify-between gap-4">
      <div class="min-w-0">
        <div class="text-xs font-semibold uppercase text-isotope-muted">{eyebrow}</div>
        <h1 class="mt-1 truncate text-xl font-semibold text-isotope-text">{title}</h1>
      </div>
      <div class="shrink-0 border border-isotope-line bg-isotope-panel px-2 py-1 text-xs text-isotope-muted">
        {subtitle}
      </div>
    </div>
  </header>

  <div class="min-h-0 flex-1 overflow-y-auto px-7 py-6" aria-live="polite">
    {#if chatMessages.length === 0}
      <div class="mx-auto flex max-w-3xl flex-col gap-4">
        <article class="flex items-start gap-3">
          <div class="grid h-9 w-9 shrink-0 place-items-center border border-isotope-line bg-isotope-bg text-xs font-semibold text-isotope-running">
            AI
          </div>
          <div class="min-w-0 flex-1 border border-isotope-line bg-isotope-bg px-4 py-3">
            <div class="text-sm font-semibold text-isotope-text">{emptyTitle}</div>
            <p class="mt-2 text-sm leading-6 text-isotope-muted">{emptyBody}</p>
            <div class="mt-3 border-l-2 border-isotope-line pl-3 text-sm leading-6 text-isotope-muted">
              {body}
            </div>
          </div>
        </article>
      </div>
    {:else}
      <div class="mx-auto flex max-w-3xl flex-col gap-5">
        {#each chatMessages as message (message.id)}
          <article class:flex-row-reverse={message.role === 'user'} class="flex items-start gap-3">
            <div
              class={[
                'grid h-8 w-8 shrink-0 place-items-center border text-xs font-semibold',
                message.role === 'user'
                  ? 'border-isotope-running bg-isotope-running text-white'
                  : 'border-isotope-line bg-isotope-bg text-isotope-running'
              ]}
            >
              {message.role === 'user' ? 'You' : 'AI'}
            </div>
            <div
              class={[
                'max-w-[78%] border px-4 py-3 text-sm leading-6 shadow-sm',
                message.role === 'user'
                  ? 'border-isotope-running bg-isotope-running text-white'
                  : 'border-isotope-line bg-isotope-bg text-isotope-text'
              ]}
            >
              <div class={message.role === 'user' ? 'mb-1 text-xs font-semibold text-white/80' : 'mb-1 text-xs font-semibold text-isotope-muted'}>
                {message.role === 'user' ? 'You' : 'Isotope'}
              </div>
              {#if message.content}
                <p>{message.content}</p>
              {:else}
                <p class="text-isotope-muted">...</p>
              {/if}
              {#if message.role === 'assistant' && message.capacityCalls?.length}
                <div class="mt-3 space-y-2">
                  {#each message.capacityCalls as call (call.id)}
                    <CapacityCallCard {call} />
                  {/each}
                </div>
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

  <div class="border-t border-isotope-line bg-white px-7 py-4">
    <div class="mx-auto max-w-3xl">
    {#if chatError}
      <div class="mb-3 border border-isotope-error/40 bg-white px-3 py-2 text-xs text-isotope-error" role="alert">
        {chatError}
      </div>
    {/if}
    <CommandComposer placeholder={composerPlaceholder} disabled={isAsking} onSubmit={onAsk} />
    </div>
  </div>
</section>
