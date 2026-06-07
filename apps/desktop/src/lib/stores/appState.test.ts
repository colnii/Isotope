import { get } from 'svelte/store';
import { describe, expect, test } from 'vitest';
import type { IsotopeSnapshot } from '../contracts/isotope';
import { createAppState } from './appState';

const realSource = {
  kind: 'real' as const,
  label: 'supervisor_state_projection',
  backendRef: 'supervisor_state:/tmp/isotope'
};

function realSnapshot(): IsotopeSnapshot {
  return {
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
      },
      {
        id: 'activity_goal_goal-1',
        kind: 'goal',
        title: 'Ship the desktop MVP',
        status: 'running',
        source: {
          kind: 'derived',
          label: 'supervisor_active_goal',
          sourceRef: { kind: 'goal', id: 'goal-1', label: 'Ship the desktop MVP' }
        },
        parentId: 'activity_supervisor_root',
        sourceRef: { kind: 'goal', id: 'goal-1', label: 'Ship the desktop MVP' },
        order: 1
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
}

describe('appState', () => {
  test('loads real snapshot and initializes local selected activity from backend activeActivity', async () => {
    const state = createAppState({
      agentClient: {
        loadSnapshot: async () => realSnapshot(),
        loadScreenArtifactContent: async () => { throw new Error('not used'); },
        resolveApproval: async () => ({
          status: 'ok',
          approvalId: 'decision-1',
          resolution: 'approved',
          runStatus: 'completed',
          snapshot: realSnapshot()
        }),
        askDesktopQuestion: async () => ({ question: '', answer: '' })
      }
    });

    await state.initialize();

    expect(get(state.snapshot)?.source.kind).toBe('real');
    expect(get(state.selectedActivityId)).toBe('activity_supervisor_root');
    expect(get(state.selectedActivity)?.kind).toBe('supervisor');
    expect(get(state.snapshot)?.counts.approvals).toBe(1);
  });

  test('keeps user-selected activity local without changing backend activeActivity', async () => {
    const state = createAppState({
      agentClient: {
        loadSnapshot: async () => realSnapshot(),
        loadScreenArtifactContent: async () => { throw new Error('not used'); },
        resolveApproval: async () => ({
          status: 'ok',
          approvalId: 'decision-1',
          resolution: 'approved',
          runStatus: 'completed',
          snapshot: realSnapshot()
        }),
        askDesktopQuestion: async () => ({ question: '', answer: '' })
      }
    });

    await state.initialize();
    state.selectActivity('activity_goal_goal-1');

    expect(get(state.selectedActivityId)).toBe('activity_goal_goal-1');
    expect(get(state.selectedActivity)?.title).toBe('Ship the desktop MVP');
    expect(get(state.snapshot)?.activeActivity?.id).toBe('activity_supervisor_root');
  });

  test('submits desktop question and updates assistant message from backend stream deltas', async () => {
    const state = createAppState({
      agentClient: {
        loadSnapshot: async () => realSnapshot(),
        loadScreenArtifactContent: async () => { throw new Error('not used'); },
        resolveApproval: async () => ({
          status: 'ok',
          approvalId: 'decision-1',
          resolution: 'approved',
          runStatus: 'completed',
          snapshot: realSnapshot()
        }),
        askDesktopQuestion: async (question, handlers) => {
          handlers?.onCapacityStart?.({
            id: 'capacity_memory_query',
            capacityId: 'memory.query',
            title: 'Memory Query',
            status: 'running',
            inputSummary: { query: 'loop' },
            resultSummary: {},
            details: []
          });
          handlers?.onDelta?.('后端');
          handlers?.onDelta?.(' 回答');
          handlers?.onCapacityResult?.({
            id: 'capacity_memory_query',
            capacityId: 'memory.query',
            title: 'Memory Query',
            status: 'ok',
            inputSummary: { query: 'loop' },
            resultSummary: { result_count: 2 },
            details: [{ label: 'Results', kind: 'json', content: { result_count: 2 } }]
          });
          return {
            question,
            answer: '后端 回答',
            provider: 'deterministic_test',
            model: 'deterministic_test',
            capacityCalls: [
              {
                id: 'capacity_memory_query',
                capacityId: 'memory.query',
                title: 'Memory Query',
                status: 'ok',
                inputSummary: { query: 'loop' },
                resultSummary: { result_count: 2 },
                details: [{ label: 'Results', kind: 'json', content: { result_count: 2 } }]
              }
            ]
          };
        }
      }
    });

    await state.initialize();
    await state.askDesktopQuestion('loop 现在怎样？');

    expect(get(state.chatMessages)).toEqual([
      {
        id: 'chat_user_1',
        role: 'user',
        content: 'loop 现在怎样？'
      },
      {
        id: 'chat_assistant_1',
        role: 'assistant',
        content: '后端 回答',
        provider: 'deterministic_test',
        model: 'deterministic_test',
        capacityCalls: [
          {
            id: 'capacity_memory_query',
            capacityId: 'memory.query',
            title: 'Memory Query',
            status: 'ok',
            inputSummary: { query: 'loop' },
            resultSummary: { result_count: 2 },
            details: [{ label: 'Results', kind: 'json', content: { result_count: 2 } }]
          }
        ]
      }
    ]);
    expect(get(state.isAskingDesktop)).toBe(false);
    expect(get(state.chatError)).toBe(null);
  });

  test('refreshes desktop snapshot after a successful chat turn', async () => {
    const before = realSnapshot();
    const after: IsotopeSnapshot = {
      ...realSnapshot(),
      snapshotId: 'desktop_snapshot_after_chat',
      counts: {
        runningAgents: 1,
        needsAttention: 0,
        approvals: 0,
        artifacts: 1,
        errors: 0
      }
    };
    let loadCount = 0;
    const state = createAppState({
      agentClient: {
        loadSnapshot: async () => {
          loadCount += 1;
          return loadCount === 1 ? before : after;
        },
        loadScreenArtifactContent: async () => { throw new Error('not used'); },
        resolveApproval: async () => ({
          status: 'ok',
          approvalId: 'decision-1',
          resolution: 'approved',
          runStatus: 'completed',
          snapshot: after
        }),
        askDesktopQuestion: async (question) => ({
          question,
          answer: '已执行动作。',
          provider: 'deterministic_test',
          model: 'deterministic_test'
        })
      }
    });

    await state.initialize();
    await state.askDesktopQuestion('检查项目态势');

    expect(loadCount).toBe(2);
    expect(get(state.snapshot)?.snapshotId).toBe('desktop_snapshot_after_chat');
    expect(get(state.snapshot)?.counts.runningAgents).toBe(1);
    expect(get(state.chatError)).toBe(null);
  });

  test('submits previous chat messages as session history on follow-up questions', async () => {
    const calls: Array<{ question: string; history?: Array<{ role: string; content: string }> }> = [];
    const state = createAppState({
      agentClient: {
        loadSnapshot: async () => realSnapshot(),
        loadScreenArtifactContent: async () => { throw new Error('not used'); },
        resolveApproval: async () => ({
          status: 'ok',
          approvalId: 'decision-1',
          resolution: 'approved',
          runStatus: 'completed',
          snapshot: realSnapshot()
        }),
        askDesktopQuestion: async (question, handlers) => {
          calls.push({
            question,
            history: handlers?.history
          });
          return {
            question,
            answer: question === '第一句' ? '第一句回复' : '第二句回复',
            provider: 'deterministic_test',
            model: 'deterministic_test'
          };
        }
      }
    });

    await state.initialize();
    await state.askDesktopQuestion('第一句');
    await state.askDesktopQuestion('我的上句话是什么');

    expect(calls).toEqual([
      {
        question: '第一句',
        history: []
      },
      {
        question: '我的上句话是什么',
        history: [
          { role: 'user', content: '第一句' },
          { role: 'assistant', content: '第一句回复' }
        ]
      }
    ]);
  });

  test('keeps capacity cards out of frontend chat history', async () => {
    const calls: Array<{ question: string; history?: Array<{ role: string; content: string }> }> = [];
    const state = createAppState({
      agentClient: {
        loadSnapshot: async () => realSnapshot(),
        loadScreenArtifactContent: async () => { throw new Error('not used'); },
        resolveApproval: async () => ({
          status: 'ok',
          approvalId: 'decision-1',
          resolution: 'approved',
          runStatus: 'completed',
          snapshot: realSnapshot()
        }),
        askDesktopQuestion: async (question, handlers) => {
          calls.push({
            question,
            history: handlers?.history
          });
          if (question === '调研 Agent OS') {
            return {
              question,
              answer: '调研和规划已完成。',
              provider: 'deterministic_test',
              model: 'deterministic_test',
              capacityCalls: [
                {
                  id: 'capacity_research_search',
                  capacityId: 'research.search',
                  title: '检索资料',
                  status: 'ok',
                  inputSummary: { query: 'Agent OS 前沿设计 2025 2026' },
                  resultSummary: {
                    agent_loop_research_provider: 'tavily',
                    agent_loop_research_report: 'Tavily returned 5 source-backed results.',
                    agent_loop_research_source_count: 5
                  },
                  details: [
                    {
                      label: 'Result',
                      kind: 'json',
                      content: {
                        agent_loop_research_source_previews: [
                          {
                            provider_rank: 1,
                            source_id: 'src_001',
                            title: 'Agentic OS 技术详解',
                            url: 'https://example.test/agentic-os',
                            snippet: 'Agent OS 强调调度、记忆、sandbox runtime。',
                            why_used: 'Tavily search result rank 1'
                          }
                        ]
                      }
                    }
                  ]
                }
              ]
            };
          }
          return {
            question,
            answer: '基于上一轮调研解释。',
            provider: 'deterministic_test',
            model: 'deterministic_test'
          };
        }
      }
    });

    await state.initialize();
    await state.askDesktopQuestion('调研 Agent OS');
    await state.askDesktopQuestion('给我讲一下');

    const followUpHistory = calls[1].history ?? [];
    expect(followUpHistory).toContainEqual({
      role: 'assistant',
      content: '调研和规划已完成。'
    });
    const serialized = JSON.stringify(followUpHistory);
    expect(serialized).not.toContain('desktop_capacity_history');
    expect(serialized).not.toContain('research.search');
    expect(serialized).not.toContain('Tavily returned 5 source-backed results.');
  });

  test('resolves approval and refreshes snapshot from backend response', async () => {
    const before = realSnapshot();
    const after: IsotopeSnapshot = {
      ...realSnapshot(),
      snapshotId: 'desktop_snapshot_after_approval',
      counts: {
        runningAgents: 0,
        needsAttention: 0,
        approvals: 0,
        artifacts: 0,
        errors: 0
      },
      approvals: []
    };
    const resolved: Array<{ approvalId: string; resolution: string; reason?: string }> = [];
    const state = createAppState({
      agentClient: {
        loadSnapshot: async () => before,
        loadScreenArtifactContent: async () => { throw new Error('not used'); },
        resolveApproval: async (approvalId, resolution, reason) => {
          resolved.push({ approvalId, resolution, reason });
          return {
            status: 'ok',
            approvalId,
            resolution,
            runStatus: 'completed',
            snapshot: after
          };
        },
        askDesktopQuestion: async () => ({ question: '', answer: '' })
      }
    });

    await state.initialize();
    await state.resolveApproval('decision-1', 'approved');

    expect(resolved).toEqual([
      {
        approvalId: 'decision-1',
        resolution: 'approved',
        reason: 'desktop operator approved'
      }
    ]);
    expect(get(state.snapshot)?.snapshotId).toBe('desktop_snapshot_after_approval');
    expect(get(state.snapshot)?.approvals).toEqual([]);
    expect(get(state.isResolvingApproval)).toBe(null);
    expect(get(state.approvalError)).toBe(null);
  });
});
