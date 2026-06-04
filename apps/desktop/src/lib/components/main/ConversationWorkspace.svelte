<script lang="ts">
  import CommandComposer from '../common/CommandComposer.svelte';
  import type { AgentClient, ApprovalResolution } from '../../client/agentClient';
  import type { ApprovalSummary } from '../../contracts/isotope';
  import type { DesktopChatMessage } from '../../stores/appState';
  import CapacityCallCard from './CapacityCallCard.svelte';

  let {
    eyebrow,
    title,
    subtitle,
    body,
    emptyTitle,
    emptyBody,
    composerPlaceholder,
    approvals = [],
    resolvingApprovalId = null,
    approvalError = null,
    chatMessages = [],
    chatError = null,
    isAsking = false,
    agentClient,
    onAsk,
    onResolveApproval
  } = $props<{
    eyebrow: string;
    title: string;
    subtitle: string;
    body: string;
    emptyTitle: string;
    emptyBody: string;
    composerPlaceholder: string;
    approvals?: ApprovalSummary[];
    resolvingApprovalId?: string | null;
    approvalError?: string | null;
    chatMessages?: DesktopChatMessage[];
    chatError?: string | null;
    isAsking?: boolean;
    agentClient: AgentClient;
    onAsk: (question: string) => void;
    onResolveApproval: (approvalId: string, resolution: ApprovalResolution) => void;
  }>();

  function approvalSourceLabel(approval: ApprovalSummary): string {
    if (approval.source.label === 'runtime_approval_request') return '运行时审批';
    if (approval.source.label === 'supervisor_decision_request') return 'Supervisor 审批';
    return approval.source.label;
  }

  function approvalDetail(approval: ApprovalSummary): string {
    const summary = approval.requestedActionSummary ?? {};
    const tool = typeof summary.tool === 'string' ? summary.tool : null;
    const command = typeof summary.terminal_command === 'string' ? summary.terminal_command : null;
    const argvCount = typeof summary.argv_count === 'number' ? summary.argv_count : null;
    if (tool === 'terminal_exec' && command) {
      return argvCount === null ? command : `${command} / argv ${argvCount}`;
    }
    if (tool) return tool;
    return approval.reasonCodes?.join(', ') || '等待人工确认';
  }
</script>

