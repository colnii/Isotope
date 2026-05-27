import { describe, expect, test } from 'vitest';
import type { IsotopeSnapshot } from '../contracts/isotope';
import { buildSnapshotView } from './snapshotView';

const realSource = {
  kind: 'real' as const,
  label: 'supervisor_state_projection',
  backendRef: 'codex_home:/tmp/isotope'
};

describe('snapshotView', () => {
  test('maps a real snapshot into page-facing display state', () => {
    const snapshot: IsotopeSnapshot = {
      schemaVersion: 1,
      snapshotId: 'desktop_snapshot_real',
      generatedAt: '2026-05-27T00:00:00Z',
      source: realSource,
      activeActivity: {
        id: 'activity_supervisor_root',
        kind: 'supervisor',
        title: 'Isotope Supervisor',
        status: 'idle',
        source: realSource
      },
      activeAgent: {
        id: 'supervisor_root',
        title: 'Isotope Supervisor',
        status: 'idle',
        kind: 'supervisor',
        role: 'coordinator',
        source: realSource
      },
      activeGoal: {
        id: 'goal-1',
        title: 'Ship the desktop MVP',
        status: 'running',
        source: {
          kind: 'derived',
          label: 'supervisor_active_goal',
          sourceRef: { kind: 'goal', id: 'goal-1', label: 'Ship the desktop MVP' }
        }
      },
      counts: {
        runningAgents: 0,
        needsAttention: 1,
        approvals: 1,
        artifacts: 0,
        errors: 0
      },
      agents: [],
      activities: [
        {
          id: 'activity_supervisor_root',
          kind: 'supervisor',
          title: 'Isotope Supervisor',
          status: 'idle',
          source: realSource,
          order: 0
        }
      ],
      approvals: [
        {
          id: 'decision-1',
          title: 'Approve launch?',
          status: 'pending',
          source: {
            kind: 'derived',
            label: 'supervisor_decision_request',
            sourceRef: { kind: 'approval', id: 'decision-1', label: 'Approve launch?' }
          }
        }
      ],
      artifacts: [],
      runningToolCalls: []
    };

    const view = buildSnapshotView(snapshot, snapshot.activities[0]);

    expect(view.agentTitle).toBe('Isotope Supervisor');
    expect(view.activeGoalTitle).toBe('Ship the desktop MVP');
    expect(view.selectedActivityTitle).toBe('Isotope Supervisor');
    expect(view.sourceKind).toBe('real');
    expect(view.approvalCount).toBe(1);
    expect(view.needsAttention).toBe(1);
  });
});
