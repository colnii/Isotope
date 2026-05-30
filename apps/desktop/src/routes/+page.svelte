<script lang="ts">
  import { browser } from '$app/environment';
  import { onMount } from 'svelte';
  import { createIsotopeClient } from '$lib/client/isotopeClient';
  import { replayMockEvents } from '$lib/client/replayMockEvents';
  import DevDiagnosticShell from '$lib/components/dev/DevDiagnosticShell.svelte';
  import MainWindowShell from '$lib/components/main/MainWindowShell.svelte';
  import FloatingOrb from '$lib/components/orb/FloatingOrb.svelte';
  import MiniWindow from '$lib/components/mini/MiniWindow.svelte';
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
  const {
    snapshot,
    selectedActivity,
    selectedActivityId,
    isLoading,
    chatMessages,
    isAskingDesktop,
    chatError
  } = appState;

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
      <MainWindowShell
        snapshot={$snapshot}
        events={replayMockEvents}
        selectedActivity={$selectedActivity}
        selectedActivityId={$selectedActivityId}
        chatMessages={$chatMessages}
        chatError={$chatError}
        isAskingDesktop={$isAskingDesktop}
        onSelectActivity={(activityId) => appState.selectActivity(activityId)}
        onAskDesktop={(question) => void appState.askDesktopQuestion(question)}
      />
    {:else}
      <div class="border border-isotope-line bg-white p-5 text-sm text-isotope-muted">
        {loadError ? 'MainWindow snapshot unavailable' : 'Loading MainWindow'}
      </div>
    {/if}
  {:else}
    <DevDiagnosticShell
      snapshot={$snapshot}
      selectedActivity={$selectedActivity}
      selectedActivityId={$selectedActivityId}
      isLoading={$isLoading}
      {loadError}
      {view}
      {mainOpen}
      events={replayMockEvents}
      onSelectActivity={(activityId) => appState.selectActivity(activityId)}
      onOpenMain={openMainWindow}
      onCloseMain={closeMainWindow}
    />
  {/if}
</main>
