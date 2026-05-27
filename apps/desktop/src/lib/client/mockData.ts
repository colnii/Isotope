import type { IsotopeSnapshot } from '../contracts/isotope';

const mockSource = {
  kind: 'mock' as const,
  label: 'desktop_mock_snapshot',
  mockReason: 'The real /desktop/snapshot endpoint is unavailable in this frontend runtime.',
  expectedRealContract: 'IsotopeSnapshot from Python/Supervisor desktop snapshot adapter'
};

export const mockSnapshot: IsotopeSnapshot = {
  schemaVersion: 1,
  snapshotId: 'mock_snapshot_001',
  generatedAt: '2026-05-27T00:00:00Z',
  source: mockSource,
  activeActivity: {
    id: 'activity_supervisor_mock',
    kind: 'supervisor',
    title: 'Mock Supervisor',
    status: 'running',
    source: mockSource
  },
  activeAgent: {
    id: 'supervisor_mock',
    title: 'Mock Supervisor',
    status: 'running',
    kind: 'supervisor',
    role: 'coordinator',
    source: mockSource
  },
  activeGoal: {
    id: 'goal_desktop_mock',
    title: 'Connect the desktop MVP',
    status: 'running',
    source: mockSource
  },
  counts: {
    runningAgents: 1,
    needsAttention: 0,
    approvals: 0,
    artifacts: 0,
    errors: 0
  },
  agents: [
    {
      id: 'supervisor_mock',
      title: 'Mock Supervisor',
      status: 'running',
      kind: 'supervisor',
      role: 'coordinator',
      source: mockSource
    }
  ],
  activities: [
    {
      id: 'activity_supervisor_mock',
      kind: 'supervisor',
      title: 'Mock Supervisor',
      status: 'running',
      source: mockSource,
      order: 0,
      summary: 'Fallback snapshot is active because no desktop API base URL is configured.'
    }
  ],
  approvals: [],
  artifacts: [],
  runningToolCalls: []
};
