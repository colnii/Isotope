import { describe, expect, test } from 'vitest';
import type { IsotopeSnapshot } from '../contracts/isotope';
import { mockSnapshot } from '../client/mockData';
import { buildMiniWindowView } from './miniWindowView';

const realSource = {
  kind: 'real' as const,
  label: 'supervisor_state_projection',
  backendRef: 'supervisor_state:/tmp/isotope'
};

describe('miniWindowView', () => {
  test('builds chat-only MiniWindow copy without monitor counts', () => {
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
        title: 'Supervisor Agent',
        status: 'running',
        kind: 'supervisor',
        role: 'coordinator',
        source: realSource
      },
      activeGoal: {
        id: 'goal-1',
        title: 'Ship MiniWindow shell',
        status: 'running',
        source: {
          kind: 'derived',
          label: 'supervisor_active_goal',
          sourceRef: { kind: 'goal', id: 'goal-1', label: 'Ship MiniWindow shell' }
        }
      },
      counts: {
        runningAgents: 0,
        needsAttention: 2,
        approvals: 1,
        artifacts: 0,
        errors: 0
      },
      agents: [],
      activities: [],
      approvals: [],
      artifacts: [],
      runningToolCalls: []
    };

    const view = buildMiniWindowView(snapshot, 'mock');

    expect(view.title).toBe('Isotope');
    expect(view.conversationLabel).toBe('AI 对话');
    expect(view.submitMode).toBe('mock');
    expect(view.composerPlaceholder).toBe('问问 Isotope');
    expect('counts' in view).toBe(false);
    expect('statusLine' in view).toBe(false);
    expect('activeGoalTitle' in view).toBe(false);
    expect('suggestedPrompts' in view).toBe(false);
  });

  test('keeps fallback snapshots out of visible chat copy', () => {
    const view = buildMiniWindowView(mockSnapshot, 'mock');

    expect(view.title).toBe('Isotope');
    expect('sourceKind' in view).toBe(false);
  });
});
