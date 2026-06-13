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
    const path = typeof summary.path === 'string' ? summary.path : null;
    const maxExcerptChars =
      typeof summary.max_excerpt_chars === 'number' ? summary.max_excerpt_chars : null;
    if (tool === 'local_file_read' && path) {
      return maxExcerptChars === null ? path : `${path} / 最多 ${maxExcerptChars} 字符`;
    }
    if (tool === 'terminal_exec' && command) {
      return argvCount === null ? command : `${command} / argv ${argvCount}`;
    }
    if (tool) return tool;
    return approval.reasonCodes?.join(', ') || '等待人工确认';
  }
</script>

<section class="iso-chat-shell" aria-label="Conversation workspace">
  <header class="iso-chat-header">
    <div class="iso-chat-header-copy">
      <div class="iso-chat-eyebrow">{eyebrow}</div>
      <h1 class="iso-chat-title">{title}</h1>
      {#if subtitle}
        <div class="iso-chat-subtitle">{subtitle}</div>
      {/if}
    </div>
    <div class="iso-suprematist-mark" aria-hidden="true">
      <span class="iso-suprematist-square"></span>
      <span class="iso-suprematist-yellow"></span>
      <span class="iso-suprematist-ring"></span>
      <span class="iso-suprematist-blue"></span>
      <span class="iso-suprematist-red"></span>
      <span class="iso-suprematist-ink"></span>
      <span class="iso-suprematist-link"></span>
    </div>
  </header>

  <div class="iso-chat-scroll" aria-live="polite">
    {#if approvals.length}
      <div class="iso-approval-card">
        <div class="flex items-center justify-between gap-3 border-b border-isotope-yellow/40 px-4 py-3">
          <div class="min-w-0">
            <div class="text-xs font-semibold uppercase text-isotope-red">Pending approval</div>
            <div class="mt-1 text-sm font-semibold text-isotope-text">有 {approvals.length} 个操作等待批准</div>
          </div>
        </div>
        <div class="divide-y divide-isotope-yellow/40">
          {#each approvals as approval (approval.id)}
            <article class="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="truncate text-sm font-semibold text-isotope-text">{approval.title}</span>
                  <span class="iso-status-chip border-isotope-yellow bg-isotope-panel-raised text-isotope-red">
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
                  class="iso-button-muted"
                  disabled={resolvingApprovalId === approval.id}
                  onclick={() => onResolveApproval(approval.id, 'denied')}
                >
                  拒绝
                </button>
                <button
                  type="button"
                  class="iso-button-primary"
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
          <div class="iso-message-avatar">
            AI
          </div>
          <div class="iso-message-bubble iso-message-bubble-assistant flex-1">
            <div class="text-sm font-semibold text-isotope-text">{emptyTitle}</div>
            {#if emptyBody}
              <p class="mt-2 text-sm leading-6 text-isotope-muted">{emptyBody}</p>
            {/if}
            {#if body}
              <div class="mt-3 border-l border-isotope-line pl-3 text-sm leading-6 text-isotope-muted">
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
              <div class="iso-message-avatar">
                AI
              </div>
            {/if}
            <div
              class={[
                message.role === 'user'
                  ? 'iso-message-bubble-user'
                  : 'iso-message-bubble iso-message-bubble-assistant'
              ]}
            >
              {#if message.role === 'assistant'}
                <div class="mb-1 text-xs font-semibold text-isotope-muted">Isotope</div>
              {/if}
              {#if message.role === 'assistant' && message.parts?.length}
                <div class="space-y-3">
                  {#each message.parts as part (part.id)}
                    {#if part.kind === 'capacity'}
                      <CapacityCallCard call={part.call} {agentClient} />
                    {:else if part.text}
                      <p class="whitespace-pre-wrap break-words">{part.text}</p>
                    {/if}
                  {/each}
                </div>
              {:else}
                {#if message.role === 'assistant' && message.capacityCalls?.length}
                  <div class="mb-3 space-y-2">
                    {#each message.capacityCalls as call (call.id)}
                      <CapacityCallCard {call} {agentClient} />
                    {/each}
                  </div>
                {/if}
                {#if message.content}
                  <p class="whitespace-pre-wrap break-words">{message.content}</p>
                {:else if !(message.role === 'assistant' && message.capacityCalls?.length)}
                  <p class="text-isotope-muted">...</p>
                {/if}
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

  <div class="border-t border-isotope-line bg-isotope-panel px-7 py-4">
    <div class="mx-auto max-w-3xl">
      {#if chatError}
        <div class="iso-error-card" role="alert">
          {chatError}
        </div>
      {/if}
      {#if approvalError}
        <div class="iso-error-card" role="alert">
          {approvalError}
        </div>
      {/if}
      <CommandComposer placeholder={composerPlaceholder} disabled={isAsking} onSubmit={onAsk} />
    </div>
  </div>
</section>
