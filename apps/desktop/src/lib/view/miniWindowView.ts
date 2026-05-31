import type { IsotopeSnapshot, SnapshotCounts } from '../contracts/isotope';

export type MiniSubmitMode = 'real' | 'mock' | 'disabled';

export type MiniSubmitPreview = {
  mode: MiniSubmitMode;
  preview: string;
};

export type MiniWindowView = {
  title: string;
  conversationLabel: string;
  agentTitle: string;
  activeGoalTitle: string;
  sourceKind: string;
  submitMode: MiniSubmitMode;
  statusLine: string;
  suggestedPrompts: string[];
  counts: SnapshotCounts;
};

export function buildMiniWindowView(
  snapshot: IsotopeSnapshot,
  submitMode: MiniSubmitMode
): MiniWindowView {
  return {
    title: snapshot.activeActivity?.title ?? snapshot.activeAgent?.title ?? 'Isotope Supervisor',
    conversationLabel: 'AI conversation',
    agentTitle: snapshot.activeAgent?.title ?? 'Isotope Supervisor',
    activeGoalTitle: snapshot.activeGoal?.title ?? 'No active goal',
    sourceKind: snapshot.source.kind,
    submitMode,
    statusLine: [
      countLabel(snapshot.counts.runningAgents, 'running'),
      countLabel(snapshot.counts.needsAttention, 'attention'),
      countLabel(snapshot.counts.approvals, 'approval')
    ].join(' / '),
    suggestedPrompts: ['Summarize current state', 'What needs attention?'],
    counts: snapshot.counts
  };
}

export function buildMockSubmitPreview(text: string): MiniSubmitPreview {
  return {
    mode: 'mock',
    preview: `Mock submit only: ${text.trim()}`
  };
}

function countLabel(count: number, label: string): string {
  if (label === 'attention' || label === 'running') return `${count} ${label}`;
  return `${count} ${label}${count === 1 ? '' : 's'}`;
}
