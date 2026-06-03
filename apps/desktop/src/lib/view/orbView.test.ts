import { describe, expect, test } from 'vitest';
import type { IsotopeSnapshot } from '../contracts/isotope';
import { mockSnapshot } from '../client/mockData';
import { buildFloatingOrbButtonTitle, buildFloatingOrbView } from './orbView';

const realSource = {
  kind: 'real' as const,
  label: 'supervisor_state_projection',
  backendRef: 'supervisor_state:/tmp/isotope'
};

describe('orbView', () => {
  test('summarizes real snapshot state for FloatingOrb', () => {
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

    const view = buildFloatingOrbView(snapshot);

    expect(view.label).toBe('Isotope Supervisor');
    expect(view.status).toBe('空闲');
    expect(view.needsAttention).toBe(2);
    expect(view.source.kind).toBe('real');
    expect(view.attentionText).toBe('2');
  });

  test('keeps mock source visible for fallback snapshots', () => {
    const view = buildFloatingOrbView(mockSnapshot);

    expect(view.label).toBe('模拟 Supervisor');
    expect(view.source.kind).toBe('mock');
    expect(view.attentionText).toBeNull();
  });

  test('omits browser tooltip text for native window surface', () => {
    expect(buildFloatingOrbButtonTitle('window', '模拟 Supervisor / 运行中 / 模拟数据')).toBeNull();
    expect(buildFloatingOrbButtonTitle('dev', '模拟 Supervisor / 运行中 / 模拟数据')).toBe(
      '模拟 Supervisor / 运行中 / 模拟数据'
    );
  });
});
