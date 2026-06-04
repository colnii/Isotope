import { describe, expect, test, vi } from 'vitest';
import type { IsotopeSnapshot } from '../contracts/isotope';
import { createAgentClient } from './agentClient';

const realSource = {
  kind: 'real' as const,
  label: 'supervisor_state_projection',
  backendRef: 'supervisor_state:/tmp/isotope'
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

  test('resolves desktop approval through configured backend', async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            status: 'ok',
            approvalId: 'approval-1',
            resolution: 'approved',
            runStatus: 'completed',
            snapshot: realSnapshot
          }),
          { status: 200 }
        )
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await createAgentClient('http://127.0.0.1:8765').resolveApproval(
      'approval-1',
      'approved',
      'operator approved from desktop'
    );

    expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8765/desktop/approvals/approval-1/resolve', {
      method: 'POST',
      cache: 'no-store',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        resolution: 'approved',
        reason: 'operator approved from desktop',
        resolver: 'desktop_frontend'
      })
    });
    expect(result.status).toBe('ok');
    expect(result.snapshot.counts.approvals).toBe(1);
  });

  test('loads original screen screenshot artifact content from configured backend', async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            status: 'ok',
            artifact: {
              artifactType: 'screen_screenshot',
              summary: 'screen screenshot captured',
              ref: {
                ref_type: 'artifact',
                scope: 'run',
                run_id: 'run_screen_001',
                artifact_id: 'artifact_screen_001'
              }
            },
            image: {
              mediaType: 'image/png',
              width: 1920,
              height: 1080,
              data: 'ZmFrZS1mdWxsLXBuZw==',
              dataUrl: 'data:image/png;base64,ZmFrZS1mdWxsLXBuZw=='
            },
            file: {
              path: '/tmp/state/runs/run_screen_001/artifacts/artifact_screen_001.json',
              directory: '/tmp/state/runs/run_screen_001/artifacts',
              downloadFilename: 'artifact_screen_001.png'
            }
          }),
          { status: 200 }
        )
    );
    vi.stubGlobal('fetch', fetchMock);

    const artifact = await createAgentClient('http://127.0.0.1:8765').loadScreenArtifactContent(
      'artifact_screen_001'
    );

    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8765/desktop/artifacts/artifact_screen_001/screen-content',
      { cache: 'no-store' }
    );
    expect(artifact.image.dataUrl).toBe('data:image/png;base64,ZmFrZS1mdWxsLXBuZw==');
    expect(artifact.file.directory).toBe('/tmp/state/runs/run_screen_001/artifacts');
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

    const answer = await createAgentClient('http://127.0.0.1:8765').askDesktopQuestion(
      'loop?',
      {
        history: [
          { role: 'user', content: '上一句' },
          { role: 'assistant', content: '上一句回复' }
        ],
        onDelta: (text) => deltas.push(text),
        onCapacityStart: (call) => capacityEvents.push(`start:${call.capacityId}`),
        onCapacityResult: (call) => capacityEvents.push(`result:${call.status}`)
      }
    );

    expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8765/desktop/chat', {
      method: 'POST',
      cache: 'no-store',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        question: 'loop?',
        history: [
          { role: 'user', content: '上一句' },
          { role: 'assistant', content: '上一句回复' }
        ]
      })
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

  test('marks running capacity calls as error when the stream reports an error', async () => {
    const stream = new ReadableStream({
      start(controller) {
        const encoder = new TextEncoder();
        controller.enqueue(encoder.encode('event: start\ndata: {"status":"ok"}\n\n'));
        controller.enqueue(
          encoder.encode(
            'event: capacity_start\ndata: {"id":"capacity_research_search","capacity_id":"research.search","title":"Research Search","status":"running","input_summary":{"query":"capacity"},"result_summary":{},"details":[{"label":"Inputs","kind":"json","content":{"query":"capacity"}}]}\n\n'
          )
        );
        controller.enqueue(
          encoder.encode(
            'event: error\ndata: {"status":"error","message":"capability inputs not allowed by input_contract: cwd, state_root"}\n\n'
          )
        );
        controller.close();
      }
    });
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(stream, {
            status: 200,
            headers: { 'content-type': 'text/event-stream; charset=utf-8' }
          })
      )
    );
    const capacityEvents: string[] = [];

    await expect(
      createAgentClient('http://127.0.0.1:8765').askDesktopQuestion('search?', {
        onCapacityResult: (call) => capacityEvents.push(`${call.capacityId}:${call.status}`)
      })
    ).rejects.toThrow('capability inputs not allowed by input_contract: cwd, state_root');

    expect(capacityEvents).toEqual(['research.search:error']);
  });

  test('desktop chat requires a real backend base URL', async () => {
    await expect(createAgentClient(null).askDesktopQuestion('loop?')).rejects.toThrow(
      '桌面对话需要配置后端 URL'
    );
  });

  test('desktop chat rejects an empty question with Chinese copy', async () => {
    await expect(createAgentClient('http://127.0.0.1:8765').askDesktopQuestion('   ')).rejects.toThrow(
      '问题不能为空'
    );
  });
});
