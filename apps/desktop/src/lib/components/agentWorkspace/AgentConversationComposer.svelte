<script lang="ts">
  import type { WorkspaceConversationKind } from '../../contracts/agentWorkspace';

  let {
    selectedConversationKind,
    selectedConversationId = null,
    currentRunIsActive = false,
    composerText = $bindable(''),
    actionError = null,
    isSending = false,
    onSendMessage,
    onStopCurrentRun
  } = $props<{
    selectedConversationKind: WorkspaceConversationKind;
    selectedConversationId?: string | null;
    currentRunIsActive?: boolean;
    composerText: string;
    actionError?: string | null;
    isSending?: boolean;
    onSendMessage: (mode: 'queue' | 'interrupt') => void;
    onStopCurrentRun: () => void;
  }>();

  const composerIsEmpty = $derived(composerText.trim().length === 0);
</script>

<footer class="border-t border-isotope-line bg-white px-5 py-4">
  {#if actionError}
    <div class="mb-3 border border-isotope-error/40 bg-white px-3 py-2 text-xs text-isotope-error" role="alert">
      {actionError}
    </div>
  {/if}
  <div class="flex gap-2">
    <input
      class="min-w-0 flex-1 border border-isotope-line px-3 py-2 text-sm"
      bind:value={composerText}
      placeholder={selectedConversationKind === 'channel' ? '发送到当前群聊' : '发送给协调 AI'}
      disabled={!selectedConversationId || isSending}
    />
    {#if currentRunIsActive && composerIsEmpty}
      <button
        class="border border-isotope-error bg-isotope-error px-4 py-2 text-sm font-semibold text-white"
        type="button"
        onclick={() => onStopCurrentRun()}
      >
        停止
      </button>
    {:else if currentRunIsActive}
      <button
        class="border border-isotope-line bg-white px-4 py-2 text-sm font-semibold text-isotope-muted"
        type="button"
        disabled={isSending}
        onclick={() => onSendMessage('queue')}
      >
        排队
      </button>
      <button
        class="border border-isotope-running bg-isotope-running px-4 py-2 text-sm font-semibold text-white"
        type="button"
        disabled={isSending}
        onclick={() => onSendMessage('interrupt')}
      >
        打断
      </button>
    {:else}
      <button
        class="border border-isotope-running bg-isotope-running px-4 py-2 text-sm font-semibold text-white"
        type="button"
        disabled={!composerText.trim() || isSending}
        onclick={() => onSendMessage('queue')}
      >
        发送
      </button>
    {/if}
  </div>
</footer>
