import type { IsotopeSnapshot } from '../contracts/isotope';
import { mockSnapshot } from './mockData';

export type ApprovalResolution = 'approved' | 'denied';

export type DesktopApprovalResolutionResult = {
  status: 'ok';
  approvalId: string;
  resolution: ApprovalResolution;
  runStatus?: string;
  snapshot: IsotopeSnapshot;
};

export type DesktopChatAnswer = {
  question: string;
  answer: string;
  provider?: string;
  model?: string;
  capacityCalls?: DesktopCapacityCall[];
};

export type DesktopCapacityDetailSection = {
  label: string;
  kind: 'json' | 'text';
  content: unknown;
};

export type DesktopCapacityCall = {
  id: string;
  capacityId: string;
  title: string;
  status: 'running' | 'ok' | 'blocked' | 'error' | 'unknown';
  inputSummary: Record<string, unknown>;
  resultSummary: Record<string, unknown>;
  details: DesktopCapacityDetailSection[];
};

export type DesktopScreenArtifactContent = {
  status: 'ok';
  artifact: {
    artifactType: 'screen_screenshot';
    summary: string;
    ref: {
      ref_type: 'artifact';
      scope: 'run';
      run_id: string;
      artifact_id: string;
    };
  };
  image: {
    mediaType: string;
    width?: number;
    height?: number;
    data: string;
    dataUrl: string;
  };
  file: {
    path: string;
    directory: string;
    downloadFilename: string;
  };
};

export type DesktopChatHistoryMessage = {
  role: 'user' | 'assistant';
  content: string;
};

export type DesktopChatHandlers = {
  history?: DesktopChatHistoryMessage[];
  onDelta?: (text: string) => void;
  onCapacityStart?: (call: DesktopCapacityCall) => void;
  onCapacityUpdate?: (call: DesktopCapacityCall) => void;
  onCapacityResult?: (call: DesktopCapacityCall) => void;
};

export type AgentClient = {
  loadSnapshot(): Promise<IsotopeSnapshot>;
  loadScreenArtifactContent(artifactId: string): Promise<DesktopScreenArtifactContent>;
  resolveApproval(
    approvalId: string,
    resolution: ApprovalResolution,
    reason?: string
  ): Promise<DesktopApprovalResolutionResult>;
  askDesktopQuestion(question: string, handlers?: DesktopChatHandlers): Promise<DesktopChatAnswer>;
};

export function createAgentClient(baseUrl: string | null = null): AgentClient {
  const apiBaseUrl = normalizeBaseUrl(baseUrl);

  return {
    async loadSnapshot() {
      if (!apiBaseUrl) return mockSnapshot;

      try {
        const response = await fetch(`${apiBaseUrl}/desktop/snapshot`, { cache: 'no-store' });
        if (!response.ok) return mockSnapshot;
        return (await response.json()) as IsotopeSnapshot;
      } catch {
        return mockSnapshot;
      }
    },
    async loadScreenArtifactContent(artifactId) {
      if (!apiBaseUrl) {
        throw new Error('截图原图需要配置后端 URL');
      }
      const cleanArtifactId = artifactId.trim();
      if (!cleanArtifactId) {
        throw new Error('artifact ID 不能为空');
      }
      const response = await fetch(
        `${apiBaseUrl}/desktop/artifacts/${encodeURIComponent(cleanArtifactId)}/screen-content`,
        { cache: 'no-store' }
      );
      if (!response.ok) {
        throw new Error(await responseErrorMessage(response));
      }
      return (await response.json()) as DesktopScreenArtifactContent;
    },
    async resolveApproval(approvalId, resolution, reason) {
      if (!apiBaseUrl) {
        throw new Error('审批操作需要配置后端 URL');
      }
      const cleanApprovalId = approvalId.trim();
      if (!cleanApprovalId) {
        throw new Error('审批 ID 不能为空');
      }
      const response = await fetch(
        `${apiBaseUrl}/desktop/approvals/${encodeURIComponent(cleanApprovalId)}/resolve`,
        {
          method: 'POST',
          cache: 'no-store',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({
            resolution,
            reason: reason?.trim() || defaultApprovalReason(resolution),
            resolver: 'desktop_frontend'
          })
        }
      );
      if (!response.ok) {
        throw new Error(await responseErrorMessage(response));
      }
      return (await response.json()) as DesktopApprovalResolutionResult;
    },
    async askDesktopQuestion(question, handlers = {}) {
      if (!apiBaseUrl) {
        throw new Error('桌面对话需要配置后端 URL');
      }
      const cleanQuestion = question.trim();
      if (!cleanQuestion) {
        throw new Error('问题不能为空');
      }
      const response = await fetch(`${apiBaseUrl}/desktop/chat`, {
        method: 'POST',
        cache: 'no-store',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          question: cleanQuestion,
          history: normalizeChatHistory(handlers.history)
        })
      });
      if (!response.ok) {
        throw new Error(await responseErrorMessage(response));
      }
      if (!response.body) {
        throw new Error('桌面对话响应缺少数据流');
      }
      return readDesktopChatStream(response.body, cleanQuestion, handlers);
    }
  };
}

