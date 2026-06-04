<script lang="ts">
  import { browser } from '$app/environment';
  import { onMount } from 'svelte';
  import { createIsotopeClient } from '$lib/client/isotopeClient';
  import MainWindowShell from '$lib/components/main/MainWindowShell.svelte';
  import MiniWindow from '$lib/components/mini/MiniWindow.svelte';
  import { createAppState } from '$lib/stores/appState';
  import { windowClient } from '$lib/window/windowClient';
  import {
    buildPageSurfaceClass,
    resolveWindowSurface,
    type DesktopWindowSurface
  } from '$lib/window/windowSurface';

  const desktopApiBaseUrl = import.meta.env.VITE_ISOTOPE_DESKTOP_API_BASE as string | undefined;
  const isotopeClient = createIsotopeClient(desktopApiBaseUrl?.trim() || null);
  const appState = createAppState(isotopeClient);
  const {
    snapshot,
    selectedActivity,
    chatMessages,
    isAskingDesktop,
    chatError,
    isResolvingApproval,
    approvalError
  } = appState;

  let loadError = $state<string | null>(null);
  let surface = $state<DesktopWindowSurface>(browser ? resolveWindowSurface(window.location.search) : 'dev');

  onMount(() => {
    surface = resolveWindowSurface(window.location.search);
    appState.initialize().catch((error: unknown) => {
      loadError = error instanceof Error ? error.message : '加载桌面快照失败。';
    });
  });

  function openMainWindow() {
    void windowClient.open('main', { focus: true });
    void windowClient.hide('mini');
  }

  function closeMiniWindow() {
    void windowClient.hide('mini');
  }

</script>

<main class={buildPageSurfaceClass(surface)}>
  {#if surface === 'mini'}
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
        {loadError ? '迷你窗口快照不可用' : '正在加载迷你窗口'}
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
        resolvingApprovalId={$isResolvingApproval}
        approvalError={$approvalError}
        agentClient={isotopeClient.agentClient}
        onAskDesktop={(question) => void appState.askDesktopQuestion(question)}
        onResolveApproval={(approvalId, resolution) => void appState.resolveApproval(approvalId, resolution)}
      />
    {:else}
      <div class="border border-isotope-line bg-white p-5 text-sm text-isotope-muted">
        {loadError ? '主窗口快照不可用' : '正在加载主窗口'}
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
        resolvingApprovalId={$isResolvingApproval}
        approvalError={$approvalError}
        agentClient={isotopeClient.agentClient}
        onAskDesktop={(question) => void appState.askDesktopQuestion(question)}
        onResolveApproval={(approvalId, resolution) => void appState.resolveApproval(approvalId, resolution)}
      />
    {:else}
      <div class="border border-isotope-line bg-white p-5 text-sm text-isotope-muted">
        {loadError ? '对话不可用' : '正在加载 Isotope 对话'}
      </div>
    {/if}
  {/if}
</main>
