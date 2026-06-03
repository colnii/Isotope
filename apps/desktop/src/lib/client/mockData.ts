import type { IsotopeSnapshot } from '../contracts/isotope';

const mockSource = {
  kind: 'mock' as const,
  label: 'desktop_mock_snapshot',
  mockReason: '当前前端运行环境无法访问真实 /desktop/snapshot 端点。',
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
    title: '模拟 Supervisor',
    status: 'running',
    source: mockSource
  },
  activeAgent: {
    id: 'supervisor_mock',
    title: '模拟 Supervisor',
    status: 'running',
    kind: 'supervisor',
    role: 'coordinator',
    source: mockSource
  },
  activeGoal: {
    id: 'goal_desktop_mock',
    title: '连接桌面 MVP',
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
      title: '模拟 Supervisor',
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
      title: '模拟 Supervisor',
      status: 'running',
      source: mockSource,
      order: 0,
      summary: '未配置桌面 API 地址，当前使用 fallback 快照。'
    }
  ],
  approvals: [],
  artifacts: [],
  runningToolCalls: []
};
