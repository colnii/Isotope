<script lang="ts">
  import { onMount } from 'svelte';
  import type { AgentWorkspaceClient } from '../../client/agentWorkspaceClient';
  import type { CodexTranscriptPage } from '../../contracts/agentGroup';
  import type {
    AgentWorkspaceDetail,
    AgentWorkspaceMember,
    CodexSessionCandidate,
    WorkspaceConversationKind,
    WorkspaceSendPolicy
  } from '../../contracts/agentWorkspace';
  import AgentChannelInspector from './AgentChannelInspector.svelte';
  import AgentConversationComposer from './AgentConversationComposer.svelte';
  import AgentConversationPane from './AgentConversationPane.svelte';
  import AgentWorkspaceSidebar from './AgentWorkspaceSidebar.svelte';
  import { workspaceChannelDisplayName, workspaceDirectMessageTitle } from './labels';

  let { agentWorkspaceClient } = $props<{
    agentWorkspaceClient: AgentWorkspaceClient;
  }>();

  let workspaces = $state<AgentWorkspaceDetail['workspace'][]>([]);
  let workspace = $state<AgentWorkspaceDetail | null>(null);
  let selectedConversationKind = $state<WorkspaceConversationKind>('channel');
  let selectedConversationId = $state<string | null>(null);
  let composerText = $state('');
  let actionError = $state<string | null>(null);
  let isLoading = $state(false);
  let isSending = $state(false);
  let newChannelName = $state('');
  let newChannelTopic = $state('');
  let workspaceSettingsOpen = $state(false);
  let workspaceTitle = $state('');
  let workspaceRootPath = $state('');
  let isSavingWorkspace = $state(false);
  let sessionScope = $state<'cwd' | 'all'>('cwd');
  let sessionCandidates = $state<CodexSessionCandidate[]>([]);
  let selectedSessionId = $state<string | null>(null);
  let isLoadingSessions = $state(false);
  let hasLoadedSessions = $state(false);
  let memberDisplayName = $state('');
  let memberRole = $state('');
  let memberGoal = $state('');
  let memberSendPolicy = $state<WorkspaceSendPolicy>('confirm');
  let transcript = $state<CodexTranscriptPage | null>(null);
  let transcriptSessionId = $state<string | null>(null);
  let showRaw = $state(false);

  const channels = $derived(workspace?.channels.filter((channel) => channel.status !== 'archived') ?? []);
  const directMessages = $derived(
    workspace?.direct_messages.filter((message) => message.status !== 'archived') ?? []
  );
  const currentMembers = $derived(
    workspace?.members.filter(
      (member) => member.channel_id === selectedConversationId && member.status !== 'archived'
    ) ?? []
  );
  const currentMessages = $derived(
    workspace?.messages.filter((message) => message.conversation_id === selectedConversationId) ?? []
  );
  const selectedSession = $derived(
    sessionCandidates.find((candidate) => candidate.session_id === selectedSessionId) ?? null
  );
  const conversationTitle = $derived(resolveConversationTitle());
  const conversationSubtitle = $derived(resolveConversationSubtitle());
  const currentRunIsActive = $derived(
    selectedConversationKind === 'channel' &&
      currentMembers.some((member) => member.status === 'running')
  );

  onMount(() => {
    void initializeWorkspace();
  });

  async function initializeWorkspace() {
    actionError = null;
    isLoading = true;
    try {
      const list = await agentWorkspaceClient.listWorkspaces();
      workspaces = list.workspaces;
      const firstWorkspaceId = list.workspaces[0]?.workspace_id;
      if (firstWorkspaceId) {
        await loadWorkspace(firstWorkspaceId);
      }
    } catch (error) {
      actionError = errorMessage(error, '智能体工作区加载失败');
    } finally {
      isLoading = false;
    }
  }

  async function loadWorkspace(workspaceId: string) {
    const detail = await agentWorkspaceClient.loadWorkspace(workspaceId);
    workspace = detail;
    syncWorkspaceDraft(detail);
    selectFallbackConversation(detail);
  }

  async function refreshWorkspace() {
    if (!workspace) return;
    await loadWorkspace(workspace.workspace.workspace_id);
  }

  function selectFallbackConversation(detail: AgentWorkspaceDetail) {
    if (selectedConversationId && conversationExists(detail, selectedConversationKind, selectedConversationId)) {
      return;
    }
    const firstChannel = detail.channels.find((channel) => channel.status !== 'archived');
    if (firstChannel) {
      selectedConversationKind = 'channel';
      selectedConversationId = firstChannel.channel_id;
      return;
    }
    const firstDm = detail.direct_messages.find((message) => message.status !== 'archived');
    selectedConversationKind = 'dm';
    selectedConversationId = firstDm?.dm_id ?? null;
  }

  function conversationExists(
    detail: AgentWorkspaceDetail,
    kind: WorkspaceConversationKind,
    conversationId: string
  ) {
    if (kind === 'channel') {
      return detail.channels.some((channel) => channel.channel_id === conversationId);
    }
    return detail.direct_messages.some((message) => message.dm_id === conversationId);
  }

  function selectConversation(kind: WorkspaceConversationKind, conversationId: string) {
    selectedConversationKind = kind;
    selectedConversationId = conversationId;
    actionError = null;
  }

  function syncWorkspaceDraft(detail: AgentWorkspaceDetail) {
    workspaceTitle = detail.workspace.title;
    workspaceRootPath = detail.workspace.root_path;
  }

  async function saveWorkspaceSettings() {
    if (!workspace) return;
    const title = workspaceTitle.trim();
    const rootPath = workspaceRootPath.trim();
    if (!title || !rootPath) return;
    actionError = null;
    isSavingWorkspace = true;
    try {
      const updated = await agentWorkspaceClient.updateWorkspace(workspace.workspace.workspace_id, {
        title,
        root_path: rootPath
      });
      workspace = updated;
      syncWorkspaceDraft(updated);
      replaceWorkspaceSummary(updated);
      selectFallbackConversation(updated);
      workspaceSettingsOpen = false;
      if (hasLoadedSessions) {
        await loadCodexSessions(sessionScope);
      }
    } catch (error) {
      actionError = errorMessage(error, '工作区设置保存失败');
    } finally {
      isSavingWorkspace = false;
    }
  }

  function replaceWorkspaceSummary(detail: AgentWorkspaceDetail) {
    const summary = detail.workspace;
    if (workspaces.some((candidate) => candidate.workspace_id === summary.workspace_id)) {
      workspaces = workspaces.map((candidate) =>
        candidate.workspace_id === summary.workspace_id ? summary : candidate
      );
      return;
    }
    workspaces = [...workspaces, summary];
  }

  function resolveConversationTitle() {
    if (!workspace || !selectedConversationId) return '智能体工作区';
    if (selectedConversationKind === 'channel') {
      const channel = channels.find((candidate) => candidate.channel_id === selectedConversationId);
      return channel ? workspaceChannelDisplayName(channel.name) : '群聊';
    }
    const directMessage = directMessages.find((message) => message.dm_id === selectedConversationId);
    return directMessage ? workspaceDirectMessageTitle(directMessage.title) : '私聊';
  }

  function resolveConversationSubtitle() {
    if (!workspace || !selectedConversationId || selectedConversationKind !== 'channel') return '';
    const channel = channels.find((candidate) => candidate.channel_id === selectedConversationId);
    return channel ? channel.topic.trim() : '';
  }

  async function createChannel() {
    if (!workspace) return;
    const name = newChannelName.trim();
    if (!name) return;
    actionError = null;
    try {
      const created = await agentWorkspaceClient.createChannel(workspace.workspace.workspace_id, {
        name,
        topic: newChannelTopic.trim()
      });
      newChannelName = '';
      newChannelTopic = '';
      selectedConversationKind = 'channel';
      selectedConversationId = created.channel.channel_id;
      await refreshWorkspace();
    } catch (error) {
      actionError = errorMessage(error, '创建群聊失败');
    }
  }

  async function loadCodexSessions(scope: 'cwd' | 'all' = sessionScope) {
    if (!workspace) return;
    actionError = null;
    sessionScope = scope;
    isLoadingSessions = true;
    try {
      const payload = await agentWorkspaceClient.listCodexSessions(
        workspace.workspace.workspace_id,
        sessionScope
      );
      sessionCandidates = payload.sessions;
      selectedSessionId = payload.sessions[0]?.session_id ?? null;
      hasLoadedSessions = true;
      applySelectedSessionDefaults();
    } catch (error) {
      actionError = errorMessage(error, 'Codex session 加载失败');
    } finally {
      isLoadingSessions = false;
    }
  }

  function selectSession(candidate: CodexSessionCandidate) {
    selectedSessionId = candidate.session_id;
    applySelectedSessionDefaults();
  }

  function applySelectedSessionDefaults() {
    const candidate = selectedSession;
    if (!candidate) return;
    if (!memberDisplayName.trim()) {
      memberDisplayName = candidate.display_title || candidate.title || candidate.short_session_id;
    }
    if (!memberRole.trim()) {
      memberRole = 'Codex 会话';
    }
  }

  async function addMember() {
    if (!workspace || !selectedConversationId || selectedConversationKind !== 'channel' || !selectedSession) {
      return;
    }
    const displayName =
      memberDisplayName.trim() ||
      selectedSession.display_title ||
      selectedSession.title ||
      selectedSession.short_session_id;
    const role = memberRole.trim() || 'Codex 会话';
    actionError = null;
    try {
      await agentWorkspaceClient.addMember(workspace.workspace.workspace_id, selectedConversationId, {
        display_name: displayName,
        role,
        goal: memberGoal.trim(),
        send_policy: memberSendPolicy,
        resume_session_id: selectedSession.session_id,
        source_path: selectedSession.source_path,
        managed_record_id: selectedSession.managed_record_id ?? null
      });
      memberDisplayName = '';
      memberRole = '';
      memberGoal = '';
      selectedSessionId = null;
      await refreshWorkspace();
    } catch (error) {
      actionError = errorMessage(error, '添加 Codex 失败');
    }
  }

  async function updateMember(member: AgentWorkspaceMember, send_policy: WorkspaceSendPolicy) {
    if (!workspace) return;
    actionError = null;
    try {
      await agentWorkspaceClient.updateMember(
        workspace.workspace.workspace_id,
        member.channel_id,
        member.member_id,
        { send_policy }
      );
      await refreshWorkspace();
    } catch (error) {
      actionError = errorMessage(error, '发送权限更新失败');
    }
  }

  async function removeMember(member: AgentWorkspaceMember) {
    if (!workspace) return;
    actionError = null;
    try {
      await agentWorkspaceClient.removeMember(
        workspace.workspace.workspace_id,
        member.channel_id,
        member.member_id
      );
      await refreshWorkspace();
    } catch (error) {
      actionError = errorMessage(error, '移除成员失败');
    }
  }

  async function loadTranscript(member: AgentWorkspaceMember) {
    if (!member.resume_session_id) return;
    actionError = null;
    const policyLimit = Number(member.transcript_policy?.page_size ?? 0);
    const transcriptLimit = Math.max(policyLimit, 1000);
    try {
      transcript = await agentWorkspaceClient.loadTranscript(member.resume_session_id, {
        offset: 0,
        limit: transcriptLimit,
        includeRaw: showRaw
      });
      transcriptSessionId = member.resume_session_id;
    } catch (error) {
      actionError = errorMessage(error, '会话记录加载失败');
    }
  }

  async function toggleTranscriptRaw() {
    showRaw = !showRaw;
    const member = currentMembers.find((candidate) => candidate.resume_session_id === transcriptSessionId);
    if (member) {
      await loadTranscript(member);
    }
  }

  async function sendMessage(mode: 'queue' | 'interrupt') {
    if (!workspace || !selectedConversationId) return;
    const message = composerText.trim();
    if (!message) return;
    actionError = null;
    isSending = true;
    try {
      await agentWorkspaceClient.sendConversation(
        workspace.workspace.workspace_id,
        selectedConversationId,
        message,
        mode
      );
      composerText = '';
      await refreshWorkspace();
    } catch (error) {
      actionError = errorMessage(error, '发送失败');
    } finally {
      isSending = false;
    }
  }

  async function stopCurrentRun() {
    if (!workspace || !selectedConversationId) return;
    actionError = null;
    try {
      await agentWorkspaceClient.stopCurrentRun(workspace.workspace.workspace_id, selectedConversationId);
      await refreshWorkspace();
    } catch (error) {
      actionError = errorMessage(error, '停止当前运行失败');
    }
  }

  async function stopMember(member: AgentWorkspaceMember) {
    if (!workspace || !selectedConversationId) return;
    actionError = null;
    try {
      await agentWorkspaceClient.stopMember(
        workspace.workspace.workspace_id,
        selectedConversationId,
        member.member_id
      );
      await refreshWorkspace();
    } catch (error) {
      actionError = errorMessage(error, '停止成员失败');
    }
  }

  function errorMessage(error: unknown, fallback: string) {
    return error instanceof Error ? error.message : fallback;
  }
