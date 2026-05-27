<script lang="ts">
  import type { ActivityNode, IsotopeEvent, IsotopeSnapshot } from '../../contracts/isotope';
  import { buildMainWindowProductView } from '../../view/mainWindowProductView';
  import ActivityRail from './ActivityRail.svelte';
  import ConversationWorkspace from './ConversationWorkspace.svelte';
  import InspectorDock from './InspectorDock.svelte';

  let {
    snapshot,
    selectedActivity,
    selectedActivityId = null,
    events = [],
    onSelectActivity
  } = $props<{
    snapshot: IsotopeSnapshot;
    selectedActivity: ActivityNode | null;
    selectedActivityId?: string | null;
    events?: IsotopeEvent[];
    onSelectActivity: (activityId: string) => void;
  }>();

  const view = $derived(buildMainWindowProductView(snapshot, selectedActivity));
</script>

<section
  class="grid min-h-screen bg-isotope-bg text-isotope-text lg:grid-cols-[220px_minmax(0,1fr)_320px]"
  aria-label="Isotope MainWindow product shell"
>
  <ActivityRail activities={snapshot.activities} selectedId={selectedActivityId} onSelect={onSelectActivity} />
  <ConversationWorkspace title={view.workspaceTitle} subtitle={view.workspaceSubtitle} body={view.workspaceBody} />
  <InspectorDock title={view.inspectorTitle} summary={view.inspectorSummary} source={snapshot.source} {events} />
</section>
