import type { ActivityNode, ApprovalSummary, DataSourceInfo, IsotopeSnapshot } from '../contracts/isotope';

export type MainWindowApprovalItem = {
  id: string;
  title: string;
  status: ApprovalSummary['status'];
  riskLevel?: ApprovalSummary['riskLevel'];
  source: DataSourceInfo;
};

export type MainWindowSnapshotView = {
  sourceKind: string;
  selectedActivityTitle: string;
  selectedActivityKind: string;
  selectedActivityStatus: string;
  selectedActivitySummary?: string;
  activeGoalTitle: string;
  activityCount: number;
  runningAgents: number;
  needsAttention: number;
  approvalCount: number;
  artifactCount: number;
  errorCount: number;
  approvalItems: MainWindowApprovalItem[];
};

export function buildMainWindowSnapshotView(
  snapshot: IsotopeSnapshot,
  selectedActivity: ActivityNode | null
): MainWindowSnapshotView {
  const activity =
    selectedActivity ??
    snapshot.activities.find((candidate) => candidate.id === snapshot.activeActivity?.id) ??
    snapshot.activities[0] ??
    null;

  return {
    sourceKind: snapshot.source.kind,
    selectedActivityTitle: activity?.title ?? 'No activity',
    selectedActivityKind: activity?.kind ?? 'unknown',
    selectedActivityStatus: activity?.status ?? 'unknown',
    selectedActivitySummary: activity?.summary,
    activeGoalTitle: snapshot.activeGoal?.title ?? 'No active goal',
    activityCount: snapshot.activities.length,
    runningAgents: snapshot.counts.runningAgents,
    needsAttention: snapshot.counts.needsAttention,
    approvalCount: snapshot.counts.approvals,
    artifactCount: snapshot.counts.artifacts,
    errorCount: snapshot.counts.errors,
    approvalItems: snapshot.approvals.map((approval) => ({
      id: approval.id,
      title: approval.title,
      status: approval.status,
      riskLevel: approval.riskLevel,
      source: approval.source
    }))
  };
}
