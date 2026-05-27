import type { IsotopeSnapshot, SnapshotCounts } from '../contracts/isotope';

export type MiniSubmitMode = 'real' | 'mock' | 'disabled';

export type MiniSubmitPreview = {
  mode: MiniSubmitMode;
  preview: string;
};

export type MiniWindowView = {
  title: string;
  agentTitle: string;
  activeGoalTitle: string;
  sourceKind: string;
  submitMode: MiniSubmitMode;
  counts: SnapshotCounts;
};

export function buildMiniWindowView(
  snapshot: IsotopeSnapshot,
  submitMode: MiniSubmitMode
): MiniWindowView {
  return {
    title: snapshot.activeActivity?.title ?? snapshot.activeAgent?.title ?? 'Isotope Supervisor',
    agentTitle: snapshot.activeAgent?.title ?? 'Isotope Supervisor',
    activeGoalTitle: snapshot.activeGoal?.title ?? 'No active goal',
    sourceKind: snapshot.source.kind,
    submitMode,
    counts: snapshot.counts
  };
}

export function buildMockSubmitPreview(text: string): MiniSubmitPreview {
  return {
    mode: 'mock',
    preview: `Mock submit only: ${text.trim()}`
  };
}
