import { derived, get, writable } from 'svelte/store';
import type { Writable } from 'svelte/store';
import type {
  AgentClient,
  ApprovalResolution,
  DesktopCapacityCall,
  DesktopChatHistoryMessage,
  DesktopTerminalApprovalPolicy
} from '../client/agentClient';
import type { ActivityNode, DesktopReadResult, IsotopeSnapshot } from '../contracts/isotope';
import {
  defaultChatSessionStorage,
  loadChatSessionState,
  nextChatSessionCount,
  nextChatTurnCount,
  persistChatSessionState,
  summarizeChatSessions,
  titleForMessages,
  type ChatSessionStorage,
  type DesktopChatSession,
  type DesktopChatSessionSummary
} from './chatSessionHistory';

export type { ChatSessionStorage, DesktopChatSession, DesktopChatSessionSummary } from './chatSessionHistory';

const DEFAULT_TERMINAL_ALLOWED_COMMANDS = ['echo', 'printf', 'pwd', 'true', 'false', 'sleep'];

export type DesktopChatMessagePart =
  | { id: string; kind: 'text'; text: string }
  | { id: string; kind: 'capacity'; call: DesktopCapacityCall };

export type DesktopChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  provider?: string;
  model?: string;
  capacityCalls?: DesktopCapacityCall[];
  parts?: DesktopChatMessagePart[];
};

export type AppClients = {
  agentClient: AgentClient;
};

export type AppStateOptions = {
  chatSessionStorage?: ChatSessionStorage | null;
  now?: () => Date;
};

type ChatMessagesStore = Pick<Writable<DesktopChatMessage[]>, 'update'>;

