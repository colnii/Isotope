<script lang="ts">
  import type { IsotopeSnapshot } from '../../contracts/isotope';
  import type { DesktopChatMessage } from '../../stores/appState';
  import { buildMiniWindowSurfaceClass, type ComponentSurface } from '../../window/windowSurface';
  import { buildMiniWindowView, type MiniSubmitMode } from '../../view/miniWindowView';
  import { windowDragClient } from '../../window/windowDragClient';
  import CommandComposer from '../common/CommandComposer.svelte';

  let {
    snapshot,
    surface = 'dev',
    chatMessages = [],
    chatError = null,
    isAsking = false,
    onAsk,
    onOpenMain,
    onClose
  } = $props<{
    snapshot: IsotopeSnapshot;
    surface?: ComponentSurface;
    chatMessages?: DesktopChatMessage[];
    chatError?: string | null;
    isAsking?: boolean;
    onAsk: (question: string) => void;
    onOpenMain: () => void;
    onClose: () => void;
  }>();

  let submitMode = $state<MiniSubmitMode>('mock');
  const view = $derived(buildMiniWindowView(snapshot, submitMode));
  const visibleMessages = $derived(chatMessages.slice(-3));

  function startWindowDrag(event: PointerEvent) {
    if (surface !== 'window' || event.button !== 0) return;
    if (event.target instanceof Element && event.target.closest('button')) return;
    void windowDragClient.startDragging();
  }
</script>

<section
  class={`${buildMiniWindowSurfaceClass(surface)} flex flex-col`}
  aria-label="Isotope 迷你窗口预览"
>
  <header
    class={surface === 'window'
      ? 'flex cursor-move select-none items-start justify-between gap-3 border-b border-isotope-line pb-3'
      : 'flex items-start justify-between gap-3 border-b border-isotope-line pb-3'}
    role="presentation"
    aria-label="迷你窗口标题栏"
    onpointerdown={startWindowDrag}
  >
    <div class="min-w-0 flex-1">
      <div class="flex items-center gap-2">
        <div class="truncate text-sm font-semibold">{view.title}</div>
      </div>
      <div class="mt-1 text-xs leading-4 text-isotope-muted">{view.conversationLabel}</div>
    </div>
    <div class="flex items-center gap-2">
      <button class="cursor-pointer border border-isotope-line bg-white px-2 py-1 text-xs font-medium" type="button" onclick={onOpenMain}>
        主窗口
      </button>
      <button class="cursor-pointer border border-isotope-line bg-white px-2 py-1 text-xs" type="button" aria-label="关闭迷你窗口" onclick={onClose}>
        x
      </button>
    </div>
  </header>

  <div class="mt-3 min-h-0 flex-1 overflow-y-auto">
    {#if visibleMessages.length === 0}
      <div class="border border-isotope-line bg-isotope-bg px-3 py-2">
        <div class="text-xs font-semibold uppercase text-isotope-muted">AI</div>
        <p class="mt-1 text-sm leading-5 text-isotope-text">
          向 Isotope 提问；执行动作时，过程会显示在主对话中。
        </p>
      </div>
    {:else}
      <div class="space-y-2">
        {#each visibleMessages as message (message.id)}
          <article class="border border-isotope-line bg-isotope-bg px-3 py-2">
            <div class="text-xs font-semibold uppercase text-isotope-muted">
              {message.role === 'user' ? '你' : 'Isotope'}
            </div>
            <p class="mt-1 max-h-16 overflow-hidden text-sm leading-5 text-isotope-text">
              {message.content || '...'}
            </p>
            {#if message.capacityCalls?.length}
              <div class="mt-2 text-xs text-isotope-muted">
                {message.capacityCalls.length} 次动作
              </div>
            {/if}
          </article>
        {/each}
      </div>
    {/if}
  </div>

  <div class="mt-3">
    <CommandComposer placeholder={view.composerPlaceholder} disabled={isAsking || submitMode === 'disabled'} onSubmit={onAsk} />
  </div>

  {#if chatError}
    <p class="mt-2 border border-isotope-error/40 bg-white px-2 py-1 text-xs text-isotope-error" role="alert">
      {chatError}
    </p>
  {/if}
</section>
