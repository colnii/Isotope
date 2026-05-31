import type { ActivityNode, DataSourceKind, IsotopeSnapshot } from '../contracts/isotope';

export type MainWindowProductView = {
  activityRailTitle: string;
  chatEyebrow: string;
  workspaceTitle: string;
  workspaceSubtitle: string;
  workspaceBody: string;
  emptyChatTitle: string;
  emptyChatBody: string;
  composerPlaceholder: string;
  inspectorTitle: string;
  inspectorSummary: string;
  sourceKind: DataSourceKind;
};

export function buildMainWindowProductView(
  snapshot: IsotopeSnapshot,
  selectedActivity: ActivityNode | null
): MainWindowProductView {
  const activeAgentTitle = snapshot.activeAgent?.title ?? 'Isotope';
  const selectedTitle =
    selectedActivity?.title ?? snapshot.activeActivity?.title ?? snapshot.activities[0]?.title ?? 'Current activity';

  return {
    activityRailTitle: 'Activities',
    chatEyebrow: 'Supervisor chat',
    workspaceTitle: snapshot.activeGoal?.title ?? selectedTitle,
    workspaceSubtitle: activeAgentTitle,
    workspaceBody: selectedActivity?.summary ?? 'Current activity context will appear here as the supervisor works.',
    emptyChatTitle: 'Ask Isotope about this workspace',
    emptyChatBody: 'Use the composer to inspect goals, workers, approvals, and recent events.',
    composerPlaceholder: 'Ask Isotope about this run',
    inspectorTitle: 'Inspector',
    inspectorSummary: `${snapshot.counts.runningAgents} running · ${snapshot.counts.needsAttention} attention · ${snapshot.counts.approvals} approvals`,
    sourceKind: snapshot.source.kind
  };
}