export function createAppState(clients: AppClients, options: AppStateOptions = {}) {
  const now = options.now ?? (() => new Date());
  const chatSessionStorage =
    options.chatSessionStorage === undefined ? defaultChatSessionStorage() : options.chatSessionStorage;
  const initialChatState = loadChatSessionState(chatSessionStorage, now);
  const snapshot = writable<IsotopeSnapshot | null>(null);
  const selectedActivityId = writable<string | null>(null);
  const isLoading = writable(false);
  const chatSessions = writable<DesktopChatSession[]>(initialChatState.sessions);
  const activeChatSessionId = writable(initialChatState.activeSessionId);
  const chatMessages = derived(
    [chatSessions, activeChatSessionId],
    ([$chatSessions, $activeChatSessionId]): DesktopChatMessage[] =>
      $chatSessions.find((session) => session.id === $activeChatSessionId)?.messages ?? []
  );
  const chatSessionSummaries = derived(
    [chatSessions, activeChatSessionId],
    ([$chatSessions, $activeChatSessionId]): DesktopChatSessionSummary[] =>
      summarizeChatSessions($chatSessions, $activeChatSessionId)
  );
  const isAskingDesktop = writable(false);
  const chatError = writable<string | null>(null);
  const isResolvingApproval = writable<string | null>(null);
  const approvalError = writable<string | null>(null);
  const terminalYoloEnabled = writable(false);
  const terminalAllowedCommands = writable<string[]>([...DEFAULT_TERMINAL_ALLOWED_COMMANDS]);
  let chatTurnCount = nextChatTurnCount(initialChatState.sessions);
  let chatSessionCount = nextChatSessionCount(initialChatState.sessions);
  persistChatSessionState(chatSessionStorage, get(chatSessions), get(activeChatSessionId));

  function persistSessions() {
    persistChatSessionState(chatSessionStorage, get(chatSessions), get(activeChatSessionId));
  }

  function createEmptyChatSession(): DesktopChatSession {
    const timestamp = now().toISOString();
    chatSessionCount += 1;
    return {
      id: `chat_session_${chatSessionCount}`,
      title: '新对话',
      createdAt: timestamp,
      updatedAt: timestamp,
      messages: []
    };
  }

  function updateSessionMessages(
    sessionId: string,
    updater: (messages: DesktopChatMessage[]) => DesktopChatMessage[]
  ) {
    const updatedAt = now().toISOString();
    chatSessions.update((sessions) =>
      sessions.map((session) => {
        if (session.id !== sessionId) return session;
        const messages = updater(session.messages);
        return {
          ...session,
          title: titleForMessages(messages, session.title),
          updatedAt,
          messages
        };
      })
    );
    persistSessions();
  }

  function chatMessagesForSession(sessionId: string): ChatMessagesStore {
    return {
      update: (updater) => updateSessionMessages(sessionId, updater)
    };
  }

  function activeChatMessagesStore(): ChatMessagesStore {
    return chatMessagesForSession(get(activeChatSessionId));
  }

  function messagesForSession(sessionId: string): DesktopChatMessage[] {
    return get(chatSessions).find((session) => session.id === sessionId)?.messages ?? [];
  }

  const selectedActivity = derived(
    [snapshot, selectedActivityId],
    ([$snapshot, $selectedActivityId]): ActivityNode | null => {
      if (!$snapshot || !$selectedActivityId) return null;
      return $snapshot.activities.find((activity) => activity.id === $selectedActivityId) ?? null;
    }
  );

  async function resolveApproval(
    approvalId: string,
    resolution: ApprovalResolution,
    reason: string = defaultApprovalReason(resolution)
  ) {
    const cleanApprovalId = approvalId.trim();
    if (!cleanApprovalId) return;
    isResolvingApproval.set(cleanApprovalId);
    approvalError.set(null);
    try {
      const result = await clients.agentClient.resolveApproval(cleanApprovalId, resolution, reason);
      snapshot.set(result.snapshot);
      if (resolution === 'approved' && result.readResult) {
        appendApprovedReadResult(activeChatMessagesStore(), result.readResult);
      }
    } catch (error) {
      approvalError.set(error instanceof Error ? error.message : '审批操作失败');
    } finally {
      isResolvingApproval.set(null);
    }
  }

  async function allowlistTerminalApproval(approvalId: string, command: string) {
    const cleanCommand = command.trim();
    if (!cleanCommand) {
      await resolveApproval(approvalId, 'approved');
      return;
    }
    terminalAllowedCommands.update((commands) =>
      commands.includes(cleanCommand) ? commands : [...commands, cleanCommand]
    );
    await resolveApproval(
      approvalId,
      'approved',
      `desktop operator approved and allowlisted terminal command: ${cleanCommand}`
    );
  }

  function terminalApprovalPolicy(): DesktopTerminalApprovalPolicy {
    return {
      mode: get(terminalYoloEnabled) ? 'yolo' : 'allowlist',
      allowedCommands: get(terminalAllowedCommands)
    };
  }

  return {
    snapshot,
    selectedActivityId,
    selectedActivity,
    isLoading,
    chatMessages,
    chatSessionSummaries,
    activeChatSessionId,
    isAskingDesktop,
    chatError,
    isResolvingApproval,
    approvalError,
    terminalYoloEnabled,
    async initialize() {
      isLoading.set(true);
      try {
        const loadedSnapshot = await clients.agentClient.loadSnapshot();
        snapshot.set(loadedSnapshot);
        selectedActivityId.set(loadedSnapshot.activeActivity?.id ?? loadedSnapshot.activities[0]?.id ?? null);
      } finally {
        isLoading.set(false);
      }
    },
    selectActivity(activityId: string) {
      selectedActivityId.set(activityId);
    },
    selectChatSession(sessionId: string) {
      const cleanSessionId = sessionId.trim();
      if (!get(chatSessions).some((session) => session.id === cleanSessionId)) return;
      activeChatSessionId.set(cleanSessionId);
      chatError.set(null);
      persistSessions();
    },
    startNewChatSession() {
      const session = createEmptyChatSession();
      chatSessions.update((sessions) => [...sessions, session]);
      activeChatSessionId.set(session.id);
      chatError.set(null);
      persistSessions();
    },
    deleteChatSession(sessionId: string) {
      const cleanSessionId = sessionId.trim();
      if (!get(chatSessions).some((session) => session.id === cleanSessionId)) return;
      let nextActiveSessionId = get(activeChatSessionId);
      chatSessions.update((sessions) => {
        const remaining = sessions.filter((session) => session.id !== cleanSessionId);
        if (!remaining.length) {
          const replacement = createEmptyChatSession();
          nextActiveSessionId = replacement.id;
          return [replacement];
        }
        if (nextActiveSessionId === cleanSessionId) {
          nextActiveSessionId = summarizeChatSessions(remaining, '')[0].id;
        }
        return remaining;
      });
      activeChatSessionId.set(nextActiveSessionId);
      chatError.set(null);
      persistSessions();
    },
    resolveApproval,
    allowlistTerminalApproval,
    toggleTerminalYolo() {
      terminalYoloEnabled.update((enabled) => !enabled);
    },
    async askDesktopQuestion(question: string) {
      const cleanQuestion = question.trim();
      if (!cleanQuestion) return;
      const sessionId = get(activeChatSessionId);
      const sessionMessages = chatMessagesForSession(sessionId);
      const history = desktopChatHistory(messagesForSession(sessionId));
      chatTurnCount += 1;
      const userId = `chat_user_${chatTurnCount}`;
      const assistantId = `chat_assistant_${chatTurnCount}`;
      chatError.set(null);
      sessionMessages.update((messages) => [
        ...messages,
        { id: userId, role: 'user', content: cleanQuestion },
        { id: assistantId, role: 'assistant', content: '' }
      ]);
      isAskingDesktop.set(true);
      try {
        const answer = await clients.agentClient.askDesktopQuestion(cleanQuestion, {
          history,
          terminalApproval: terminalApprovalPolicy(),
          onCapacityStart: (call) => {
            updateAssistantCapacityPart(sessionMessages, assistantId, call);
          },
          onCapacityUpdate: (call) => {
            updateAssistantCapacityPart(sessionMessages, assistantId, call);
          },
          onCapacityResult: (call) => {
            updateAssistantCapacityPart(sessionMessages, assistantId, call);
          },
          onDelta: (text) => {
            appendAssistantTextPart(sessionMessages, assistantId, text);
          }
        });
        sessionMessages.update((messages) =>
          messages.map((message) =>
            message.id === assistantId
              ? finalizeAssistantMessage(message, answer)
              : message
          )
        );
        await refreshSnapshotAfterChat(clients.agentClient, snapshot, selectedActivityId);
      } catch (error) {
        const message = error instanceof Error ? error.message : '桌面对话失败';
        chatError.set(message);
        sessionMessages.update((messages) =>
          messages.map((item) =>
            item.id === assistantId
              ? { ...item, content: '后端暂时没有返回回答。' }
              : item
          )
        );
      } finally {
        isAskingDesktop.set(false);
      }
    }
  };
}

