<script lang="ts">
  import { browser } from '$app/environment';
  import { onMount } from 'svelte';
  import { createIsotopeClient } from '$lib/client/isotopeClient';
  import MainWindowShell from '$lib/components/main/MainWindowShell.svelte';
  import FloatingOrb from '$lib/components/orb/FloatingOrb.svelte';
  import MiniWindow from '$lib/components/mini/MiniWindow.svelte';
  import { createAppState } from '$lib/stores/appState';
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
    chatMessages,
    isAskingDesktop,
    chatError
  } = appState;

  let loadError = $state<string | null>(null);
  let miniOpen = $state(false);
  let surface = $state<DesktopWindowSurface>(browser ? resolveWindowSurface(window.location.search) : 'dev');

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

</script>

<main class={buildPageSurfaceClass(surface)}>
  {#if surface === 'orb'}
    {#if $snapshot}
      <FloatingOrb surface="window" onOpenMini={openMiniWindow} />
    {:else}
      <div class="grid min-h-[96px] place-items-center text-xs text-isotope-muted">
        {loadError ? 'Orb snapshot unavailable' : 'Loading orb'}
      </div>
    {/if}
  {:else if surface === 'mini'}
    {#if $snapshot}
      <MiniWindow
        snapshot={$snapshot}
        surface="window"
        chatMessages={$chatMessages}
        chatError={$chatError}
        isAsking={$isAskingDesktop}
        onAsk={(question) => void appState.askDesktopQuestion(question)}
        onOpenMain={openMainWindow}
        onClose={closeMiniWindow}
      />
    {:else}
      <div class="border border-isotope-line bg-white p-3 text-sm text-isotope-muted">
        {loadError ? 'MiniWindow snapshot unavailable' : 'Loading MiniWindow'}
      </div>
    {/if}
  {:else if surface === 'main'}
    {#if $snapshot}
      <MainWindowShell
        snapshot={$snapshot}
        selectedActivity={$selectedActivity}
        chatMessages={$chatMessages}
        chatError={$chatError}
        isAskingDesktop={$isAskingDesktop}
        onAskDesktop={(question) => void appState.askDesktopQuestion(question)}
      />
    {:else}
      <div class="border border-isotope-line bg-white p-5 text-sm text-isotope-muted">
        {loadError ? 'MainWindow snapshot unavailable' : 'Loading MainWindow'}
      </div>
    {/if}
  {:else}
    {#if $snapshot}
      <MainWindowShell
        snapshot={$snapshot}
        selectedActivity={$selectedActivity}
        chatMessages={$chatMessages}
        chatError={$chatError}
        isAskingDesktop={$isAskingDesktop}
        onAskDesktop={(question) => void appState.askDesktopQuestion(question)}
      />
      {#if miniOpen}
        <MiniWindow
          snapshot={$snapshot}
          chatMessages={$chatMessages}
          chatError={$chatError}
          isAsking={$isAskingDesktop}
          onAsk={(question) => void appState.askDesktopQuestion(question)}
          onOpenMain={openMainWindow}
          onClose={closeMiniWindow}
        />
      {/if}
    {:else}
      <div class="border border-isotope-line bg-white p-5 text-sm text-isotope-muted">
        {loadError ? 'Chat unavailable' : 'Loading Isotope chat'}
      </div>
    {/if}
  {/if}
</main>
