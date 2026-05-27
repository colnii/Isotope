<script lang="ts">
  import { browser } from '$app/environment';
  import { onMount } from 'svelte';
  import { createIsotopeClient } from '$lib/client/isotopeClient';
  import { replayMockEvents } from '$lib/client/replayMockEvents';
  import FloatingOrb from '$lib/components/orb/FloatingOrb.svelte';
  import MainWindowSnapshotShell from '$lib/components/main/MainWindowSnapshotShell.svelte';
  import MiniWindow from '$lib/components/mini/MiniWindow.svelte';
  import SourceBadge from '$lib/components/common/SourceBadge.svelte';
  import { createAppState } from '$lib/stores/appState';
  import { buildSnapshotView } from '$lib/view/snapshotView';
  import { windowClient } from '$lib/window/windowClient';
  import {
    buildPageSurfaceClass,
    resolveWindowSurface,
    type DesktopWindowSurface
  } from '$lib/window/windowSurface';

  const desktopApiBaseUrl = import.meta.env.VITE_ISOTOPE_DESKTOP_API_BASE as string | undefined;
  const appState = createAppState(createIsotopeClient(desktopApiBaseUrl?.trim() || null));
  const { snapshot, selectedActivity, selectedActivityId, isLoading } = appState;

  let loadError = $state<string | null>(null);
  let miniOpen = $state(false);
  let mainOpen = $state(false);
  let surface = $state<DesktopWindowSurface>(browser ? resolveWindowSurface(window.location.search) : 'dev');
  const view = $derived($snapshot ? buildSnapshotView($snapshot, $selectedActivity) : null);

  onMount(() => {
    surface = resolveWindowSurface(window.location.search);
    appState.initialize().catch((error: unknown) => {
      loadError = error instanceof Error ? error.message : 'Failed to load desktop snapshot.';
    });
  });

  function openMiniWindow() {
    if (surface === 'dev') {
      miniOpen = true;
      return;
    }

    void windowClient.open('mini', { focus: true });
  }

  function openMainWindow() {
    if (surface === 'dev') {
      mainOpen = true;
      miniOpen = false;
      return;
    }

    void windowClient.open('main', { focus: true });
    void windowClient.hide('mini');
  }

  function closeMiniWindow() {
    if (surface === 'dev') {
      miniOpen = false;
      return;
    }

    void windowClient.hide('mini');
  }

  function closeMainWindow() {
    if (surface === 'dev') {
      mainOpen = false;
      return;
    }

    void windowClient.hide('main');
  }
</script>

