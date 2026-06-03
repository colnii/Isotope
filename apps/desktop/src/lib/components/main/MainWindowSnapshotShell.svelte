<script lang="ts">
  import type { ActivityNode, IsotopeEvent, IsotopeSnapshot } from '../../contracts/isotope';
  import { buildMainWindowSnapshotView } from '../../view/mainWindowView';
  import ActivityTree from '../activity/ActivityTree.svelte';
  import SourceBadge from '../common/SourceBadge.svelte';
  import EventStream from '../events/EventStream.svelte';

  let {
    snapshot,
    events = [],
    selectedActivity,
    selectedActivityId = null,
    onSelectActivity,
    onClose
  } = $props<{
    snapshot: IsotopeSnapshot;
    events?: IsotopeEvent[];
    selectedActivity: ActivityNode | null;
    selectedActivityId?: string | null;
    onSelectActivity: (id: string) => void;
    onClose: () => void;
  }>();

  const view = $derived(buildMainWindowSnapshotView(snapshot, selectedActivity));
</script>

<section
  class="fixed inset-6 z-10 grid overflow-hidden border border-isotope-line bg-white shadow-2xl lg:grid-cols-[280px_minmax(0,1fr)_260px]"
  aria-label="Isotope 主窗口快照外壳"
>
  <aside class="border-b border-isotope-line bg-white/95 p-4 lg:border-b-0 lg:border-r">
    <div class="flex items-center justify-between gap-3">
      <h2 class="text-sm font-semibold">活动</h2>
      <SourceBadge source={snapshot.source} />
    </div>
    <div class="mt-3 max-h-[calc(100vh-9rem)] overflow-auto">
      <ActivityTree nodes={snapshot.activities} selectedId={selectedActivityId} onSelect={onSelectActivity} />
    </div>
  </aside>

  <main class="min-w-0 overflow-auto p-5">
    <div class="flex items-start justify-between gap-4">
      <div class="min-w-0">
        <div class="text-xs uppercase text-isotope-muted">当前活动</div>
        <h1 class="mt-1 truncate text-xl font-semibold">{view.selectedActivityTitle}</h1>
        <p class="mt-1 text-sm text-isotope-muted">
          {view.selectedActivityKind} · {view.selectedActivityStatus}
        </p>
      </div>
      <button class="border border-isotope-line px-2 py-1 text-sm" type="button" aria-label="关闭主窗口" onclick={onClose}>
        关闭
      </button>
    </div>

    {#if view.selectedActivitySummary}
      <p class="mt-4 border border-isotope-line bg-isotope-panel p-3 text-sm text-isotope-muted">
        {view.selectedActivitySummary}
      </p>
    {/if}

    <section class="mt-5 border-t border-isotope-line pt-4">
      <div class="text-xs uppercase text-isotope-muted">活跃目标</div>
      <p class="mt-1 text-base">{view.activeGoalTitle}</p>
    </section>
  </main>

  <aside class="border-t border-isotope-line bg-white/95 p-4 lg:border-l lg:border-t-0">
    <h2 class="text-sm font-semibold">快照状态</h2>
    <dl class="mt-3 grid grid-cols-2 gap-2 text-sm">
      <div class="border border-isotope-line p-2">
        <dt class="text-xs text-isotope-muted">活动</dt>
        <dd class="mt-1 font-semibold">{view.activityCount}</dd>
      </div>
      <div class="border border-isotope-line p-2">
        <dt class="text-xs text-isotope-muted">运行中</dt>
        <dd class="mt-1 font-semibold">{view.runningAgents}</dd>
      </div>
      <div class="border border-isotope-line p-2">
        <dt class="text-xs text-isotope-muted">需处理</dt>
        <dd class="mt-1 font-semibold">{view.needsAttention}</dd>
      </div>
      <div class="border border-isotope-line p-2">
        <dt class="text-xs text-isotope-muted">审批</dt>
        <dd class="mt-1 font-semibold">{view.approvalCount}</dd>
      </div>
      <div class="border border-isotope-line p-2">
        <dt class="text-xs text-isotope-muted">产物</dt>
        <dd class="mt-1 font-semibold">{view.artifactCount}</dd>
      </div>
      <div class="border border-isotope-line p-2">
        <dt class="text-xs text-isotope-muted">错误</dt>
        <dd class="mt-1 font-semibold">{view.errorCount}</dd>
      </div>
    </dl>

    <section class="mt-4">
      <h3 class="text-xs font-semibold uppercase text-isotope-muted">审批摘要</h3>
      {#if view.approvalItems.length > 0}
        <ul class="mt-2 space-y-2">
          {#each view.approvalItems as approval (approval.id)}
            <li class="border border-isotope-line p-2 text-sm">
              <span class="flex items-start justify-between gap-2">
                <span class="min-w-0">
                  <span class="block truncate font-medium">{approval.title}</span>
                  <span class="text-xs text-isotope-muted">
                    {approval.status}{approval.riskLevel ? ` · ${approval.riskLevel}` : ''}
                  </span>
                </span>
                <SourceBadge source={approval.source} />
              </span>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="mt-2 text-sm text-isotope-muted">暂无审批项。</p>
      {/if}
    </section>

    <div class="mt-4">
      <EventStream events={events} />
    </div>
  </aside>
</section>
