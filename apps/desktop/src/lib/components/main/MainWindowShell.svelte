<script lang="ts">
  import type { ApprovalSummary, ActivityNode, IsotopeSnapshot } from '../../contracts/isotope';
  import type { AgentClient, ApprovalResolution } from '../../client/agentClient';
  import type { DesktopChatMessage } from '../../stores/appState';
  import { buildMainWindowProductView } from '../../view/mainWindowProductView';
  import ConversationWorkspace from './ConversationWorkspace.svelte';

  let {
    snapshot,
    selectedActivity,
    chatMessages = [],
    chatError = null,
    isAskingDesktop = false,
    resolvingApprovalId = null,
    approvalError = null,
    agentClient,
    onAskDesktop,
    onResolveApproval
  } = $props<{
    snapshot: IsotopeSnapshot;
    selectedActivity: ActivityNode | null;
    chatMessages?: DesktopChatMessage[];
    chatError?: string | null;
    isAskingDesktop?: boolean;
    resolvingApprovalId?: string | null;
    approvalError?: string | null;
    agentClient: AgentClient;
    onAskDesktop: (question: string) => void;
    onResolveApproval: (approvalId: string, resolution: ApprovalResolution) => void;
  }>();

  const view = $derived(buildMainWindowProductView(snapshot, selectedActivity));
  const pendingApprovals = $derived.by((): ApprovalSummary[] =>
    snapshot.approvals.filter((approval: ApprovalSummary) => approval.status === 'pending')
  );
</script>

<section
  class="min-h-screen bg-white text-isotope-text"
  aria-label="Isotope AI 对话"
>
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
    {agentClient}
    onAsk={onAskDesktop}
    onResolveApproval={onResolveApproval}
  />
</section>
