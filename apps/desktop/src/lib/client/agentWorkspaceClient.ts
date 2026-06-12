import type {
  CodexTranscriptPage,
} from '../contracts/agentGroup';
import type {
  AddWorkspaceMemberRequest,
  AgentWorkspaceChannel,
  AgentWorkspaceDetail,
  AgentWorkspaceListPayload,
  AgentWorkspaceMember,
  CodexSessionCandidatePayload,
  CreateWorkspaceChannelRequest,
  UpdateWorkspaceMemberRequest,
  UpdateWorkspaceRequest,
  WorkspaceConversationMessage,
  WorkspaceRuntimeControlRecord
} from '../contracts/agentWorkspace';

export type TranscriptRequest = {
  offset?: number;
  limit?: number;
  includeRaw?: boolean;
  latest?: boolean;
};

export type AgentWorkspaceClient = {
  listWorkspaces(): Promise<AgentWorkspaceListPayload>;
  loadWorkspace(workspaceId: string): Promise<AgentWorkspaceDetail>;
  watchWorkspace(
    workspaceId: string,
    handlers: AgentWorkspaceEventHandlers
  ): () => void;
  listCodexSessions(
    workspaceId: string,
    scope?: 'cwd' | 'all'
  ): Promise<CodexSessionCandidatePayload>;
  updateWorkspace(
    workspaceId: string,
    request: UpdateWorkspaceRequest
  ): Promise<AgentWorkspaceDetail>;
  createChannel(
    workspaceId: string,
    request: CreateWorkspaceChannelRequest
  ): Promise<{ status: 'ok'; channel: AgentWorkspaceChannel }>;
  addMember(
    workspaceId: string,
    channelId: string,
    request: AddWorkspaceMemberRequest
  ): Promise<{ status: 'ok'; member: AgentWorkspaceMember }>;
  updateMember(
    workspaceId: string,
    channelId: string,
    memberId: string,
    request: UpdateWorkspaceMemberRequest
  ): Promise<{ status: 'ok'; member: AgentWorkspaceMember }>;
  removeMember(
    workspaceId: string,
    channelId: string,
    memberId: string
  ): Promise<{ status: 'ok'; member: AgentWorkspaceMember }>;
  sendConversation(
    workspaceId: string,
    conversationId: string,
    message: string,
    mode: 'queue' | 'interrupt'
  ): Promise<{ status: 'ok'; message: WorkspaceConversationMessage }>;
  stopCurrentRun(
    workspaceId: string,
    conversationId: string
  ): Promise<{ status: 'ok'; control: WorkspaceRuntimeControlRecord }>;
  stopMember(
    workspaceId: string,
    conversationId: string,
    memberId: string
  ): Promise<{ status: 'ok'; control: WorkspaceRuntimeControlRecord }>;
  loadTranscript(sessionId: string, request?: TranscriptRequest): Promise<CodexTranscriptPage>;
};

export type AgentWorkspaceEventHandlers = {
  onUpdate?: (payload: AgentWorkspaceDetail) => void;
  onError?: (error: Error) => void;
};

