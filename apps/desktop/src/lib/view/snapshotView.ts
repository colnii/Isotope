import type { ActivityNode, IsotopeSnapshot } from '../contracts/isotope';

export type SnapshotView = {
  agentTitle: string;
  activeGoalTitle: string;
  selectedActivityTitle: string;
  sourceKind: string;
  activityCount: number;
  approvalCount: number;
  needsAttention: number;
};

export function buildSnapshotView(
  snapshot: IsotopeSnapshot,
  selectedActivity: ActivityNode | null
): SnapshotView {
  return {
    agentTitle: snapshot.activeAgent?.title ?? 'Isotope Supervisor',
    activeGoalTitle: snapshot.activeGoal?.title ?? 'No active goal',
    selectedActivityTitle:
      selectedActivity?.title ?? snapshot.activeActivity?.title ?? snapshot.activities[0]?.title ?? 'No activity',
    sourceKind: snapshot.source.kind,
    activityCount: snapshot.activities.length,
    approvalCount: snapshot.counts.approvals,
    needsAttention: snapshot.counts.needsAttention
  };
}
