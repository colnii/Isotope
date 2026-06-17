<script lang="ts">
  import type { DesktopChatSessionSummary } from '../../../stores/appState';

  let {
    sessions = [],
    activeSessionId = '',
    onSelectSession,
    onNewSession
  } = $props<{
    sessions?: DesktopChatSessionSummary[];
    activeSessionId?: string;
    onSelectSession: (sessionId: string) => void;
    onNewSession: () => void;
  }>();

  function formatUpdatedAt(value: string): string {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return new Intl.DateTimeFormat('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    }).format(date);
  }
</script>

<aside class="iso-session-sidebar" aria-label="历史会话">
  <header class="iso-session-sidebar-header">
    <div>
      <div class="iso-session-sidebar-kicker">Chat sessions</div>
      <h2 class="iso-session-sidebar-title">历史会话</h2>
    </div>
    <button
      type="button"
      class="iso-session-new-button"
      aria-label="新建会话"
      title="新建会话"
      onclick={onNewSession}
    >
      +
    </button>
  </header>

  <div class="iso-session-list">
    {#if sessions.length === 0}
      <div class="iso-session-empty">暂无会话</div>
    {:else}
      {#each sessions as session (session.id)}
        <button
          type="button"
          class={[
            'iso-session-item',
            session.id === activeSessionId || session.active ? 'iso-session-item-active' : ''
          ]}
          aria-current={session.id === activeSessionId ? 'page' : undefined}
          onclick={() => onSelectSession(session.id)}
        >
          <span class="iso-session-item-title">{session.title}</span>
          <span class="iso-session-item-meta">
            {session.messageCount} 条 / {formatUpdatedAt(session.updatedAt)}
          </span>
        </button>
      {/each}
    {/if}
  </div>
</aside>
