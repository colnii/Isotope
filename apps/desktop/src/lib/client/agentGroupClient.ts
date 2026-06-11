import type { AgentGroupDetail, CodexTranscriptPage } from '../contracts/agentGroup';

export type TranscriptRequest = {
  offset?: number;
  limit?: number;
  includeRaw?: boolean;
};

export type AgentGroupClient = {
  loadGroup(groupId: string): Promise<AgentGroupDetail>;
  stopCurrentRun(groupId: string): Promise<Record<string, unknown>>;
  stopMember(groupId: string, memberId: string): Promise<Record<string, unknown>>;
  loadTranscript(sessionId: string, request?: TranscriptRequest): Promise<CodexTranscriptPage>;
};

export function createAgentGroupClient(baseUrl: string | null): AgentGroupClient {
  const apiBaseUrl = normalizeBaseUrl(baseUrl);
  return {
    async loadGroup(groupId) {
      const base = requiredBase(apiBaseUrl);
      const response = await fetch(
        `${base}/desktop/agent-groups/${encodeURIComponent(groupId)}`,
        { cache: 'no-store' }
      );
      if (!response.ok) throw new Error(await responseErrorMessage(response));
      return (await response.json()) as AgentGroupDetail;
    },
    async stopCurrentRun(groupId) {
      return postControl(requiredBase(apiBaseUrl), groupId, {
        intent: 'terminate',
        target: 'current_run',
        target_member_id: null,
        reason: 'desktop current run stop'
      });
    },
    async stopMember(groupId, memberId) {
      return postControl(requiredBase(apiBaseUrl), groupId, {
        intent: 'terminate',
        target: 'member',
        target_member_id: memberId,
        reason: 'desktop member stop'
      });
    },
    async loadTranscript(sessionId, request = {}) {
      const base = requiredBase(apiBaseUrl);
      const offset = request.offset ?? 0;
      const limit = request.limit ?? 200;
      const includeRaw = request.includeRaw === true;
      const response = await fetch(
        `${base}/desktop/codex-sessions/${encodeURIComponent(
          sessionId
        )}/transcript?offset=${offset}&limit=${limit}&include_raw=${includeRaw}`,
        { cache: 'no-store' }
      );
      if (!response.ok) throw new Error(await responseErrorMessage(response));
      return (await response.json()) as CodexTranscriptPage;
    }
  };
}

async function postControl(
  base: string,
  groupId: string,
  payload: Record<string, unknown>
): Promise<Record<string, unknown>> {
  const response = await fetch(
    `${base}/desktop/agent-groups/${encodeURIComponent(groupId)}/control`,
    {
      method: 'POST',
      cache: 'no-store',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload)
    }
  );
  if (!response.ok) throw new Error(await responseErrorMessage(response));
  return (await response.json()) as Record<string, unknown>;
}

function normalizeBaseUrl(baseUrl: string | null): string | null {
  const trimmed = baseUrl?.trim();
  return trimmed ? trimmed.replace(/\/$/, '') : null;
}

function requiredBase(baseUrl: string | null): string {
  if (!baseUrl) throw new Error('Agent Group Chat 需要配置后端 URL');
  return baseUrl;
}

async function responseErrorMessage(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    const message = payload?.error?.message;
    if (typeof message === 'string' && message) return message;
  } catch {
    return `Agent Group Chat 请求失败：HTTP ${response.status}`;
  }
  return `Agent Group Chat 请求失败：HTTP ${response.status}`;
}
