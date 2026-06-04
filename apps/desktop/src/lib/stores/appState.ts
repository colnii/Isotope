import { derived, get, writable } from 'svelte/store';
import type {
  AgentClient,
  ApprovalResolution,
  DesktopCapacityCall,
  DesktopChatHistoryMessage
} from '../client/agentClient';
import type { ActivityNode, IsotopeSnapshot } from '../contracts/isotope';

export type DesktopChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  provider?: string;
  model?: string;
  capacityCalls?: DesktopCapacityCall[];
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
  let chatTurnCount = 0;
  const selectedActivity = derived(
    [snapshot, selectedActivityId],
    ([$snapshot, $selectedActivityId]): ActivityNode | null => {
      if (!$snapshot || !$selectedActivityId) return null;
      return $snapshot.activities.find((activity) => activity.id === $selectedActivityId) ?? null;
    }
  );

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
    async resolveApproval(approvalId: string, resolution: ApprovalResolution) {
      const cleanApprovalId = approvalId.trim();
      if (!cleanApprovalId) return;
      isResolvingApproval.set(cleanApprovalId);
      approvalError.set(null);
      try {
        const result = await clients.agentClient.resolveApproval(
          cleanApprovalId,
          resolution,
          defaultApprovalReason(resolution)
        );
        snapshot.set(result.snapshot);
      } catch (error) {
        approvalError.set(error instanceof Error ? error.message : '审批操作失败');
      } finally {
        isResolvingApproval.set(null);
      }
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
          onCapacityStart: (call) => {
            updateAssistantCapacityCall(chatMessages, assistantId, call);
          },
          onCapacityUpdate: (call) => {
            updateAssistantCapacityCall(chatMessages, assistantId, call);
          },
          onCapacityResult: (call) => {
            updateAssistantCapacityCall(chatMessages, assistantId, call);
          },
          onDelta: (text) => {
            chatMessages.update((messages) =>
              messages.map((message) =>
                message.id === assistantId
                  ? { ...message, content: message.content + text }
                  : message
              )
            );
          }
        });
        chatMessages.update((messages) =>
          messages.map((message) =>
            message.id === assistantId
              ? {
                  ...message,
                  content: answer.answer || message.content,
                  provider: answer.provider,
                  model: answer.model,
                  ...(answer.capacityCalls?.length
                    ? { capacityCalls: answer.capacityCalls }
                    : {})
                }
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

function updateAssistantCapacityCall(
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
      return { ...message, capacityCalls: nextCalls };
    })
  );
}
