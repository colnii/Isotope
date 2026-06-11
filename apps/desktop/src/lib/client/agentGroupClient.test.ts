import { describe, expect, it, vi } from 'vitest';
import { createAgentGroupClient } from './agentGroupClient';

describe('agentGroupClient', () => {
  it('loads agent group detail', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        status: 'ok',
        group: {
          group_id: 'group_rna',
          title: 'RNA group',
          goal: 'Coordinate RNA work',
          status: 'active'
        },
        connected_members: [],
        private_chat: [],
        messages: [],
        turns: []
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    const client = createAgentGroupClient('http://localhost:8765');
    const payload = await client.loadGroup('group_rna');

    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8765/desktop/agent-groups/group_rna', {
      cache: 'no-store'
    });
    expect(payload.group.group_id).toBe('group_rna');
  });

  it('requests member stop through control endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: 'terminated' }));
    vi.stubGlobal('fetch', fetchMock);

    const client = createAgentGroupClient('http://localhost:8765');
    await client.stopMember('group_rna', 'member_research');

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      intent: 'terminate',
      target: 'member',
      target_member_id: 'member_research',
      reason: 'desktop member stop'
    });
  });

  it('loads transcript with offset limit and raw flag', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        status: 'ok',
        session_id: 'session_1',
        offset: 20,
        limit: 50,
        has_more: false,
        next_offset: 21,
        events: []
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    const client = createAgentGroupClient('http://localhost:8765');
    await client.loadTranscript('session_1', {
      offset: 20,
      limit: 50,
      includeRaw: true
    });

    expect(fetchMock.mock.calls[0][0]).toBe(
      'http://localhost:8765/desktop/codex-sessions/session_1/transcript?offset=20&limit=50&include_raw=true'
    );
  });
});

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'content-type': 'application/json' }
  });
}
