<script lang="ts">
  import type {
    AgentWorkspaceChannel,
    AgentWorkspaceDirectMessage,
    AgentWorkspaceSummary,
    WorkspaceConversationKind
  } from '../../contracts/agentWorkspace';
  import { workspaceChannelDisplayName, workspaceDirectMessageTitle } from './labels';

  let {
    workspace = null,
    channels = [],
    directMessages = [],
    selectedConversationId = null,
    newChannelName = $bindable(''),
    newChannelTopic = $bindable(''),
    workspaceSettingsOpen = $bindable(false),
    workspaceTitle = $bindable(''),
    workspaceRootPath = $bindable(''),
    isSavingWorkspace = false,
    onCreateChannel,
    onSaveWorkspace,
    onSelectConversation
  } = $props<{
    workspace?: AgentWorkspaceSummary | null;
    channels?: AgentWorkspaceChannel[];
    directMessages?: AgentWorkspaceDirectMessage[];
    selectedConversationId?: string | null;
    newChannelName: string;
    newChannelTopic: string;
    workspaceSettingsOpen: boolean;
    workspaceTitle: string;
    workspaceRootPath: string;
    isSavingWorkspace?: boolean;
    onCreateChannel: () => void;
    onSaveWorkspace: () => void;
    onSelectConversation: (kind: WorkspaceConversationKind, conversationId: string) => void;
  }>();
</script>

<aside class="iso-agent-sidebar">
  <div class="iso-agent-sidebar-header">
    <div class="truncate text-sm font-semibold">{workspace?.title ?? '智能体工作区'}</div>
    <div class="mt-1 truncate text-[11px] text-isotope-muted">{workspace?.root_path ?? '加载中'}</div>
    <button
      class="iso-agent-button-secondary mt-3 flex w-full justify-start"
      type="button"
      onclick={() => {
        workspaceSettingsOpen = !workspaceSettingsOpen;
      }}
    >
      工作区设置
    </button>
    {#if workspaceSettingsOpen}
      <form
        class="mt-3 space-y-2"
        onsubmit={(event) => {
          event.preventDefault();
          onSaveWorkspace();
        }}
      >
        <label class="block text-[11px] font-semibold text-isotope-muted">
          工作区名称
          <input
            class="iso-agent-input-compact mt-1 w-full font-normal"
            bind:value={workspaceTitle}
            disabled={!workspace || isSavingWorkspace}
          />
        </label>
        <label class="block text-[11px] font-semibold text-isotope-muted">
          绑定目录
          <input
            class="iso-agent-input-compact mt-1 w-full font-normal"
            bind:value={workspaceRootPath}
            disabled={!workspace || isSavingWorkspace}
          />
        </label>
        <div class="flex gap-2">
          <button
            class="iso-agent-button-primary flex-1"
            type="submit"
            disabled={!workspace || isSavingWorkspace}
          >
            {isSavingWorkspace ? '保存中' : '保存设置'}
          </button>
          <button
            class="iso-agent-button-secondary"
            type="button"
            onclick={() => {
              workspaceSettingsOpen = false;
            }}
          >
            取消
          </button>
        </div>
      </form>
    {/if}
  </div>

  <div class="border-b border-isotope-line px-3 py-3">
    <div class="flex gap-2">
      <input
        class="iso-agent-input-compact min-w-0 flex-1"
        bind:value={newChannelName}
        placeholder="群聊名称"
      />
      <button
        class="iso-agent-button-secondary"
        type="button"
        onclick={() => onCreateChannel()}
      >
        +
      </button>
    </div>
    <input
      class="iso-agent-input-compact mt-2 w-full"
      bind:value={newChannelTopic}
      placeholder="群聊目标/说明（可选）"
    />
  </div>

  <nav class="min-h-0 flex-1 overflow-y-auto px-3 py-3" aria-label="工作区会话">
    <div class="mb-2 text-[11px] font-semibold uppercase tracking-wide text-isotope-muted">群聊</div>
    <div class="space-y-1">
      {#each channels as channel (channel.channel_id)}
        <button
          class={`iso-agent-nav-item ${
            selectedConversationId === channel.channel_id ? 'iso-agent-nav-item-active' : ''
          }`}
          type="button"
          onclick={() => onSelectConversation('channel', channel.channel_id)}
        >
          # {workspaceChannelDisplayName(channel.name)}
        </button>
      {/each}
    </div>

    <div class="mb-2 mt-5 text-[11px] font-semibold uppercase tracking-wide text-isotope-muted">
      私聊
    </div>
    <div class="space-y-1">
      {#each directMessages as directMessage (directMessage.dm_id)}
        <button
          class={`iso-agent-nav-item ${
            selectedConversationId === directMessage.dm_id ? 'iso-agent-nav-item-active' : ''
          }`}
          type="button"
          onclick={() => onSelectConversation('dm', directMessage.dm_id)}
        >
          {workspaceDirectMessageTitle(directMessage.title)}
        </button>
      {/each}
    </div>
  </nav>
</aside>