function defaultApprovalReason(resolution: ApprovalResolution): string {
  return resolution === 'approved' ? 'desktop operator approved' : 'desktop operator denied';
}

function normalizeChatHistory(history: DesktopChatHistoryMessage[] = []): DesktopChatHistoryMessage[] {
  return history
    .map((message) => ({
      role: message.role,
      content: message.content.trim()
    }))
    .filter((message) => (message.role === 'user' || message.role === 'assistant') && message.content.length > 0)
    .slice(-12);
}

function normalizeBaseUrl(baseUrl: string | null): string | null {
  const trimmed = baseUrl?.trim();
  if (!trimmed) return null;
  return trimmed.replace(/\/$/, '');
}

async function readDesktopChatStream(
  body: ReadableStream<Uint8Array>,
  question: string,
  handlers: DesktopChatHandlers
): Promise<DesktopChatAnswer> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let answer = '';
  let provider: string | undefined;
  let model: string | undefined;
  const capacityCalls = new Map<string, DesktopCapacityCall>();
  const result = (): DesktopChatAnswer => {
    const calls = [...capacityCalls.values()];
    return { question, answer, provider, model, ...(calls.length ? { capacityCalls: calls } : {}) };
  };
  const handleEvent = (event: { name: string; data: Record<string, unknown> }): boolean => {
    if (event.name === 'delta') {
      const text = typeof event.data.text === 'string' ? event.data.text : '';
      if (text) {
        answer += text;
        handlers.onDelta?.(text);
      }
    } else if (event.name === 'capacity_start') {
      const call = normalizeCapacityCall(event.data);
      capacityCalls.set(call.id, call);
      handlers.onCapacityStart?.(call);
    } else if (event.name === 'capacity_update') {
      const call = mergeCapacityCall(capacityCalls.get(capacityCallId(event.data)), event.data);
      capacityCalls.set(call.id, call);
      handlers.onCapacityUpdate?.(call);
    } else if (event.name === 'capacity_result') {
      const call = mergeCapacityCall(capacityCalls.get(capacityCallId(event.data)), event.data);
      capacityCalls.set(call.id, call);
      handlers.onCapacityResult?.(call);
    } else if (event.name === 'done') {
      provider = typeof event.data.provider === 'string' ? event.data.provider : undefined;
      model = typeof event.data.model === 'string' ? event.data.model : undefined;
      return true;
    } else if (event.name === 'error') {
      markRunningCapacityCallsError(capacityCalls, event.data, handlers);
      throw new Error(typeof event.data.message === 'string' ? event.data.message : '桌面对话失败');
    }
    return false;
  };

  while (true) {
    const { value, done } = await reader.read();
    if (value) {
      buffer += decoder.decode(value, { stream: !done });
      const blocks = buffer.split(/\r?\n\r?\n/);
      buffer = blocks.pop() ?? '';
      for (const [index, block] of blocks.entries()) {
        const event = parseDesktopChatEvent(block);
        if (handleEvent(event)) {
          await reader.cancel().catch(() => undefined);
          return result();
        }
        if (index < blocks.length - 1) {
          await yieldToBrowserEventLoop();
        }
      }
    }
    if (done) break;
  }

  if (buffer.trim()) {
    const event = parseDesktopChatEvent(buffer);
    if (handleEvent(event)) {
      await reader.cancel().catch(() => undefined);
      return result();
    }
  }

  return result();
}

