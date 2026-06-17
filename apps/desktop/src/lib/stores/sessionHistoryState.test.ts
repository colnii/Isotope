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
    counts: {
      runningAgents: 0,
      needsAttention: 0,
      approvals: 0,
      artifacts: 0,
      errors: 0
    },
    agents: [],
    activities: [],
    approvals: [],
    artifacts: [],
    runningToolCalls: []
  };
}

function memoryStorage(seed: Record<string, string> = {}) {
  const values = new Map(Object.entries(seed));
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
    removeItem: (key: string) => {
      values.delete(key);
    },
    value: (key: string) => values.get(key) ?? null
  };
}

function appState(storage = memoryStorage()) {
  const calls: Array<{ question: string; history?: Array<{ role: string; content: string }> }> = [];
  const state = createAppState(
    {
      agentClient: {
        loadSnapshot: async () => realSnapshot(),
        loadScreenArtifactContent: async () => { throw new Error('not used'); },
        resolveApproval: async () => ({
          status: 'ok',
          approvalId: 'approval-1',
          resolution: 'approved',
          runStatus: 'completed',
          snapshot: realSnapshot()
        }),
        askDesktopQuestion: async (question, handlers) => {
          calls.push({ question, history: handlers?.history });
          return {
            question,
            answer: `回复：${question}`,
            provider: 'deterministic_test',
            model: 'deterministic_test'
          };
        }
      }
    },
    {
      chatSessionStorage: storage,
      now: () => new Date('2026-06-18T06:00:00.000Z')
    }
  );
  return { state, calls, storage };
}

describe('session history state', () => {
  test('starts with one persisted empty chat session', () => {
    const { state, storage } = appState();

    expect(get(state.activeChatSessionId)).toBe('chat_session_1');
    expect(get(state.chatMessages)).toEqual([]);
    expect(get(state.chatSessionSummaries)).toEqual([
      {
        id: 'chat_session_1',
        title: '新对话',
        updatedAt: '2026-06-18T06:00:00.000Z',
        messageCount: 0,
        active: true
      }
    ]);
    expect(storage.value('isotope.desktop.chatSessions.v1')).toContain('chat_session_1');
  });

  test('keeps independent history when switching sessions', async () => {
    const { state, calls } = appState();

    await state.askDesktopQuestion('第一句');
    const firstSessionId = get(state.activeChatSessionId);
    state.startNewChatSession();
    await state.askDesktopQuestion('第二句');
    state.selectChatSession(firstSessionId);
    await state.askDesktopQuestion('我的上句话是什么');

    expect(get(state.chatSessionSummaries).map((session) => session.title)).toEqual([
      '第一句',
      '第二句'
    ]);
    expect(get(state.chatMessages).map((message) => message.content)).toEqual([
      '第一句',
      '回复：第一句',
      '我的上句话是什么',
      '回复：我的上句话是什么'
    ]);
    expect(calls).toEqual([
      { question: '第一句', history: [] },
      { question: '第二句', history: [] },
      {
        question: '我的上句话是什么',
        history: [
          { role: 'user', content: '第一句' },
          { role: 'assistant', content: '回复：第一句' }
        ]
      }
    ]);
  });

  test('loads persisted sessions and active selection from storage', () => {
    const storage = memoryStorage({
      'isotope.desktop.chatSessions.v1': JSON.stringify({
        activeSessionId: 'chat_session_2',
        sessions: [
          {
            id: 'chat_session_1',
            title: '旧会话',
            createdAt: '2026-06-17T01:00:00.000Z',
            updatedAt: '2026-06-17T01:00:00.000Z',
            messages: [{ id: 'chat_user_1', role: 'user', content: '旧问题' }]
          },
          {
            id: 'chat_session_2',
            title: '当前会话',
            createdAt: '2026-06-18T01:00:00.000Z',
            updatedAt: '2026-06-18T01:00:00.000Z',
            messages: [{ id: 'chat_user_2', role: 'user', content: '当前问题' }]
          }
        ]
      })
    });
    const { state } = appState(storage);

    expect(get(state.activeChatSessionId)).toBe('chat_session_2');
    expect(get(state.chatMessages)).toEqual([{ id: 'chat_user_2', role: 'user', content: '当前问题' }]);
    expect(get(state.chatSessionSummaries)).toEqual([
      {
        id: 'chat_session_2',
        title: '当前会话',
        updatedAt: '2026-06-18T01:00:00.000Z',
        messageCount: 1,
        active: true
      },
      {
        id: 'chat_session_1',
        title: '旧会话',
        updatedAt: '2026-06-17T01:00:00.000Z',
        messageCount: 1,
        active: false
      }
    ]);
  });
});
