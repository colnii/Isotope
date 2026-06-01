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

  test('streams desktop chat answer from the configured backend', async () => {
    const stream = new ReadableStream({
      start(controller) {
        const encoder = new TextEncoder();
        controller.enqueue(encoder.encode('event: start\ndata: {"status":"ok"}\n\n'));
        controller.enqueue(
          encoder.encode(
            'event: capacity_start\ndata: {"id":"capacity_memory_query","capacity_id":"memory.query","title":"Memory Query","status":"running","input_summary":{"query":"capacity"},"result_summary":{},"details":[{"label":"Inputs","kind":"json","content":{"query":"capacity"}}]}\n\n'
          )
        );
        controller.enqueue(
          encoder.encode(
            'event: capacity_result\ndata: {"id":"capacity_memory_query","capacity_id":"memory.query","title":"Memory Query","status":"ok","input_summary":{"query":"capacity"},"result_summary":{"result_count":2},"details":[{"label":"Results","kind":"json","content":{"result_count":2}}]}\n\n'
          )
        );
        controller.enqueue(encoder.encode('event: delta\ndata: {"text":"Loop"}\n\n'));
        controller.enqueue(encoder.encode('event: delta\ndata: {"text":" 正常"}\n\n'));
        controller.enqueue(
          encoder.encode('event: done\ndata: {"status":"ok","provider":"fake","model":"fake"}\n\n')
        );
        controller.close();
      }
    });
    const fetchMock = vi.fn(
      async () =>
        new Response(stream, {
          status: 200,
          headers: { 'content-type': 'text/event-stream; charset=utf-8' }
        })
    );
    vi.stubGlobal('fetch', fetchMock);
    const deltas: string[] = [];
    const capacityEvents: string[] = [];

    const answer = await createAgentClient('http://127.0.0.1:8765').askDesktopQuestion('loop?', {
      onDelta: (text) => deltas.push(text),
      onCapacityStart: (call) => capacityEvents.push(`start:${call.capacityId}`),
      onCapacityResult: (call) => capacityEvents.push(`result:${call.status}`)
    });

    expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8765/desktop/chat', {
      method: 'POST',
      cache: 'no-store',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ question: 'loop?' })
    });
    expect(deltas).toEqual(['Loop', ' 正常']);
    expect(capacityEvents).toEqual(['start:memory.query', 'result:ok']);
    expect(answer).toEqual({
      question: 'loop?',
      answer: 'Loop 正常',
      provider: 'fake',
      model: 'fake',
      capacityCalls: [
        {
          id: 'capacity_memory_query',
          capacityId: 'memory.query',
          title: 'Memory Query',
          status: 'ok',
          inputSummary: { query: 'capacity' },
          resultSummary: { result_count: 2 },
          details: [
            {
              label: 'Results',
              kind: 'json',
              content: { result_count: 2 }
            }
          ]
        }
      ]
    });
  });

  test('desktop chat requires a real backend base URL', async () => {
    await expect(createAgentClient(null).askDesktopQuestion('loop?')).rejects.toThrow(
      'Desktop chat requires a configured backend URL'
    );
  });
});
