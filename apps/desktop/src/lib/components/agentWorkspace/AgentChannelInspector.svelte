<script lang="ts">
  import type { CodexTranscriptPage } from '../../contracts/agentGroup';
  import type {
    AgentWorkspaceMember,
    CodexSessionCandidate,
    WorkspaceConversationKind,
    WorkspaceSendPolicy
  } from '../../contracts/agentWorkspace';
  import CodexTranscriptPanel from '../agentGroup/CodexTranscriptPanel.svelte';
  import CodexSessionPicker from './CodexSessionPicker.svelte';
  import { workspaceMemberStatusLabel } from './labels';

  let {
    selectedConversationKind,
    conversationTitle,
    currentMembers = [],
    sessionScope = $bindable<'cwd' | 'all'>('cwd'),
    sessionCandidates = [],
    selectedSessionId = $bindable<string | null>(null),
    selectedSession = null,
    isLoadingSessions = false,
    memberDisplayName = $bindable(''),
    memberRole = $bindable(''),
    memberGoal = $bindable(''),
    memberSendPolicy = $bindable<WorkspaceSendPolicy>('confirm'),
    transcript = null,
    showRaw = false,
    onLoadCodexSessions,
    onSelectSession,
    onAddMember,
    onUpdateMember,
    onRemoveMember,
    onStopMember,
    onReactivateMember,
    onLoadTranscript,
    onToggleTranscriptRaw
  } = $props<{
    selectedConversationKind: WorkspaceConversationKind;
    conversationTitle: string;
    currentMembers?: AgentWorkspaceMember[];
    sessionScope: 'cwd' | 'all';
    sessionCandidates?: CodexSessionCandidate[];
    selectedSessionId: string | null;
    selectedSession?: CodexSessionCandidate | null;
    isLoadingSessions?: boolean;
    memberDisplayName: string;
    memberRole: string;
    memberGoal: string;
    memberSendPolicy: WorkspaceSendPolicy;
    transcript?: CodexTranscriptPage | null;
    showRaw?: boolean;
    onLoadCodexSessions: (scope: 'cwd' | 'all') => void;
    onSelectSession: (candidate: CodexSessionCandidate) => void;
    onAddMember: () => void;
    onUpdateMember: (member: AgentWorkspaceMember, sendPolicy: WorkspaceSendPolicy) => void;
    onRemoveMember: (member: AgentWorkspaceMember) => void;
    onStopMember: (member: AgentWorkspaceMember) => void;
    onReactivateMember: (member: AgentWorkspaceMember) => void;
    onLoadTranscript: (member: AgentWorkspaceMember) => void;
    onToggleTranscriptRaw: () => void;
  }>();
</script>

<aside class="hidden w-[23rem] shrink-0 overflow-y-auto border-l border-isotope-line bg-[#f6f7f9] p-4 xl:block">
  <div class="mb-4 flex items-center justify-between gap-3">
    <div>
      <div class="text-sm font-semibold">频道设置</div>
      <div class="mt-1 text-xs text-isotope-muted">{conversationTitle}</div>
    </div>
    <button
      class="border border-isotope-line bg-white px-3 py-1.5 text-xs font-semibold text-isotope-muted"
      type="button"
      onclick={() => onLoadCodexSessions(sessionScope)}
    >
      会话列表
    </button>
  </div>

  {#if selectedConversationKind !== 'channel'}
    <div class="border border-isotope-line bg-white px-3 py-3 text-sm text-isotope-muted">
      私聊没有群聊成员。
    </div>
  {:else}
    <div class="space-y-3">
      {#each currentMembers as member (member.member_id)}
        <article class="border border-isotope-line bg-white px-3 py-3">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="truncate text-sm font-semibold">{member.display_name}</div>
              <div class="mt-1 truncate text-xs text-isotope-muted">{member.resume_session_id}</div>
            </div>
            <span class="shrink-0 border border-isotope-line px-2 py-0.5 text-[11px] text-isotope-muted">
              {workspaceMemberStatusLabel(member.status)}
            </span>
          </div>
          <div class="mt-3 grid grid-cols-[1fr_auto_auto_auto] gap-2">
            <select
              class="min-w-0 border border-isotope-line bg-white px-2 py-1.5 text-xs"
              value={member.send_policy}
              onchange={(event) =>
                onUpdateMember(member, (event.currentTarget as HTMLSelectElement).value as WorkspaceSendPolicy)}
            >
              <option value="auto">自动发送</option>
              <option value="confirm">发送前确认</option>
              <option value="draft_only">只写草稿</option>
            </select>
            <button
              class="border border-isotope-line bg-white px-2 py-1.5 text-xs font-semibold text-isotope-muted"
              type="button"
              disabled={!member.resume_session_id}
              onclick={() => onLoadTranscript(member)}
            >
              查看记录
            </button>
            {#if member.status === 'terminated'}
              <button
                class="border border-isotope-running/40 bg-white px-2 py-1.5 text-xs font-semibold text-isotope-running"
                type="button"
                onclick={() => onReactivateMember(member)}
              >
                启用
              </button>
            {:else}
              <button
                class="border border-isotope-error/40 bg-white px-2 py-1.5 text-xs font-semibold text-isotope-error"
                type="button"
                onclick={() => onStopMember(member)}
              >
                停止
              </button>
            {/if}
            <button
              class="border border-isotope-line bg-white px-2 py-1.5 text-xs font-semibold text-isotope-muted"
              type="button"
              onclick={() => onRemoveMember(member)}
            >
              移除
            </button>
          </div>
        </article>
      {/each}
    </div>

    <CodexSessionPicker
      bind:sessionScope
      {sessionCandidates}
      bind:selectedSessionId
      {selectedSession}
      {isLoadingSessions}
      bind:memberDisplayName
      bind:memberRole
      bind:memberGoal
      bind:memberSendPolicy
      {onLoadCodexSessions}
      {onSelectSession}
      {onAddMember}
    />

    <div class="mt-5">
      <CodexTranscriptPanel {transcript} {showRaw} onToggleRaw={() => onToggleTranscriptRaw()} />
    </div>
  {/if}
</aside>
