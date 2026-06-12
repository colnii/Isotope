<script lang="ts">
  import type {
    AgentWorkspaceChannel,
    AgentWorkspaceDirectMessage,
    AgentWorkspaceSummary,
    WorkspaceConversationKind
  } from '../../contracts/agentWorkspace';

  let {
    workspace = null,
    channels = [],
    directMessages = [],
    selectedConversationId = null,
    newChannelName = $bindable(''),
    newChannelTopic = $bindable(''),
    onCreateChannel,
    onSelectConversation
  } = $props<{
    workspace?: AgentWorkspaceSummary | null;
    channels?: AgentWorkspaceChannel[];
    directMessages?: AgentWorkspaceDirectMessage[];
    selectedConversationId?: string | null;
    newChannelName: string;
    newChannelTopic: string;
    onCreateChannel: () => void;
    onSelectConversation: (kind: WorkspaceConversationKind, conversationId: string) => void;
  }>();
</script>

<aside class="flex w-64 shrink-0 flex-col border-r border-isotope-line bg-[#eef2f6]">
  <div class="border-b border-isotope-line px-4 py-4">
    <div class="truncate text-sm font-semibold">{workspace?.title ?? 'Agent Workspace'}</div>
    <div class="mt-1 truncate text-[11px] text-isotope-muted">{workspace?.root_path ?? 'loading'}</div>
  </div>

  <div class="border-b border-isotope-line px-3 py-3">
    <div class="flex gap-2">
      <input
        class="min-w-0 flex-1 border border-isotope-line bg-white px-2 py-1.5 text-xs"
        bind:value={newChannelName}
        placeholder="+ New Group"
      />
      <button
        class="border border-isotope-running bg-white px-2 py-1.5 text-xs font-semibold text-isotope-running"
        type="button"
        onclick={() => onCreateChannel()}
      >
        +
      </button>
    </div>
    <input
      class="mt-2 w-full border border-isotope-line bg-white px-2 py-1.5 text-xs"
      bind:value={newChannelTopic}
      placeholder="Topic"
    />
  </div>

  <nav class="min-h-0 flex-1 overflow-y-auto px-3 py-3" aria-label="Workspace conversations">
    <div class="mb-2 text-[11px] font-semibold uppercase tracking-wide text-isotope-muted">Channels</div>
    <div class="space-y-1">
      {#each channels as channel (channel.channel_id)}
        <button
          class={`w-full truncate border px-3 py-2 text-left text-sm ${
            selectedConversationId === channel.channel_id
              ? 'border-isotope-running bg-white font-semibold text-isotope-running'
              : 'border-transparent text-isotope-text hover:border-isotope-line hover:bg-white'
          }`}
          type="button"
          onclick={() => onSelectConversation('channel', channel.channel_id)}
        >
          # {channel.name}
        </button>
      {/each}
    </div>

    <div class="mb-2 mt-5 text-[11px] font-semibold uppercase tracking-wide text-isotope-muted">
      Direct messages
    </div>
    <div class="space-y-1">
      {#each directMessages as directMessage (directMessage.dm_id)}
        <button
          class={`w-full truncate border px-3 py-2 text-left text-sm ${
            selectedConversationId === directMessage.dm_id
              ? 'border-isotope-running bg-white font-semibold text-isotope-running'
              : 'border-transparent text-isotope-text hover:border-isotope-line hover:bg-white'
          }`}
          type="button"
          onclick={() => onSelectConversation('dm', directMessage.dm_id)}
        >
          {directMessage.title}
        </button>
      {/each}
    </div>
  </nav>
</aside>
