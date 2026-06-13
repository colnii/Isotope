<script lang="ts">
  import type { AgentGroupClient } from '../../client/agentGroupClient';
  import type {
    AgentGroupDetail,
    CodexTranscriptPage,
    ConnectedCodexMember
  } from '../../contracts/agentGroup';
  import AgentGroupMemberStrip from './AgentGroupMemberStrip.svelte';
  import AgentGroupPrivateChat from './AgentGroupPrivateChat.svelte';
  import AgentGroupStream from './AgentGroupStream.svelte';
  import CodexTranscriptPanel from './CodexTranscriptPanel.svelte';

  let {
    group,
    isRunning = false,
    composerText = '',
    agentGroupClient
  } = $props<{
    group: AgentGroupDetail;
    isRunning?: boolean;
    composerText?: string;
    agentGroupClient: AgentGroupClient;
  }>();

  let localComposerText = $state('');
  let transcript = $state<CodexTranscriptPage | null>(null);
  let showRaw = $state(false);
  let actionError = $state<string | null>(null);
  const composerIsEmpty = $derived(localComposerText.trim().length === 0);

  $effect(() => {
    if (!localComposerText && composerText) {
      localComposerText = composerText;
    }
  });

  async function stopCurrentRun() {
    actionError = null;
    try {
      await agentGroupClient.stopCurrentRun(group.group.group_id);
    } catch (error) {
      actionError = error instanceof Error ? error.message : 'Stop current run failed';
    }
  }

  async function stopMember(memberId: string) {
    actionError = null;
    try {
      await agentGroupClient.stopMember(group.group.group_id, memberId);
    } catch (error) {
      actionError = error instanceof Error ? error.message : 'Stop member failed';
    }
  }

  async function sendMessage(mode: 'queue' | 'interrupt') {
    const message = localComposerText.trim();
    if (!message) return;
    actionError = null;
    try {
      await agentGroupClient.sendMessage(group.group.group_id, message, mode);
      localComposerText = '';
    } catch (error) {
      actionError = error instanceof Error ? error.message : 'Send failed';
    }
  }

  async function openTranscript(member: ConnectedCodexMember) {
    if (!member.resume_session_id) return;
    actionError = null;
    try {
      transcript = await agentGroupClient.loadTranscript(member.resume_session_id, {
        offset: 0,
        limit: Number(member.transcript_policy?.page_size ?? 200),
        includeRaw: showRaw,
        latest: true
      });
    } catch (error) {
      actionError = error instanceof Error ? error.message : 'Transcript load failed';
    }
  }
</script>

<section class="iso-agent-group-shell" aria-label="Agent Group Chat">
  <header class="border-b border-isotope-line bg-isotope-panel px-5 py-4">
    <div class="text-xs font-semibold uppercase text-isotope-muted">Agent Group Chat</div>
    <h1 class="mt-1 text-xl font-semibold">{group.group.title}</h1>
    <p class="mt-1 text-sm text-isotope-muted">{group.group.goal}</p>
  </header>

  <AgentGroupMemberStrip
    members={group.connected_members}
    onStopMember={stopMember}
    onOpenTranscript={openTranscript}
  />

  <div class="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_22rem]">
    <AgentGroupStream messages={group.messages} />
    <AgentGroupPrivateChat messages={group.private_chat} />
  </div>

  <CodexTranscriptPanel {transcript} {showRaw} onToggleRaw={() => (showRaw = !showRaw)} />

  <footer class="iso-agent-composer">
    {#if actionError}
      <div class="iso-agent-error-card" role="alert">
        {actionError}
      </div>
    {/if}
    <div class="flex gap-2">
      <input
        class="iso-agent-input flex-1"
        bind:value={localComposerText}
        placeholder="给协调模型发消息"
      />
      {#if isRunning && composerIsEmpty}
        <button
          class="iso-agent-button-danger"
          type="button"
          onclick={stopCurrentRun}
        >
          Stop current run
        </button>
      {:else if isRunning}
        <button
          class="iso-agent-button-secondary"
          type="button"
          onclick={() => sendMessage('queue')}
        >
          Queue
        </button>
        <button
          class="iso-agent-button-primary"
          type="button"
          onclick={() => sendMessage('interrupt')}
        >
          Interrupt
        </button>
      {:else}
        <button
          class="iso-agent-button-primary"
          type="button"
          onclick={() => sendMessage('queue')}
        >
          Send
        </button>
      {/if}
    </div>
  </footer>
</section>
