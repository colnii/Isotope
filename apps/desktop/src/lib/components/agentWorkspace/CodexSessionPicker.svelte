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
    <div class="text-sm font-semibold">Codex sessions</div>
    <div class="flex gap-1">
      <button
        class={`border px-2 py-1 text-xs font-semibold ${
          sessionScope === 'cwd'
            ? 'border-isotope-running bg-white text-isotope-running'
            : 'border-isotope-line bg-white text-isotope-muted'
        }`}
        type="button"
        onclick={() => {
          sessionScope = 'cwd';
          onLoadCodexSessions(sessionScope);
        }}
      >
        cwd
      </button>
      <button
        class={`border px-2 py-1 text-xs font-semibold ${
          sessionScope === 'all'
            ? 'border-isotope-running bg-white text-isotope-running'
            : 'border-isotope-line bg-white text-isotope-muted'
        }`}
        type="button"
        onclick={() => {
          sessionScope = 'all';
          onLoadCodexSessions(sessionScope);
        }}
      >
        all
      </button>
    </div>
  </div>

  <div class="max-h-44 space-y-2 overflow-y-auto">
    {#if isLoadingSessions}
      <div class="border border-isotope-line bg-white px-3 py-2 text-xs text-isotope-muted">Loading</div>
    {:else}
      {#each sessionCandidates as candidate (candidate.session_id)}
        <button
          class={`w-full border px-3 py-2 text-left ${
            selectedSessionId === candidate.session_id
              ? 'border-isotope-running bg-white'
              : 'border-isotope-line bg-white'
          }`}
          type="button"
          onclick={() => onSelectSession(candidate)}
        >
          <div class="truncate text-xs font-semibold">{candidate.title || candidate.short_session_id}</div>
          <div class="mt-1 truncate text-[11px] text-isotope-muted">{candidate.cwd ?? candidate.source_path}</div>
        </button>
      {/each}
    {/if}
  </div>

  <div class="mt-3 space-y-2">
    <input
      class="w-full border border-isotope-line bg-white px-2 py-1.5 text-xs"
      bind:value={memberDisplayName}
      placeholder="Display name"
    />
    <input
      class="w-full border border-isotope-line bg-white px-2 py-1.5 text-xs"
      bind:value={memberRole}
      placeholder="Role"
    />
    <input
      class="w-full border border-isotope-line bg-white px-2 py-1.5 text-xs"
      bind:value={memberGoal}
      placeholder="Goal"
    />
    <select class="w-full border border-isotope-line bg-white px-2 py-1.5 text-xs" bind:value={memberSendPolicy}>
      <option value="auto">auto</option>
      <option value="confirm">confirm</option>
      <option value="draft_only">draft_only</option>
    </select>
    <button
      class="w-full border border-isotope-running bg-isotope-running px-3 py-2 text-xs font-semibold text-white"
      type="button"
      disabled={!selectedSession}
      onclick={() => onAddMember()}
    >
      Add selected Codex
    </button>
  </div>
</section>