export function createAgentWorkspaceClient(baseUrl: string | null): AgentWorkspaceClient {
  const apiBaseUrl = normalizeBaseUrl(baseUrl);
  return {
    async listWorkspaces() {
      const response = await fetch(`${requiredBase(apiBaseUrl)}/desktop/agent-workspaces`, {
        cache: 'no-store'
      });
      if (!response.ok) throw new Error(await responseErrorMessage(response));
      return (await response.json()) as AgentWorkspaceListPayload;
    },
    async loadWorkspace(workspaceId) {
      const response = await fetch(
        `${requiredBase(apiBaseUrl)}/desktop/agent-workspaces/${encodeURIComponent(workspaceId)}`,
        { cache: 'no-store' }
      );
      if (!response.ok) throw new Error(await responseErrorMessage(response));
      return (await response.json()) as AgentWorkspaceDetail;
    },
    watchWorkspace(workspaceId, handlers) {
      const base = requiredBase(apiBaseUrl);
      if (typeof EventSource === 'undefined') {
        throw new Error('当前浏览器不支持智能体工作区实时更新');
      }
      const source = new EventSource(
        `${base}/desktop/agent-workspaces/${encodeURIComponent(workspaceId)}/events`
      );
      source.addEventListener('workspace_update', (event) => {
        try {
          handlers.onUpdate?.(JSON.parse((event as MessageEvent).data) as AgentWorkspaceDetail);
        } catch (error) {
          handlers.onError?.(errorMessage(error, '智能体工作区实时更新解析失败'));
        }
      });
      return () => source.close();
    },
    async listCodexSessions(workspaceId, scope = 'cwd') {
      const response = await fetch(
        `${requiredBase(apiBaseUrl)}/desktop/agent-workspaces/${encodeURIComponent(
          workspaceId
        )}/codex-sessions?scope=${encodeURIComponent(scope)}`,
        { cache: 'no-store' }
      );
      if (!response.ok) throw new Error(await responseErrorMessage(response));
      return (await response.json()) as CodexSessionCandidatePayload;
    },
    async updateWorkspace(workspaceId, request) {
      return postJson(
        requiredBase(apiBaseUrl),
        `/desktop/agent-workspaces/${encodeURIComponent(workspaceId)}`,
        request
      ) as Promise<AgentWorkspaceDetail>;
    },
    async createChannel(workspaceId, request) {
      return postJson(
        requiredBase(apiBaseUrl),
        `/desktop/agent-workspaces/${encodeURIComponent(workspaceId)}/channels`,
        {
          name: request.name,
          topic: request.topic ?? ''
        }
      ) as Promise<{ status: 'ok'; channel: AgentWorkspaceChannel }>;
    },
    async addMember(workspaceId, channelId, request) {
      return postJson(
        requiredBase(apiBaseUrl),
        `/desktop/agent-workspaces/${encodeURIComponent(workspaceId)}/channels/${encodeURIComponent(
          channelId
        )}/members`,
        request
      ) as Promise<{ status: 'ok'; member: AgentWorkspaceMember }>;
    },
    async updateMember(workspaceId, channelId, memberId, request) {
      return postJson(
        requiredBase(apiBaseUrl),
        `/desktop/agent-workspaces/${encodeURIComponent(workspaceId)}/channels/${encodeURIComponent(
          channelId
        )}/members/${encodeURIComponent(memberId)}`,
        { action: 'update', ...request }
      ) as Promise<{ status: 'ok'; member: AgentWorkspaceMember }>;
    },
    async removeMember(workspaceId, channelId, memberId) {
      return postJson(
        requiredBase(apiBaseUrl),
        `/desktop/agent-workspaces/${encodeURIComponent(workspaceId)}/channels/${encodeURIComponent(
          channelId
        )}/members/${encodeURIComponent(memberId)}`,
        { action: 'remove' }
      ) as Promise<{ status: 'ok'; member: AgentWorkspaceMember }>;
    },
    async sendConversation(workspaceId, conversationId, message, mode) {
      return postJson(
        requiredBase(apiBaseUrl),
        `/desktop/agent-workspaces/${encodeURIComponent(
          workspaceId
        )}/conversations/${encodeURIComponent(conversationId)}/chat`,
        { message, mode }
      ) as Promise<{ status: 'ok'; message: WorkspaceConversationMessage }>;
    },
    async stopCurrentRun(workspaceId, conversationId) {
      return postControl(requiredBase(apiBaseUrl), workspaceId, conversationId, {
        intent: 'terminate',
        target: 'current_run',
        target_member_id: null,
        reason: 'desktop current run stop'
      });
    },
    async stopMember(workspaceId, conversationId, memberId) {
      return postControl(requiredBase(apiBaseUrl), workspaceId, conversationId, {
        intent: 'terminate',
        target: 'member',
        target_member_id: memberId,
        reason: 'desktop member stop'
      });
    },
    async loadTranscript(sessionId, request = {}) {
      const base = requiredBase(apiBaseUrl);
      const offset = request.offset ?? 0;
      const limit = request.limit ?? 1000;
      const includeRaw = request.includeRaw === true;
      const latest = request.latest === true;
      const response = await fetch(
        `${base}/desktop/codex-sessions/${encodeURIComponent(
          sessionId
        )}/transcript?offset=${offset}&limit=${limit}&include_raw=${includeRaw}&latest=${latest}`,
        { cache: 'no-store' }
      );
      if (!response.ok) throw new Error(await responseErrorMessage(response));
      return (await response.json()) as CodexTranscriptPage;
    }
  };
}

async function postControl(
  base: string,
  workspaceId: string,
  conversationId: string,
  payload: Record<string, unknown>
): Promise<{ status: 'ok'; control: WorkspaceRuntimeControlRecord }> {
  return postJson(
    base,
    `/desktop/agent-workspaces/${encodeURIComponent(workspaceId)}/conversations/${encodeURIComponent(
      conversationId
    )}/control`,
    payload
  ) as Promise<{ status: 'ok'; control: WorkspaceRuntimeControlRecord }>;
}

async function postJson(
  base: string,
  path: string,
  payload: Record<string, unknown>
): Promise<Record<string, unknown>> {
  const response = await fetch(`${base}${path}`, {
    method: 'POST',
    cache: 'no-store',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!response.ok) throw new Error(await responseErrorMessage(response));
  return (await response.json()) as Record<string, unknown>;
}

function normalizeBaseUrl(baseUrl: string | null): string | null {
  const trimmed = baseUrl?.trim();
  return trimmed ? trimmed.replace(/\/$/, '') : null;
}

function requiredBase(baseUrl: string | null): string {
  if (!baseUrl) throw new Error('智能体工作区需要配置后端 URL');
  return baseUrl;
}

async function responseErrorMessage(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    const message = payload?.error?.message;
    if (typeof message === 'string' && message) return message;
  } catch {
    return `智能体工作区请求失败：HTTP ${response.status}`;
  }
  return `智能体工作区请求失败：HTTP ${response.status}`;
}

function errorMessage(error: unknown, fallback: string): Error {
  return error instanceof Error ? error : new Error(fallback);
}
