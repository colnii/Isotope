<script lang="ts">
  import type { ActivityNode, IsotopeSnapshot } from '../../contracts/isotope';
  import type { DesktopChatMessage } from '../../stores/appState';
  import { buildMainWindowProductView } from '../../view/mainWindowProductView';
  import ConversationWorkspace from './ConversationWorkspace.svelte';

  let {
    snapshot,
    selectedActivity,
    chatMessages = [],
    chatError = null,
    isAskingDesktop = false,
    onAskDesktop
  } = $props<{
    snapshot: IsotopeSnapshot;
    selectedActivity: ActivityNode | null;
    chatMessages?: DesktopChatMessage[];
    chatError?: string | null;
    isAskingDesktop?: boolean;
    onAskDesktop: (question: string) => void;
  }>();

  const view = $derived(buildMainWindowProductView(snapshot, selectedActivity));
</script>

<section
  class="min-h-screen bg-white text-isotope-text"
  aria-label="Isotope AI chat"
>
  <ConversationWorkspace
    eyebrow={view.chatEyebrow}
    title={view.workspaceTitle}
    subtitle={view.workspaceSubtitle}
    body={view.workspaceBody}
    emptyTitle={view.emptyChatTitle}
    emptyBody={view.emptyChatBody}
    composerPlaceholder={view.composerPlaceholder}
    {chatMessages}
    {chatError}
    isAsking={isAskingDesktop}
    onAsk={onAskDesktop}
  />
</section>
