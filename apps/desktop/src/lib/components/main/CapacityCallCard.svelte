<script lang="ts">
  import type {
    AgentClient,
    DesktopCapacityCall,
    DesktopScreenArtifactContent
  } from '../../client/agentClient';
  import {
    capacityCallStatusLabel,
    capacityCallSummary,
    screenArtifactsForCapacityCall
  } from '../../view/capacityCallView';
  import { windowClient } from '../../window/windowClient';
  import CapacityCallDetails from './CapacityCallDetails.svelte';

  let { call, agentClient } = $props<{
    call: DesktopCapacityCall;
    agentClient: AgentClient;
  }>();

  let expanded = $state(false);
  let fullscreen = $state(false);
  let imageFullscreen = $state(false);
  let loadingArtifactId = $state<string | null>(null);
  let screenArtifactError = $state<string | null>(null);
  let selectedScreenArtifact = $state<DesktopScreenArtifactContent | null>(null);

  const statusLabel = $derived(capacityCallStatusLabel(call));
  const summary = $derived(capacityCallSummary(call));
  const screenArtifacts = $derived(screenArtifactsForCapacityCall(call));
  const statusClass = $derived(
    call.status === 'ok'
      ? 'border-isotope-done text-isotope-done'
      : call.status === 'running'
        ? 'border-isotope-running text-isotope-running'
        : call.status === 'error'
          ? 'border-isotope-attention text-isotope-attention'
          : 'border-isotope-line text-isotope-muted'
  );

  function closeFullscreen() {
    fullscreen = false;
  }

  function closeImageFullscreen() {
    imageFullscreen = false;
  }

  function toggleExpanded() {
    expanded = !expanded;
  }

  function openFullscreen() {
    fullscreen = true;
  }

  async function loadScreenArtifact(artifactId: string): Promise<DesktopScreenArtifactContent> {
    if (selectedScreenArtifact?.artifact.ref.artifact_id === artifactId) {
      return selectedScreenArtifact;
    }
    loadingArtifactId = artifactId;
    screenArtifactError = null;
    try {
      const artifact = await agentClient.loadScreenArtifactContent(artifactId);
      selectedScreenArtifact = artifact;
      return artifact;
    } catch (error) {
      screenArtifactError = error instanceof Error ? error.message : '截图原图读取失败';
      throw error;
    } finally {
      loadingArtifactId = null;
    }
  }

  async function viewOriginal(artifactId: string) {
    try {
      await loadScreenArtifact(artifactId);
      imageFullscreen = true;
    } catch {
      // Error is rendered inside the card.
    }
  }

  async function openArtifactFolder(artifactId: string) {
    try {
      const artifact = await loadScreenArtifact(artifactId);
      await windowClient.openPath(artifact.file.directory);
    } catch {
      // Error is rendered inside the card.
    }
  }

  async function downloadArtifact(artifactId: string) {
    try {
      const artifact = await loadScreenArtifact(artifactId);
      const anchor = document.createElement('a');
      anchor.href = artifact.image.dataUrl;
      anchor.download = artifact.file.downloadFilename;
      anchor.rel = 'noopener';
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
    } catch {
      // Error is rendered inside the card.
    }
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      closeFullscreen();
      closeImageFullscreen();
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<section class="border border-isotope-line bg-white text-isotope-text shadow-sm" aria-label={`capacity 调用 ${call.capacityId}`}>
  <div class="flex items-start justify-between gap-3 px-3 py-2">
    <div class="min-w-0">
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-xs font-semibold uppercase text-isotope-muted">capacity</span>
        <span class={`border px-1.5 py-0.5 text-[11px] font-semibold uppercase ${statusClass}`}>{statusLabel}</span>
      </div>
      <div class="mt-1 truncate text-sm font-semibold">{call.title}</div>
      <div class="mt-1 break-words text-xs leading-5 text-isotope-muted">{summary}</div>
    </div>
    <div class="flex shrink-0 items-center gap-1">
      <button
        class="grid h-7 w-7 place-items-center border border-isotope-line bg-isotope-panel text-xs"
        type="button"
        title={expanded ? '收起' : '展开'}
        aria-label={expanded ? '收起 capacity 详情' : '展开 capacity 详情'}
        onclick={toggleExpanded}
      >
        {expanded ? '-' : '+'}
      </button>
      <button
        class="grid h-7 w-7 place-items-center border border-isotope-line bg-isotope-panel text-xs"
        type="button"
        title="全屏"
        aria-label="全屏查看 capacity 详情"
        onclick={openFullscreen}
      >
        []
      </button>
    </div>
  </div>

  {#if expanded}
    <div class="space-y-3 border-t border-isotope-line px-3 py-3">
      {#if screenArtifacts.length}
        <div class="border border-isotope-line bg-isotope-panel px-3 py-2">
          <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div class="min-w-0">
              <div class="text-xs font-semibold uppercase text-isotope-muted">screen screenshot</div>
              <div class="mt-1 truncate text-sm font-semibold text-isotope-text">{screenArtifacts[0].artifactId}</div>
            </div>
            <div class="flex shrink-0 flex-wrap items-center gap-2">
              <button
                class="border border-isotope-running bg-white px-2.5 py-1.5 text-xs font-semibold text-isotope-running disabled:opacity-50"
                type="button"
                disabled={loadingArtifactId === screenArtifacts[0].artifactId}
                onclick={() => viewOriginal(screenArtifacts[0].artifactId)}
              >
                原图
              </button>
              <button
                class="border border-isotope-line bg-white px-2.5 py-1.5 text-xs font-semibold text-isotope-muted disabled:opacity-50"
                type="button"
                disabled={loadingArtifactId === screenArtifacts[0].artifactId}
                onclick={() => openArtifactFolder(screenArtifacts[0].artifactId)}
              >
                文件夹
              </button>
              <button
                class="border border-isotope-line bg-white px-2.5 py-1.5 text-xs font-semibold text-isotope-muted disabled:opacity-50"
                type="button"
                disabled={loadingArtifactId === screenArtifacts[0].artifactId}
                onclick={() => downloadArtifact(screenArtifacts[0].artifactId)}
              >
                下载
              </button>
            </div>
          </div>
          {#if selectedScreenArtifact}
            <div class="mt-2 text-xs text-isotope-muted">
              {selectedScreenArtifact.image.width ?? '?'} x {selectedScreenArtifact.image.height ?? '?'} · {selectedScreenArtifact.file.path}
            </div>
          {/if}
          {#if screenArtifactError}
            <div class="mt-2 border border-isotope-error/40 bg-white px-2 py-1 text-xs text-isotope-error">
              {screenArtifactError}
            </div>
          {/if}
        </div>
      {/if}
      <CapacityCallDetails details={call.details} />
    </div>
  {/if}
</section>

{#if fullscreen}
  <div class="fixed inset-0 z-50 bg-isotope-text/35 p-4" role="dialog" aria-modal="true" aria-label={`capacity 详情 ${call.capacityId}`}>
    <section class="mx-auto flex h-full max-w-5xl flex-col border border-isotope-line bg-white shadow-xl">
      <header class="flex items-start justify-between gap-3 border-b border-isotope-line px-4 py-3">
        <div class="min-w-0">
          <div class="text-xs font-semibold uppercase text-isotope-muted">capacity 详情</div>
          <h2 class="mt-1 truncate text-lg font-semibold">{call.title}</h2>
          <p class="mt-1 text-sm text-isotope-muted">{summary}</p>
        </div>
        <button
          class="grid h-8 w-8 place-items-center border border-isotope-line bg-isotope-panel text-sm"
          type="button"
          aria-label="关闭全屏 capacity 详情"
          onclick={closeFullscreen}
        >
          x
        </button>
      </header>
      <div class="min-h-0 flex-1 overflow-auto p-4">
        <CapacityCallDetails details={call.details} fullscreen />
      </div>
    </section>
  </div>
{/if}

{#if imageFullscreen && selectedScreenArtifact}
  <div class="fixed inset-0 z-[60] bg-black/80 p-3" role="dialog" aria-modal="true" aria-label="screen screenshot 原图">
    <section class="flex h-full flex-col border border-isotope-line bg-white shadow-xl">
      <header class="flex items-center justify-between gap-3 border-b border-isotope-line px-4 py-3">
        <div class="min-w-0">
          <div class="text-xs font-semibold uppercase text-isotope-muted">screen screenshot</div>
          <h2 class="mt-1 truncate text-base font-semibold text-isotope-text">{selectedScreenArtifact.file.downloadFilename}</h2>
        </div>
        <div class="flex shrink-0 items-center gap-2">
          <button
            class="border border-isotope-line bg-isotope-panel px-3 py-1.5 text-xs font-semibold text-isotope-muted"
            type="button"
            onclick={() => openArtifactFolder(selectedScreenArtifact!.artifact.ref.artifact_id)}
          >
            文件夹
          </button>
          <button
            class="border border-isotope-line bg-isotope-panel px-3 py-1.5 text-xs font-semibold text-isotope-muted"
            type="button"
            onclick={() => downloadArtifact(selectedScreenArtifact!.artifact.ref.artifact_id)}
          >
            下载
          </button>
          <button
            class="grid h-8 w-8 place-items-center border border-isotope-line bg-isotope-panel text-sm"
            type="button"
            aria-label="关闭截图原图"
            onclick={closeImageFullscreen}
          >
            x
          </button>
        </div>
      </header>
      <div class="min-h-0 flex-1 overflow-auto bg-[#111] p-4">
        <img
          class="block max-w-none border border-white/20 bg-white"
          src={selectedScreenArtifact.image.dataUrl}
          alt="screen screenshot original"
        />
      </div>
    </section>
  </div>
{/if}
