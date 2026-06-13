<script lang="ts">
  import type {
    AgentWorkspaceMember,
    WorkspaceConversationKind,
    WorkspaceConversationMessage
  } from '../../contracts/agentWorkspace';

  let {
    selectedConversationKind,
    conversationTitle,
    conversationSubtitle = '',
    currentMembersCount,
    currentMembers = [],
    currentMessages = [],
    isLoading = false,
    onRefresh
  } = $props<{
    selectedConversationKind: WorkspaceConversationKind;
    conversationTitle: string;
    conversationSubtitle?: string;
    currentMembersCount: number;
    currentMembers?: AgentWorkspaceMember[];
    currentMessages?: WorkspaceConversationMessage[];
    isLoading?: boolean;
    onRefresh: () => void;
  }>();

  function actorDisplayName(actorId: string): string {
    if (actorId === 'user') return '我';
    if (actorId === 'supervisor') return '系统';
    return (
      currentMembers.find((member: AgentWorkspaceMember) => member.member_id === actorId)?.display_name ||
      actorId
    );
  }
</script>

<main class="iso-agent-pane">
  <header class="iso-agent-pane-header">
    <div class="min-w-0">
      <div class="truncate text-lg font-semibold">
        {selectedConversationKind === 'channel' ? '# ' : ''}{conversationTitle}
      </div>
      <div class="mt-1 truncate text-xs text-isotope-muted">
        {conversationSubtitle || (selectedConversationKind === 'channel' ? `${currentMembersCount} 个成员` : '私聊')}
      </div>
    </div>
    <button
      class="iso-agent-button-secondary"
      type="button"
      onclick={() => onRefresh()}
    >
      刷新
    </button>
  </header>

  <div class="iso-agent-stream">
    {#if isLoading}
      <div class="iso-agent-panel px-3 py-2 text-sm text-isotope-muted">
        正在加载智能体工作区
      </div>
    {:else if currentMessages.length === 0}
      <div class="iso-agent-panel border-dashed px-3 py-3 text-sm text-isotope-muted">
        暂无消息
      </div>
    {:else}
      <div class="space-y-3">
        {#each currentMessages as message (message.message_id)}
          <article class="iso-agent-message">
            <div class="flex items-center justify-between gap-3">
              <div class="text-xs font-semibold text-isotope-muted">
                {actorDisplayName(message.from_actor)}
              </div>
              <time class="shrink-0 text-[11px] text-isotope-muted">{message.created_at}</time>
            </div>
            <p class="mt-2 whitespace-pre-wrap text-sm leading-6">{message.summary}</p>
          </article>
        {/each}
      </div>
    {/if}
  </div>
</main>
