import { describe, expect, test } from 'vitest';
import type { IsotopeSnapshot } from '../contracts/isotope';
import { mockSnapshot } from '../client/mockData';
import { buildMiniWindowView, buildMockSubmitPreview } from './miniWindowView';

const realSource = {
  kind: 'real' as const,
  label: 'supervisor_state_projection',
  backendRef: 'codex_home:/tmp/isotope'
};

describe('miniWindowView', () => {
  test('summarizes real snapshot state for MiniWindow', () => {
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

    expect(view.title).toBe('Isotope Supervisor');
    expect(view.agentTitle).toBe('Supervisor Agent');
    expect(view.activeGoalTitle).toBe('Ship MiniWindow shell');
    expect(view.sourceKind).toBe('real');
    expect(view.submitMode).toBe('mock');
    expect(view.counts.needsAttention).toBe(2);
    expect(view.conversationLabel).toBe('AI conversation');
    expect(view.statusLine).toBe('0 running / 2 attention / 1 approval');
    expect(view.suggestedPrompts).toEqual([
      'Summarize current state',
      'What needs attention?'
    ]);
  });

  test('keeps mock source visible for fallback snapshots', () => {
    const view = buildMiniWindowView(mockSnapshot, 'mock');

    expect(view.sourceKind).toBe('mock');
    expect(view.title).toBe('Mock Supervisor');
  });

  test('builds local-only mock submit preview without claiming real interaction', () => {
    expect(buildMockSubmitPreview('  inspect state  ')).toEqual({
      mode: 'mock',
      preview: 'Mock submit only: inspect state'
    });
  });
});
