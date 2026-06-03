<script lang="ts">
  import type { ActivityNode, IsotopeEvent, IsotopeSnapshot } from '../../contracts/isotope';
  import type { SnapshotView } from '../../view/snapshotView';
  import MainWindowSnapshotShell from '../main/MainWindowSnapshotShell.svelte';
  import DebugSourceBadge from './DebugSourceBadge.svelte';

  let {
    snapshot,
    selectedActivity,
    selectedActivityId,
    isLoading,
    loadError,
    view,
    mainOpen,
    events,
    onSelectActivity,
    onOpenMain,
    onCloseMain
  } = $props<{
    snapshot: IsotopeSnapshot | null;
    selectedActivity: ActivityNode | null;
    selectedActivityId: string | null;
    isLoading: boolean;
    loadError: string | null;
    view: SnapshotView | null;
    mainOpen: boolean;
    events: IsotopeEvent[];
    onSelectActivity: (activityId: string) => void;
    onOpenMain: () => void;
    onCloseMain: () => void;
  }>();
</script>

<div class="mx-auto grid max-w-6xl gap-4 lg:grid-cols-[260px_minmax(0,1fr)_260px]" aria-label="开发诊断外壳">
  <aside class="border border-isotope-line bg-white/90 p-4">
    <div class="flex items-center justify-between gap-3">
      <h2 class="text-sm font-semibold">活动</h2>
      {#if snapshot}
        <DebugSourceBadge source={snapshot.source} />
      {/if}
    </div>
    <div class="mt-3 space-y-2">
      {#if snapshot}
        {#each snapshot.activities as activity (activity.id)}
          <button
            class="block w-full border border-isotope-line px-3 py-2 text-left text-sm hover:bg-isotope-panel"
            class:bg-isotope-panel={selectedActivity?.id === activity.id}
            type="button"
            onclick={() => onSelectActivity(activity.id)}
          >
            <span class="block font-medium">{activity.title}</span>
            <span class="block text-xs text-isotope-muted">{activity.kind} · {activity.status}</span>
          </button>
        {/each}
      {:else if isLoading}
        <p class="text-sm text-isotope-muted">正在加载快照...</p>
      {:else}
        <p class="text-sm text-isotope-muted">暂无已加载快照。</p>
      {/if}
    </div>
  </aside>

  <section class="border border-isotope-line bg-white/95 p-5">
    {#if view}
      <div class="text-xs uppercase text-isotope-muted">当前 Agent</div>
      <h1 class="mt-1 text-xl font-semibold">{view.agentTitle}</h1>
      <p class="mt-3 text-sm text-isotope-muted">活跃目标</p>
      <p class="mt-1 text-base">{view.activeGoalTitle}</p>
      <div class="mt-5 border-t border-isotope-line pt-4">
        <div class="text-xs uppercase text-isotope-muted">当前活动</div>
        <h2 class="mt-1 text-lg font-semibold">{view.selectedActivityTitle}</h2>
        {#if selectedActivity?.summary}
          <p class="mt-2 text-sm text-isotope-muted">{selectedActivity.summary}</p>
        {/if}
      </div>
    {:else if loadError}
      <h1 class="text-xl font-semibold">快照不可用</h1>
      <p class="mt-2 text-sm text-isotope-muted">{loadError}</p>
    {:else}
      <h1 class="text-xl font-semibold">Isotope Desktop</h1>
      <p class="mt-2 text-sm text-isotope-muted">等待桌面快照。</p>
    {/if}
  </section>

  <aside class="border border-isotope-line bg-white/90 p-4">
    <h2 class="text-sm font-semibold">状态</h2>
    {#if view && snapshot}
      <dl class="mt-3 grid grid-cols-2 gap-2 text-sm">
        <div class="border border-isotope-line p-2">
          <dt class="text-xs text-isotope-muted">活动</dt>
          <dd class="mt-1 font-semibold">{view.activityCount}</dd>
        </div>
        <div class="border border-isotope-line p-2">
          <dt class="text-xs text-isotope-muted">审批</dt>
          <dd class="mt-1 font-semibold">{view.approvalCount}</dd>
        </div>
        <div class="border border-isotope-line p-2">
          <dt class="text-xs text-isotope-muted">需处理</dt>
          <dd class="mt-1 font-semibold">{view.needsAttention}</dd>
        </div>
        <div class="border border-isotope-line p-2">
          <dt class="text-xs text-isotope-muted">错误</dt>
          <dd class="mt-1 font-semibold">{snapshot.counts.errors}</dd>
        </div>
      </dl>
      <div class="mt-4">
        <h3 class="text-xs font-semibold uppercase text-isotope-muted">审批摘要</h3>
        {#if snapshot.approvals.length > 0}
          <ul class="mt-2 space-y-2">
            {#each snapshot.approvals as approval (approval.id)}
              <li class="border border-isotope-line p-2 text-sm">
                <span class="block font-medium">{approval.title}</span>
                <span class="text-xs text-isotope-muted">{approval.status}</span>
              </li>
            {/each}
          </ul>
        {:else}
          <p class="mt-2 text-sm text-isotope-muted">暂无审批项。</p>
        {/if}
      </div>
    {:else}
      <p class="mt-3 text-sm text-isotope-muted">暂无状态。</p>
    {/if}
  </aside>
</div>

{#if snapshot}
  {#if mainOpen}
    <MainWindowSnapshotShell
      snapshot={snapshot}
      events={events}
      selectedActivity={selectedActivity}
      selectedActivityId={selectedActivityId}
      onSelectActivity={onSelectActivity}
      onClose={onCloseMain}
    />
  {/if}
{/if}