async function refreshSnapshotAfterChat(
  agentClient: AgentClient,
  snapshot: ReturnType<typeof writable<IsotopeSnapshot | null>>,
  selectedActivityId: ReturnType<typeof writable<string | null>>
) {
  try {
    const loadedSnapshot = await agentClient.loadSnapshot();
    snapshot.set(loadedSnapshot);
    const selected = get(selectedActivityId);
    if (selected && loadedSnapshot.activities.some((activity) => activity.id === selected)) {
      return;
    }
    selectedActivityId.set(loadedSnapshot.activeActivity?.id ?? loadedSnapshot.activities[0]?.id ?? null);
  } catch {
    // Chat already succeeded; keep the existing snapshot if the refresh fails.
  }
}

function defaultApprovalReason(resolution: ApprovalResolution): string {
  return resolution === 'approved' ? 'desktop operator approved' : 'desktop operator denied';
}

function desktopChatHistory(messages: DesktopChatMessage[]): DesktopChatHistoryMessage[] {
  return messages
    .map((message) => ({
      role: message.role,
      content: message.content.trim()
    }))
    .filter((message) => message.content.length > 0)
    .slice(-12);
}

function appendApprovedReadResult(
  chatMessages: ChatMessagesStore,
  readResult: DesktopReadResult
) {
  const excerpt = typeof readResult.excerpt === 'string' ? readResult.excerpt : '';
  const suffix = readResult.truncated ? '\n\n[内容已截断]' : '';
  const text =
    readResult.status === 'readable'
      ? `已读取本地文件：${readResult.path}\n\n${excerpt}${suffix}`
      : `本地文件读取未完成：${readResult.path} (${readResult.status})`;
  const suffixId = Date.now();
  chatMessages.update((messages) => [
    ...messages,
    {
      id: `chat_approval_read_${suffixId}`,
      role: 'assistant',
      content: text,
      parts: [{ id: `chat_approval_read_text_${suffixId}`, kind: 'text', text }]
    }
  ]);
}