function yieldToBrowserEventLoop(): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, 0);
  });
}

function markRunningCapacityCallsError(
  capacityCalls: Map<string, DesktopCapacityCall>,
  payload: Record<string, unknown>,
  handlers: DesktopChatHandlers
): void {
  const message = typeof payload.message === 'string' && payload.message ? payload.message : '桌面对话失败';
  for (const [id, call] of capacityCalls.entries()) {
    if (call.status !== 'running') continue;
    const updated: DesktopCapacityCall = {
      ...call,
      status: 'error',
      resultSummary: {
        ...call.resultSummary,
        error_message: message
      },
      details: [
        ...call.details,
        {
          label: 'Error',
          kind: 'text',
          content: message
        }
      ]
    };
    capacityCalls.set(id, updated);
    handlers.onCapacityResult?.(updated);
  }
}

function parseDesktopChatEvent(block: string): { name: string; data: Record<string, unknown> } {
  const lines = block.split(/\r?\n/);
  const eventLine = lines.find((line) => line.startsWith('event: '));
  const dataLines = lines
    .filter((line) => line.startsWith('data: '))
    .map((line) => line.slice('data: '.length));
  const name = eventLine?.slice('event: '.length).trim() || 'message';
  const data = dataLines.length ? JSON.parse(dataLines.join('\n')) : {};
  return { name, data };
}

async function responseErrorMessage(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    const message = payload?.error?.message;
    if (typeof message === 'string' && message) return message;
  } catch {
    // Fall through to stable status text.
  }
  return `桌面对话请求失败：HTTP ${response.status}`;
}

function normalizeCapacityCall(payload: Record<string, unknown>): DesktopCapacityCall {
  const capacityId = stringField(payload, 'capacity_id', 'unknown');
  return {
    id: capacityCallId(payload),
    capacityId,
    title: stringField(payload, 'title', capacityId),
    status: capacityStatus(payload.status),
    inputSummary: recordField(payload.input_summary),
    resultSummary: recordField(payload.result_summary),
    details: detailSections(payload.details)
  };
}

function mergeCapacityCall(
  existing: DesktopCapacityCall | undefined,
  payload: Record<string, unknown>
): DesktopCapacityCall {
  const next = normalizeCapacityCall(payload);
  if (!existing) return next;
  return {
    ...existing,
    ...next,
    inputSummary: Object.keys(next.inputSummary).length ? next.inputSummary : existing.inputSummary,
    resultSummary: Object.keys(next.resultSummary).length ? next.resultSummary : existing.resultSummary,
    details: next.details.length ? next.details : existing.details
  };
}

function capacityCallId(payload: Record<string, unknown>): string {
  const id = payload.id;
  if (typeof id === 'string' && id.trim()) return id;
  const capacityId = stringField(payload, 'capacity_id', 'unknown');
  return `capacity_${capacityId.replace(/[^a-z0-9]+/gi, '_').replace(/^_+|_+$/g, '') || 'unknown'}`;
}

function stringField(payload: Record<string, unknown>, key: string, fallback: string): string {
  const value = payload[key];
  return typeof value === 'string' && value.trim() ? value : fallback;
}

function recordField(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function capacityStatus(value: unknown): DesktopCapacityCall['status'] {
  return value === 'running' || value === 'ok' || value === 'blocked' || value === 'error'
    ? value
    : 'unknown';
}

function detailSections(value: unknown): DesktopCapacityDetailSection[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return [];
    const section = item as Record<string, unknown>;
    const label = stringField(section, 'label', '详情');
    const kind = section.kind === 'text' ? 'text' : 'json';
    return [{ label, kind, content: section.content }];
  });
}