<section class="flex min-h-screen min-w-0 flex-col bg-white" aria-label="Conversation workspace">
  <header class="border-b border-isotope-line px-7 py-5">
    <div class="flex items-center justify-between gap-4">
      <div class="min-w-0">
        <div class="text-xs font-semibold uppercase text-isotope-muted">{eyebrow}</div>
        <h1 class="mt-1 truncate text-xl font-semibold text-isotope-text">{title}</h1>
      </div>
      {#if subtitle}
        <div class="shrink-0 border border-isotope-line bg-isotope-panel px-2 py-1 text-xs text-isotope-muted">
          {subtitle}
        </div>
      {/if}
    </div>
  </header>

  <div class="min-h-0 flex flex-1 flex-col overflow-y-auto px-7 py-6" aria-live="polite">
    {#if approvals.length}
      <div class="mx-auto mb-5 w-full max-w-3xl border border-isotope-warning/50 bg-isotope-warning/10">
        <div class="flex items-center justify-between gap-3 border-b border-isotope-warning/30 px-4 py-3">
          <div class="min-w-0">
            <div class="text-xs font-semibold uppercase text-isotope-warning">Pending approval</div>
            <div class="mt-1 text-sm font-semibold text-isotope-text">有 {approvals.length} 个操作等待批准</div>
          </div>
        </div>
        <div class="divide-y divide-isotope-warning/20">
          {#each approvals as approval (approval.id)}
            <article class="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="truncate text-sm font-semibold text-isotope-text">{approval.title}</span>
                  <span class="border border-isotope-warning/40 bg-white px-2 py-0.5 text-[11px] uppercase text-isotope-warning">
                    {approvalSourceLabel(approval)}
                  </span>
                </div>
                <div class="mt-1 text-xs text-isotope-muted">
                  {approvalDetail(approval)}
                </div>
              </div>
              <div class="flex shrink-0 items-center gap-2">
                <button
                  type="button"
                  class="border border-isotope-line bg-white px-3 py-1.5 text-xs font-semibold text-isotope-muted disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={resolvingApprovalId === approval.id}
                  onclick={() => onResolveApproval(approval.id, 'denied')}
                >
                  拒绝
                </button>
                <button
                  type="button"
                  class="border border-isotope-running bg-isotope-running px-3 py-1.5 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={resolvingApprovalId === approval.id}
                  onclick={() => onResolveApproval(approval.id, 'approved')}
                >
                  {resolvingApprovalId === approval.id ? '处理中' : '批准'}
                </button>
              </div>
            </article>
          {/each}
        </div>
      </div>
    {/if}
    {#if chatMessages.length === 0}
      <div class="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center gap-4">
        <article class="flex items-start gap-3">
          <div class="grid h-9 w-9 shrink-0 place-items-center border border-isotope-line bg-isotope-bg text-xs font-semibold text-isotope-running">
            AI
          </div>
          <div class="min-w-0 flex-1 border border-isotope-line bg-isotope-bg px-4 py-3">
            <div class="text-sm font-semibold text-isotope-text">{emptyTitle}</div>
            {#if emptyBody}
              <p class="mt-2 text-sm leading-6 text-isotope-muted">{emptyBody}</p>
            {/if}
            {#if body}
              <div class="mt-3 border-l-2 border-isotope-line pl-3 text-sm leading-6 text-isotope-muted">
                {body}
              </div>
            {/if}
          </div>
        </article>
      </div>
    {:else}
      <div class="mx-auto mt-auto flex w-full max-w-3xl flex-col gap-4">
        {#each chatMessages as message (message.id)}
          <article
            class={[
              'flex w-full items-end gap-3',
              message.role === 'user' ? 'justify-end' : 'justify-start'
            ]}
          >
            {#if message.role === 'assistant'}
              <div class="grid h-8 w-8 shrink-0 place-items-center border border-isotope-line bg-isotope-bg text-xs font-semibold text-isotope-running">
                AI
              </div>
            {/if}
            <div
              class={[
                'min-w-0 border px-4 py-3 text-sm leading-6 shadow-sm',
                message.role === 'user'
                  ? 'max-w-[min(72%,32rem)] border-isotope-running bg-isotope-running text-white'
                  : 'max-w-[min(82%,40rem)] border-isotope-line bg-isotope-bg text-isotope-text'
              ]}
            >
              {#if message.role === 'assistant'}
                <div class="mb-1 text-xs font-semibold text-isotope-muted">Isotope</div>
              {/if}
              {#if message.content}
                <p class="whitespace-pre-wrap break-words">{message.content}</p>
              {:else}
                <p class="text-isotope-muted">...</p>
              {/if}
              {#if message.role === 'assistant' && message.capacityCalls?.length}
                <div class="mt-3 space-y-2">
                  {#each message.capacityCalls as call (call.id)}
                    <CapacityCallCard {call} {agentClient} />
                  {/each}
                </div>
              {/if}
              {#if message.role === 'assistant' && (message.provider || message.model)}
                <div class="mt-2 text-[11px] uppercase text-isotope-muted">
                  {[message.provider, message.model].filter(Boolean).join(' / ')}
                </div>
              {/if}
            </div>
          </article>
        {/each}
      </div>
    {/if}
  </div>

  <div class="border-t border-isotope-line bg-white px-7 py-4">
    <div class="mx-auto max-w-3xl">
    {#if chatError}
      <div class="mb-3 border border-isotope-error/40 bg-white px-3 py-2 text-xs text-isotope-error" role="alert">
        {chatError}
      </div>
    {/if}
    {#if approvalError}
      <div class="mb-3 border border-isotope-error/40 bg-white px-3 py-2 text-xs text-isotope-error" role="alert">
        {approvalError}
      </div>
    {/if}
    <CommandComposer placeholder={composerPlaceholder} disabled={isAsking} onSubmit={onAsk} />
    </div>
  </div>
</section>
