import type { DesktopChatMessage } from './appState';

export type DesktopChatSession = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: DesktopChatMessage[];
};

export type DesktopChatSessionSummary = {
  id: string;
  title: string;
  updatedAt: string;
  messageCount: number;
  active: boolean;
};

export type ChatSessionStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

const CHAT_SESSION_STORAGE_KEY = 'isotope.desktop.chatSessions.v1';

export function defaultChatSessionStorage(): ChatSessionStorage | null {
  if (import.meta.env.MODE === 'test') return null;
  try {
    return typeof globalThis.localStorage === 'undefined' ? null : globalThis.localStorage;
  } catch {
    return null;
  }
}

export function loadChatSessionState(
  storage: ChatSessionStorage | null,
  now: () => Date
): { sessions: DesktopChatSession[]; activeSessionId: string } {
  const fallback = () => {
    const timestamp = now().toISOString();
    const session = {
      id: 'chat_session_1',
      title: '新对话',
      createdAt: timestamp,
      updatedAt: timestamp,
      messages: []
    };
    return { sessions: [session], activeSessionId: session.id };
  };
  if (!storage) return fallback();
  try {
    const raw = storage.getItem(CHAT_SESSION_STORAGE_KEY);
    if (!raw) return fallback();
    const payload = JSON.parse(raw) as { activeSessionId?: unknown; sessions?: unknown };
    const sessions = Array.isArray(payload.sessions)
      ? payload.sessions.map(normalizeStoredSession).filter((session): session is DesktopChatSession => !!session)
      : [];
    if (!sessions.length) return fallback();
    const activeSessionId =
      typeof payload.activeSessionId === 'string' &&
      sessions.some((session) => session.id === payload.activeSessionId)
        ? payload.activeSessionId
        : sessions[0].id;
    return { sessions, activeSessionId };
  } catch {
    return fallback();
  }
}

export function persistChatSessionState(
  storage: ChatSessionStorage | null,
  sessions: DesktopChatSession[],
  activeSessionId: string
) {
  if (!storage) return;
  try {
    storage.setItem(
      CHAT_SESSION_STORAGE_KEY,
      JSON.stringify({
        activeSessionId,
        sessions
      })
    );
  } catch {
    // Local persistence is a convenience; chat should remain usable if storage is unavailable.
  }
}

export function summarizeChatSessions(
  sessions: DesktopChatSession[],
  activeSessionId: string
): DesktopChatSessionSummary[] {
  return [...sessions]
    .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))
    .map((session) => ({
      id: session.id,
      title: session.title,
      updatedAt: session.updatedAt,
      messageCount: session.messages.length,
      active: session.id === activeSessionId
    }));
}

export function titleForMessages(messages: DesktopChatMessage[], fallback: string): string {
  const firstUserMessage = messages.find((message) => message.role === 'user')?.content.trim();
  if (!firstUserMessage) return fallback || '新对话';
  return firstUserMessage.length > 28 ? `${firstUserMessage.slice(0, 28)}...` : firstUserMessage;
}

export function nextChatTurnCount(sessions: DesktopChatSession[]): number {
  let max = 0;
  for (const session of sessions) {
    for (const message of session.messages) {
      const match = /^chat_(?:user|assistant)_(\d+)$/.exec(message.id);
      if (match) max = Math.max(max, Number(match[1]));
    }
  }
  return max;
}

export function nextChatSessionCount(sessions: DesktopChatSession[]): number {
  let max = 0;
  for (const session of sessions) {
    const match = /^chat_session_(\d+)$/.exec(session.id);
    if (match) max = Math.max(max, Number(match[1]));
  }
  return max || 1;
}

function normalizeStoredSession(value: unknown): DesktopChatSession | null {
  if (!value || typeof value !== 'object') return null;
  const raw = value as Record<string, unknown>;
  if (
    typeof raw.id !== 'string' ||
    typeof raw.createdAt !== 'string' ||
    typeof raw.updatedAt !== 'string' ||
    !Array.isArray(raw.messages)
  ) {
    return null;
  }
  const messages = raw.messages
    .map(normalizeStoredMessage)
    .filter((message): message is DesktopChatMessage => !!message);
  return {
    id: raw.id,
    title: typeof raw.title === 'string' && raw.title.trim() ? raw.title.trim() : titleForMessages(messages, '新对话'),
    createdAt: raw.createdAt,
    updatedAt: raw.updatedAt,
    messages
  };
}

function normalizeStoredMessage(value: unknown): DesktopChatMessage | null {
  if (!value || typeof value !== 'object') return null;
  const raw = value as Record<string, unknown>;
  if (
    typeof raw.id !== 'string' ||
    (raw.role !== 'user' && raw.role !== 'assistant') ||
    typeof raw.content !== 'string'
  ) {
    return null;
  }
  return {
    ...(raw as DesktopChatMessage),
    id: raw.id,
    role: raw.role,
    content: raw.content
  };
}
