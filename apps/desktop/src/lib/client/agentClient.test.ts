import { describe, expect, test, vi } from 'vitest';
import type { IsotopeSnapshot } from '../contracts/isotope';
import { createAgentClient } from './agentClient';

const realSource = {
  kind: 'real' as const,
  label: 'supervisor_state_projection',
  backendRef: 'codex_home:/tmp/isotope'
};

const realSnapshot: IsotopeSnapshot = {
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

describe('agentClient', () => {
  test('loads real desktop snapshot from configured base URL', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(realSnapshot), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    const snapshot = await createAgentClient('http://127.0.0.1:8765').loadSnapshot();

    expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8765/desktop/snapshot', { cache: 'no-store' });
    expect(snapshot.source.kind).toBe('real');
    expect(snapshot.counts.approvals).toBe(snapshot.approvals.length);
    expect('eventCursor' in snapshot).toBe(false);
    expect('lastEventId' in snapshot).toBe(false);
  });

  test('falls back to marked mock snapshot when real endpoint is unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('missing', { status: 404 })));

    const snapshot = await createAgentClient('http://127.0.0.1:8765').loadSnapshot();

    expect(snapshot.source.kind).toBe('mock');
    expect(snapshot.source.expectedRealContract).toContain('IsotopeSnapshot');
  });
});
