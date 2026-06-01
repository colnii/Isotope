import { derived, get, writable } from 'svelte/store';
import type { AgentClient, DesktopCapacityCall, DesktopChatHistoryMessage } from '../client/agentClient';
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
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Desktop chat failed';
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