<main class={buildPageSurfaceClass(surface)}>
  {#if surface === 'orb'}
    {#if $snapshot}
      <FloatingOrb snapshot={$snapshot} surface="window" onOpenMini={openMiniWindow} />
    {:else}
      <div class="grid min-h-[96px] place-items-center text-xs text-isotope-muted">
        {loadError ? 'Orb snapshot unavailable' : 'Loading orb'}
      </div>
    {/if}
  {:else if surface === 'mini'}
    {#if $snapshot}
      <MiniWindow snapshot={$snapshot} surface="window" onOpenMain={openMainWindow} onClose={closeMiniWindow} />
    {:else}
      <div class="border border-isotope-line bg-white p-3 text-sm text-isotope-muted">
        {loadError ? 'MiniWindow snapshot unavailable' : 'Loading MiniWindow'}
      </div>
    {/if}
  {:else if surface === 'main'}
    {#if $snapshot}
      <MainWindowSnapshotShell
        snapshot={$snapshot}
        events={replayMockEvents}
        selectedActivity={$selectedActivity}
        selectedActivityId={$selectedActivityId}
        onSelectActivity={(activityId) => appState.selectActivity(activityId)}
        onClose={closeMainWindow}
      />
    {:else}
      <div class="border border-isotope-line bg-white p-5 text-sm text-isotope-muted">
        {loadError ? 'MainWindow snapshot unavailable' : 'Loading MainWindow'}
      </div>
    {/if}
  {:else}
    <div class="mx-auto grid max-w-6xl gap-4 lg:grid-cols-[260px_minmax(0,1fr)_260px]">
      <aside class="border border-isotope-line bg-white/90 p-4">
        <div class="flex items-center justify-between gap-3">
          <h2 class="text-sm font-semibold">Activity</h2>
          {#if $snapshot}
            <SourceBadge source={$snapshot.source} />
          {/if}
        </div>
        <div class="mt-3 space-y-2">
          {#if $snapshot}
            {#each $snapshot.activities as activity (activity.id)}
              <button
                class="block w-full border border-isotope-line px-3 py-2 text-left text-sm hover:bg-isotope-panel"
                class:bg-isotope-panel={$selectedActivity?.id === activity.id}
                type="button"
                onclick={() => appState.selectActivity(activity.id)}
              >
                <span class="block font-medium">{activity.title}</span>
                <span class="block text-xs text-isotope-muted">{activity.kind} · {activity.status}</span>
              </button>
            {/each}
          {:else if $isLoading}
            <p class="text-sm text-isotope-muted">Loading snapshot...</p>
          {:else}
            <p class="text-sm text-isotope-muted">No snapshot loaded.</p>
          {/if}
        </div>
      </aside>

      <section class="border border-isotope-line bg-white/95 p-5">
        {#if view}
          <div class="text-xs uppercase text-isotope-muted">Current agent</div>
          <h1 class="mt-1 text-xl font-semibold">{view.agentTitle}</h1>
          <p class="mt-3 text-sm text-isotope-muted">Active goal</p>
          <p class="mt-1 text-base">{view.activeGoalTitle}</p>
          <div class="mt-5 border-t border-isotope-line pt-4">
            <div class="text-xs uppercase text-isotope-muted">Selected activity</div>
            <h2 class="mt-1 text-lg font-semibold">{view.selectedActivityTitle}</h2>
            {#if $selectedActivity?.summary}
              <p class="mt-2 text-sm text-isotope-muted">{$selectedActivity.summary}</p>
            {/if}
          </div>
        {:else if loadError}
          <h1 class="text-xl font-semibold">Snapshot unavailable</h1>
          <p class="mt-2 text-sm text-isotope-muted">{loadError}</p>
        {:else}
          <h1 class="text-xl font-semibold">Isotope Desktop</h1>
          <p class="mt-2 text-sm text-isotope-muted">Waiting for desktop snapshot.</p>
        {/if}
      </section>

      <aside class="border border-isotope-line bg-white/90 p-4">
        <h2 class="text-sm font-semibold">Status</h2>
        {#if view && $snapshot}
          <dl class="mt-3 grid grid-cols-2 gap-2 text-sm">
            <div class="border border-isotope-line p-2">
              <dt class="text-xs text-isotope-muted">Activities</dt>
              <dd class="mt-1 font-semibold">{view.activityCount}</dd>
            </div>
            <div class="border border-isotope-line p-2">
              <dt class="text-xs text-isotope-muted">Approvals</dt>
              <dd class="mt-1 font-semibold">{view.approvalCount}</dd>
            </div>
            <div class="border border-isotope-line p-2">
              <dt class="text-xs text-isotope-muted">Attention</dt>
              <dd class="mt-1 font-semibold">{view.needsAttention}</dd>
            </div>
            <div class="border border-isotope-line p-2">
              <dt class="text-xs text-isotope-muted">Errors</dt>
              <dd class="mt-1 font-semibold">{$snapshot.counts.errors}</dd>
            </div>
          </dl>
          <div class="mt-4">
            <h3 class="text-xs font-semibold uppercase text-isotope-muted">Approval summary</h3>
            {#if $snapshot.approvals.length > 0}
              <ul class="mt-2 space-y-2">
                {#each $snapshot.approvals as approval (approval.id)}
                  <li class="border border-isotope-line p-2 text-sm">
                    <span class="block font-medium">{approval.title}</span>
                    <span class="text-xs text-isotope-muted">{approval.status}</span>
                  </li>
                {/each}
              </ul>
            {:else}
              <p class="mt-2 text-sm text-isotope-muted">No approval items.</p>
            {/if}
          </div>
        {:else}
          <p class="mt-3 text-sm text-isotope-muted">No status yet.</p>
        {/if}
      </aside>
    </div>

    {#if $snapshot}
      <FloatingOrb snapshot={$snapshot} onOpenMini={openMiniWindow} />
      {#if miniOpen}
        <MiniWindow snapshot={$snapshot} surface="dev" onOpenMain={openMainWindow} onClose={closeMiniWindow} />
      {/if}
      {#if mainOpen}
        <MainWindowSnapshotShell
          snapshot={$snapshot}
          events={replayMockEvents}
          selectedActivity={$selectedActivity}
          selectedActivityId={$selectedActivityId}
          onSelectActivity={(activityId) => appState.selectActivity(activityId)}
          onClose={closeMainWindow}
        />
      {/if}
    {/if}
  {/if}
</main>
