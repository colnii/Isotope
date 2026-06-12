import { describe, expect, it, vi } from 'vitest';
import { createAgentWorkspaceClient } from './agentWorkspaceClient';

describe('agentWorkspaceClient', () => {
  it('loads workspaces and workspace detail', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ status: 'ok', workspaces: [] }))
      .mockResolvedValueOnce(
        jsonResponse({
          status: 'ok',
          workspace: workspaceSummary(),
          channels: [],
          direct_messages: [],
          members: [],
          messages: [],
          controls: []
        })
      );
    vi.stubGlobal('fetch', fetchMock);

    const client = createAgentWorkspaceClient('http://localhost:8765');
    await client.listWorkspaces();
    const detail = await client.loadWorkspace('workspace_rna');

    expect(fetchMock.mock.calls[0][0]).toBe('http://localhost:8765/desktop/agent-workspaces');
    expect(fetchMock.mock.calls[1][0]).toBe(
      'http://localhost:8765/desktop/agent-workspaces/workspace_rna'
    );
    expect(detail.workspace.workspace_id).toBe('workspace_rna');
  });

  it('updates workspace title and root path', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        status: 'ok',
        workspace: {
          ...workspaceSummary(),
          title: 'RNA 工作区',
          root_path: '/home/lumber/Github/AI_Camp_RNA_2026'
        },
        channels: [],
        direct_messages: [],
        members: [],
        messages: [],
        controls: []
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    const client = createAgentWorkspaceClient('http://localhost:8765');
    await client.updateWorkspace('workspace_rna', {
      title: 'RNA 工作区',
      root_path: '/home/lumber/Github/AI_Camp_RNA_2026'
    });

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8765/desktop/agent-workspaces/workspace_rna',
      {
        method: 'POST',
        cache: 'no-store',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          title: 'RNA 工作区',
          root_path: '/home/lumber/Github/AI_Camp_RNA_2026'
        })
      }
    );
  });

  it('loads recent codex sessions by cwd or all scope', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: 'ok', sessions: [] }));
    vi.stubGlobal('fetch', fetchMock);

    const client = createAgentWorkspaceClient('http://localhost:8765');
    await client.listCodexSessions('workspace_rna', 'all');

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8765/desktop/agent-workspaces/workspace_rna/codex-sessions?scope=all',
      { cache: 'no-store' }
    );
  });

  it('creates channels and manages codex members', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ status: 'ok', channel: { channel_id: 'channel_1' } }))
      .mockResolvedValueOnce(jsonResponse({ status: 'ok', member: { member_id: 'member_1' } }))
      .mockResolvedValueOnce(jsonResponse({ status: 'ok', member: { send_policy: 'draft_only' } }))
      .mockResolvedValueOnce(jsonResponse({ status: 'ok', member: { status: 'archived' } }));
    vi.stubGlobal('fetch', fetchMock);

    const client = createAgentWorkspaceClient('http://localhost:8765');
    await client.createChannel('workspace_rna', { name: 'rna-research', topic: 'Research' });
    await client.addMember('workspace_rna', 'channel_1', {
      display_name: 'Research Codex',
      role: 'Explore RNA strategy',
      goal: 'Find directions',
      send_policy: 'confirm',
      resume_session_id: 'session_1',
      source_path: '/tmp/session.jsonl',
      managed_record_id: null
    });
    await client.updateMember('workspace_rna', 'channel_1', 'member_1', {
      send_policy: 'draft_only'
    });
    await client.removeMember('workspace_rna', 'channel_1', 'member_1');

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      name: 'rna-research',
      topic: 'Research'
    });
    expect(JSON.parse(fetchMock.mock.calls[1][1].body).resume_session_id).toBe('session_1');
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({
      action: 'update',
      send_policy: 'draft_only'
    });
    expect(JSON.parse(fetchMock.mock.calls[3][1].body)).toEqual({ action: 'remove' });
  });

  it('sends channel messages and stop controls', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ status: 'ok', message: { message_id: 'msg_1' } }))
      .mockResolvedValueOnce(jsonResponse({ status: 'ok', control: { control_id: 'ctrl_1' } }))
      .mockResolvedValueOnce(jsonResponse({ status: 'ok', control: { control_id: 'ctrl_2' } }));
    vi.stubGlobal('fetch', fetchMock);

    const client = createAgentWorkspaceClient('http://localhost:8765');
    await client.sendConversation('workspace_rna', 'channel_1', 'sync lanes', 'interrupt');
    await client.stopCurrentRun('workspace_rna', 'channel_1');
    await client.stopMember('workspace_rna', 'channel_1', 'member_1');

    expect(fetchMock.mock.calls[0][0]).toBe(
      'http://localhost:8765/desktop/agent-workspaces/workspace_rna/conversations/channel_1/chat'
    );
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
      intent: 'terminate',
      target: 'current_run',
      target_member_id: null,
      reason: 'desktop current run stop'
    });
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({
      intent: 'terminate',
      target: 'member',
      target_member_id: 'member_1',
      reason: 'desktop member stop'
    });
  });

  it('loads high-limit codex transcript pages for workspace members', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        status: 'ok',
        session_id: 'session_1',
        offset: 0,
        limit: 1000,
        next_offset: 1000,
        has_more: false,
        total_events: 1,
        events: []
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    const client = createAgentWorkspaceClient('http://localhost:8765');
    await client.loadTranscript('session_1', { limit: 1000, includeRaw: true, latest: true });

    expect(fetchMock.mock.calls[0][0]).toBe(
      'http://localhost:8765/desktop/codex-sessions/session_1/transcript?offset=0&limit=1000&include_raw=true&latest=true'
    );
  });
});

function workspaceSummary() {
  return {
    workspace_id: 'workspace_rna',
    title: 'AI_Camp_RNA_2026',
    root_path: '/home/lumber/Github/AI_Camp_RNA_2026',
    status: 'active',
    created_at: '2026-06-12T00:00:00Z',
    updated_at: '2026-06-12T00:00:00Z'
  };
}

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'content-type': 'application/json' }
  });
}
