import { derived, get, writable } from 'svelte/store';
import type {
  AgentClient,
  ApprovalResolution,
  DesktopCapacityCall,
  DesktopChatHistoryMessage,
  DesktopTerminalApprovalPolicy
} from '../client/agentClient';
import type { ActivityNode, DesktopReadResult, IsotopeSnapshot } from '../contracts/isotope';

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

export function createAppState(clients: AppClients) {
  const snapshot = writable<IsotopeSnapshot | null>(null);
  const selectedActivityId = writable<string | null>(null);
  const isLoading = writable(false);
  const chatMessages = writable<DesktopChatMessage[]>([]);
  const isAskingDesktop = writable(false);
  const chatError = writable<string | null>(null);
  const isResolvingApproval = writable<string | null>(null);
  const approvalError = writable<string | null>(null);
  const terminalYoloEnabled = writable(false);
  const terminalAllowedCommands = writable<string[]>([...DEFAULT_TERMINAL_ALLOWED_COMMANDS]);
  let chatTurnCount = 0;
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
        appendApprovedReadResult(chatMessages, result.readResult);
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
    resolveApproval,
    allowlistTerminalApproval,
    toggleTerminalYolo() {
      terminalYoloEnabled.update((enabled) => !enabled);
    },
    async askDesktopQuestion(question: string) {
      const cleanQuestion = question.trim();
      if (!cleanQuestion) return;
      const history = desktopChatHistory(get(chatMessages));
      chatTurnCount += 1;
      const userId = `chat_user_${chatTurnCount}`;
      const assistantId = `chat_assistant_${chatTurnCount}`;
      chatError.set(null);
      chatMessages.update((messages) => [
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
            updateAssistantCapacityPart(chatMessages, assistantId, call);
          },
          onCapacityUpdate: (call) => {
            updateAssistantCapacityPart(chatMessages, assistantId, call);
          },
          onCapacityResult: (call) => {
            updateAssistantCapacityPart(chatMessages, assistantId, call);
          },
          onDelta: (text) => {
            appendAssistantTextPart(chatMessages, assistantId, text);
          }
        });
        chatMessages.update((messages) =>
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
        chatMessages.update((messages) =>
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
  chatMessages: ReturnType<typeof writable<DesktopChatMessage[]>>,
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
  chatMessages: ReturnType<typeof writable<DesktopChatMessage[]>>,
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
  chatMessages: ReturnType<typeof writable<DesktopChatMessage[]>>,
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