</script>

<section class="flex min-h-screen bg-[#f6f7f9] text-isotope-text" aria-label="智能体工作区">
  <AgentWorkspaceSidebar
    workspace={workspace?.workspace ?? null}
    {channels}
    {directMessages}
    {selectedConversationId}
    bind:newChannelName
    bind:newChannelTopic
    bind:workspaceSettingsOpen
    bind:workspaceTitle
    bind:workspaceRootPath
    {isSavingWorkspace}
    onCreateChannel={() => void createChannel()}
    onSaveWorkspace={() => void saveWorkspaceSettings()}
    onSelectConversation={selectConversation}
  />

  <div class="flex min-w-0 flex-1 flex-col">
    <AgentConversationPane
      {selectedConversationKind}
      {conversationTitle}
      {conversationSubtitle}
      currentMembersCount={currentMembers.length}
      {currentMessages}
      {isLoading}
      onRefresh={() => void refreshWorkspace()}
    />
    <AgentConversationComposer
      {selectedConversationKind}
      {selectedConversationId}
      {currentRunIsActive}
      bind:composerText
      {actionError}
      {isSending}
      onSendMessage={(mode) => void sendMessage(mode)}
      onStopCurrentRun={() => void stopCurrentRun()}
    />
  </div>

  <AgentChannelInspector
    {selectedConversationKind}
    {conversationTitle}
    {currentMembers}
    bind:sessionScope
    {sessionCandidates}
    bind:selectedSessionId
    {selectedSession}
    {isLoadingSessions}
    bind:memberDisplayName
    bind:memberRole
    bind:memberGoal
    bind:memberSendPolicy
    {transcript}
    {showRaw}
    onLoadCodexSessions={(scope) => void loadCodexSessions(scope)}
    onSelectSession={selectSession}
    onAddMember={() => void addMember()}
    onUpdateMember={(member, sendPolicy) => void updateMember(member, sendPolicy)}
    onRemoveMember={(member) => void removeMember(member)}
    onStopMember={(member) => void stopMember(member)}
    onLoadTranscript={(member) => void loadTranscript(member)}
    onToggleTranscriptRaw={() => void toggleTranscriptRaw()}
  />
</section>
