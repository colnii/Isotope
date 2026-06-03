import type { ActivityNode, ApprovalSummary, DataSourceInfo, IsotopeSnapshot } from '../contracts/isotope';
import { activityKindLabel, activityStatusLabel, approvalRiskLabel, approvalStatusLabel } from './labels';

export type MainWindowApprovalItem = {
  id: string;
  title: string;
  status: string;
  riskLevel?: string;
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
    selectedActivityTitle: activity?.title ?? '暂无活动',
    selectedActivityKind: activity ? activityKindLabel(activity.kind) : '未知',
    selectedActivityStatus: activity ? activityStatusLabel(activity.status) : '未知',
    selectedActivitySummary: activity?.summary,
    activeGoalTitle: snapshot.activeGoal?.title ?? '暂无活跃目标',
    activityCount: snapshot.activities.length,
    runningAgents: snapshot.counts.runningAgents,
    needsAttention: snapshot.counts.needsAttention,
    approvalCount: snapshot.counts.approvals,
    artifactCount: snapshot.counts.artifacts,
    errorCount: snapshot.counts.errors,
    approvalItems: snapshot.approvals.map((approval) => ({
      id: approval.id,
      title: approval.title,
      status: approvalStatusLabel(approval.status),
      riskLevel: approvalRiskLabel(approval.riskLevel),
      source: approval.source
    }))
  };
}
