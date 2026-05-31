<script lang="ts">
  import type { ActivityNode, IsotopeEvent, IsotopeSnapshot } from '../../contracts/isotope';
  import type { DesktopChatMessage } from '../../stores/appState';
  import { buildMainWindowProductView } from '../../view/mainWindowProductView';
  import ActivityRail from './ActivityRail.svelte';
  import ConversationWorkspace from './ConversationWorkspace.svelte';
  import InspectorDock from './InspectorDock.svelte';

  let {
    snapshot,
    selectedActivity,
    selectedActivityId = null,
    chatMessages = [],
    chatError = null,
    isAskingDesktop = false,
    events = [],
    onSelectActivity,
    onAskDesktop
  } = $props<{
    snapshot: IsotopeSnapshot;
    selectedActivity: ActivityNode | null;
    selectedActivityId?: string | null;
    chatMessages?: DesktopChatMessage[];
    chatError?: string | null;
    isAskingDesktop?: boolean;
    events?: IsotopeEvent[];
    onSelectActivity: (activityId: string) => void;
    onAskDesktop: (question: string) => void;
  }>();

  const view = $derived(buildMainWindowProductView(snapshot, selectedActivity));
</script>

<section
  class="grid min-h-screen bg-isotope-bg text-isotope-text lg:grid-cols-[220px_minmax(0,1fr)_320px]"
  aria-label="Isotope MainWindow product shell"
>
  <ActivityRail activities={snapshot.activities} selectedId={selectedActivityId} onSelect={onSelectActivity} />
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
  <InspectorDock title={view.inspectorTitle} summary={view.inspectorSummary} source={snapshot.source} {events} />
</section>
