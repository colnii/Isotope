import { describe, expect, test } from 'vitest';
import type { ActivityNode, IsotopeSnapshot } from '../contracts/isotope';
import { buildMainWindowSnapshotView } from './mainWindowView';

const source = { kind: 'real' as const, label: 'desktop snapshot', backendRef: 'supervisor_state_projection' };

function snapshotWith(): IsotopeSnapshot {
  return {
    schemaVersion: 1,
    snapshotId: 'snapshot-1',
    generatedAt: '2026-05-27T00:00:00Z',
    source,
    activeActivity: {
      id: 'activity_supervisor_root',
      kind: 'supervisor',
      title: 'Isotope Supervisor',
      status: 'running',
      source
    },
    activeAgent: {
      id: 'agent_supervisor',
      title: 'Isotope Supervisor',
      status: 'running',
      kind: 'supervisor',
      source
    },
    activeGoal: {
      id: 'goal-1',
      title: 'Ship desktop MVP',
      status: 'running',
      source
    },
    counts: {
      runningAgents: 1,
      needsAttention: 2,
      approvals: 1,
      artifacts: 3,
      errors: 0
    },
    agents: [],
    activities: [
      {
        id: 'activity_supervisor_root',
        kind: 'supervisor',
        title: 'Isotope Supervisor',
        status: 'running',
        source,
        childIds: ['activity_goal_1'],
        order: 0
      },
      {
        id: 'activity_goal_1',
        kind: 'goal',
        title: 'Ship desktop MVP',
        status: 'running',
        source,
        parentId: 'activity_supervisor_root',
        summary: 'Thin main shell only.',
        order: 0
      }
    ],
    approvals: [
      {
        id: 'approval-1',
        title: 'Review command',
        status: 'pending',
        riskLevel: 'medium',
        source
      }
    ],
    artifacts: [],
    runningToolCalls: []
  };
}

describe('buildMainWindowSnapshotView', () => {
  test('summarizes snapshot state for the thin MainWindow shell', () => {
    const snapshot = snapshotWith();
    const selected = snapshot.activities[1];

    expect(buildMainWindowSnapshotView(snapshot, selected)).toEqual({
      sourceKind: 'real',
      selectedActivityTitle: 'Ship desktop MVP',
      selectedActivityKind: 'goal',
      selectedActivityStatus: 'running',
      selectedActivitySummary: 'Thin main shell only.',
      activeGoalTitle: 'Ship desktop MVP',
      activityCount: 2,
      runningAgents: 1,
      needsAttention: 2,
      approvalCount: 1,
      artifactCount: 3,
      errorCount: 0,
      approvalItems: [{ id: 'approval-1', title: 'Review command', status: 'pending', riskLevel: 'medium' }]
    });
  });

  test('falls back to backend-authored activeActivity when no local activity is selected', () => {
    const snapshot = snapshotWith();

    expect(buildMainWindowSnapshotView(snapshot, null).selectedActivityTitle).toBe('Isotope Supervisor');
  });
});
