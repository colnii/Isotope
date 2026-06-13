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

<footer class="iso-agent-composer">
  {#if actionError}
    <div class="iso-agent-error-card" role="alert">
      {actionError}
    </div>
  {/if}
  <div class="flex gap-2">
    <input
      class="iso-agent-input flex-1"
      bind:value={composerText}
      placeholder={selectedConversationKind === 'channel' ? '发送到当前群聊' : '发送给协调 AI'}
      disabled={!selectedConversationId || isSending}
    />
    {#if currentRunIsActive && composerIsEmpty}
      <button
        class="iso-agent-button-danger"
        type="button"
        onclick={() => onStopCurrentRun()}
      >
        停止
      </button>
    {:else if currentRunIsActive}
      <button
        class="iso-agent-button-secondary"
        type="button"
        disabled={isSending}
        onclick={() => onSendMessage('queue')}
      >
        排队
      </button>
      <button
        class="iso-agent-button-primary"
        type="button"
        disabled={isSending}
        onclick={() => onSendMessage('interrupt')}
      >
        打断
      </button>
    {:else}
      <button
        class="iso-agent-button-primary"
        type="button"
        disabled={!composerText.trim() || isSending}
        onclick={() => onSendMessage('queue')}
      >
        发送
      </button>
    {/if}
  </div>
</footer>
