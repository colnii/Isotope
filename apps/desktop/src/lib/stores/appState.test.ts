import { get } from 'svelte/store';
import { describe, expect, test } from 'vitest';
import type { IsotopeSnapshot } from '../contracts/isotope';
import { createAppState } from './appState';

const realSource = {
  kind: 'real' as const,
  label: 'supervisor_state_projection',
  backendRef: 'codex_home:/tmp/isotope'
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
            provider: 'fake',
            model: 'fake',
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
        provider: 'fake',
        model: 'fake',
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
});
