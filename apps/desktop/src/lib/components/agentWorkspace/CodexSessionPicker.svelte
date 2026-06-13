<script lang="ts">
  import type { CodexSessionCandidate, WorkspaceSendPolicy } from '../../contracts/agentWorkspace';

  let {
    sessionScope = $bindable<'cwd' | 'all'>('cwd'),
    sessionCandidates = [],
    selectedSessionId = $bindable<string | null>(null),
    selectedSession = null,
    isLoadingSessions = false,
    memberDisplayName = $bindable(''),
    memberRole = $bindable(''),
    memberGoal = $bindable(''),
    memberSendPolicy = $bindable<WorkspaceSendPolicy>('confirm'),
    onLoadCodexSessions,
    onSelectSession,
    onAddMember
  } = $props<{
    sessionScope: 'cwd' | 'all';
    sessionCandidates?: CodexSessionCandidate[];
    selectedSessionId: string | null;
    selectedSession?: CodexSessionCandidate | null;
    isLoadingSessions?: boolean;
    memberDisplayName: string;
    memberRole: string;
    memberGoal: string;
    memberSendPolicy: WorkspaceSendPolicy;
    onLoadCodexSessions: (scope: 'cwd' | 'all') => void;
    onSelectSession: (candidate: CodexSessionCandidate) => void;
    onAddMember: () => void;
  }>();
</script>

<section class="mt-5 border-t border-isotope-line pt-4">
  <div class="mb-3 flex items-center justify-between gap-2">
    <div class="text-sm font-semibold">Codex 会话列表</div>
    <div class="flex gap-1">
      <button
        class={`iso-agent-button-secondary ${
          sessionScope === 'cwd'
            ? 'border-isotope-red text-isotope-red'
            : ''
        }`}
        type="button"
        onclick={() => {
          sessionScope = 'cwd';
          onLoadCodexSessions(sessionScope);
        }}
      >
        当前目录
      </button>
      <button
        class={`iso-agent-button-secondary ${
          sessionScope === 'all'
            ? 'border-isotope-red text-isotope-red'
            : ''
        }`}
        type="button"
        onclick={() => {
          sessionScope = 'all';
          onLoadCodexSessions(sessionScope);
        }}
      >
        全部
      </button>
    </div>
  </div>

  <div class="max-h-44 space-y-2 overflow-y-auto">
    {#if isLoadingSessions}
      <div class="iso-agent-panel px-3 py-2 text-xs text-isotope-muted">加载中</div>
    {:else}
      {#each sessionCandidates as candidate (candidate.session_id)}
        <button
          class={`iso-agent-panel w-full px-3 py-2 text-left ${
            selectedSessionId === candidate.session_id ? 'border-isotope-red' : ''
          }`}
          type="button"
          onclick={() => onSelectSession(candidate)}
        >
          <div class="truncate text-xs font-semibold">
            {candidate.display_title || candidate.title || candidate.short_session_id}
          </div>
          <div class="mt-1 truncate text-[11px] text-isotope-muted">{candidate.cwd ?? candidate.source_path}</div>
        </button>
      {/each}
    {/if}
  </div>

  <div class="mt-3 space-y-2">
    <input
      class="iso-agent-input-compact w-full"
      bind:value={memberDisplayName}
      placeholder="显示名称"
    />
    <input
      class="iso-agent-input-compact w-full"
      bind:value={memberRole}
      placeholder="角色"
    />
    <input
      class="iso-agent-input-compact w-full"
      bind:value={memberGoal}
      placeholder="成员目标/备注（可选）"
    />
    <select class="iso-agent-input-compact w-full" bind:value={memberSendPolicy}>
      <option value="auto">自动发送</option>
      <option value="confirm">发送前确认</option>
      <option value="draft_only">只写草稿</option>
    </select>
    <button
      class="iso-agent-button-primary w-full"
      type="button"
      disabled={!selectedSession}
      onclick={() => onAddMember()}
    >
      添加选中的 Codex
    </button>
  </div>
</section>
