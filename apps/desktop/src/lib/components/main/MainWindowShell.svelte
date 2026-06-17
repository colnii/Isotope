<script lang="ts">
  import type { ApprovalSummary, ActivityNode, IsotopeSnapshot } from '../../contracts/isotope';
  import type { AgentClient, ApprovalResolution } from '../../client/agentClient';
  import type { DesktopChatMessage, DesktopChatSessionSummary } from '../../stores/appState';
  import { buildMainWindowProductView } from '../../view/mainWindowProductView';
  import ConversationWorkspace from './ConversationWorkspace.svelte';
  import SessionHistorySidebar from './sessionHistory/SessionHistorySidebar.svelte';

  let {
    snapshot,
    selectedActivity,
    chatMessages = [],
    chatSessionSummaries = [],
    activeChatSessionId = '',
    chatError = null,
    isAskingDesktop = false,
    resolvingApprovalId = null,
    approvalError = null,
    terminalYoloEnabled = false,
    agentClient,
    onAskDesktop,
    onSelectChatSession = () => undefined,
    onDeleteChatSession = () => undefined,
    onNewChatSession = () => undefined,
    onResolveApproval,
    onToggleTerminalYolo,
    onAllowlistTerminalApproval
  } = $props<{
    snapshot: IsotopeSnapshot;
    selectedActivity: ActivityNode | null;
    chatMessages?: DesktopChatMessage[];
    chatSessionSummaries?: DesktopChatSessionSummary[];
    activeChatSessionId?: string;
    chatError?: string | null;
    isAskingDesktop?: boolean;
    resolvingApprovalId?: string | null;
    approvalError?: string | null;
    terminalYoloEnabled?: boolean;
    agentClient: AgentClient;
    onAskDesktop: (question: string) => void;
    onSelectChatSession?: (sessionId: string) => void;
    onDeleteChatSession?: (sessionId: string) => void;
    onNewChatSession?: () => void;
    onResolveApproval: (approvalId: string, resolution: ApprovalResolution) => void;
    onToggleTerminalYolo: () => void;
    onAllowlistTerminalApproval: (approvalId: string, command: string) => void;
  }>();

  const view = $derived(buildMainWindowProductView(snapshot, selectedActivity));
  const pendingApprovals = $derived.by((): ApprovalSummary[] =>
    snapshot.approvals.filter((approval: ApprovalSummary) => approval.status === 'pending')
  );
</script>

<section class="iso-main-window-shell" aria-label="Isotope AI 对话">
  <SessionHistorySidebar
    sessions={chatSessionSummaries}
    activeSessionId={activeChatSessionId}
    onSelectSession={onSelectChatSession}
    onDeleteSession={onDeleteChatSession}
    onNewSession={onNewChatSession}
  />
  <div class="iso-main-conversation-pane">
  <ConversationWorkspace
    eyebrow={view.chatEyebrow}
    title={view.workspaceTitle}
    subtitle={view.workspaceSubtitle}
    body={view.workspaceBody}
    emptyTitle={view.emptyChatTitle}
    emptyBody={view.emptyChatBody}
    composerPlaceholder={view.composerPlaceholder}
    approvals={pendingApprovals}
    {resolvingApprovalId}
    {approvalError}
    {chatMessages}
    {chatError}
    isAsking={isAskingDesktop}
    {terminalYoloEnabled}
    {agentClient}
    onAsk={onAskDesktop}
    onResolveApproval={onResolveApproval}
    onToggleTerminalYolo={onToggleTerminalYolo}
    onAllowlistTerminalApproval={onAllowlistTerminalApproval}
  />
  </div>
</section>