function appendAssistantTextPart(
  chatMessages: ChatMessagesStore,
  assistantId: string,
  text: string
) {
  if (!text) return;
  chatMessages.update((messages) =>
    messages.map((message) => {
      if (message.id !== assistantId) return message;
      const parts = message.parts ?? [];
      const lastPart = parts.at(-1);
      const nextParts =
        lastPart?.kind === 'text'
          ? [...parts.slice(0, -1), { ...lastPart, text: lastPart.text + text }]
          : [
              ...parts,
              {
                id: `${assistantId}_text_${parts.filter((part) => part.kind === 'text').length + 1}`,
                kind: 'text' as const,
                text
              }
            ];
      return {
        ...message,
        content: message.content + text,
        parts: nextParts
      };
    })
  );
}

function updateAssistantCapacityPart(
  chatMessages: ChatMessagesStore,
  assistantId: string,
  call: DesktopCapacityCall
) {
  chatMessages.update((messages) =>
    messages.map((message) => {
      if (message.id !== assistantId) return message;
      const existing = message.capacityCalls ?? [];
      const nextCalls = existing.some((item) => item.id === call.id)
        ? existing.map((item) => (item.id === call.id ? { ...item, ...call } : item))
        : [...existing, call];
      return {
        ...message,
        capacityCalls: nextCalls,
        parts: updateCapacityPart(message.parts ?? [], assistantId, call)
      };
    })
  );
}

function updateCapacityPart(
  parts: DesktopChatMessagePart[],
  assistantId: string,
  call: DesktopCapacityCall
): DesktopChatMessagePart[] {
  const partId = `${assistantId}_capacity_${call.id}`;
  if (parts.some((part) => part.id === partId)) {
    return parts.map((part) =>
      part.id === partId && part.kind === 'capacity' ? { ...part, call } : part
    );
  }
  return [...parts, { id: partId, kind: 'capacity', call }];
}

function finalizeAssistantMessage(
  message: DesktopChatMessage,
  answer: { answer: string; provider?: string; model?: string; capacityCalls?: DesktopCapacityCall[] }
): DesktopChatMessage {
  const capacityCalls = answer.capacityCalls ?? message.capacityCalls;
  return {
    ...message,
    content: answer.answer || message.content,
    provider: answer.provider,
    model: answer.model,
    ...(capacityCalls?.length ? { capacityCalls } : {}),
    ...(message.parts?.length && capacityCalls?.length
      ? { parts: refreshCapacityParts(message.parts, capacityCalls) }
      : {})
  };
}

function refreshCapacityParts(
  parts: DesktopChatMessagePart[],
  capacityCalls: DesktopCapacityCall[]
): DesktopChatMessagePart[] {
  const callsById = new Map(capacityCalls.map((call) => [call.id, call]));
  return parts.map((part) => {
    if (part.kind !== 'capacity') return part;
    return callsById.has(part.call.id) ? { ...part, call: callsById.get(part.call.id)! } : part;
  });
}
