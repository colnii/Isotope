"""Static body markup for the local Supervisor dashboard."""

from __future__ import annotations


DASHBOARD_BODY = r'''  <header>
    <h1>Codex Supervisor</h1>
    <div class="meta">
      <div id="generated-at">等待数据</div>
      <div id="snapshot-meta">读模型：unknown</div>
      <div id="refresh-state">自动刷新中</div>
    </div>
  </header>
  <main>
    <div class="recommendation">
      <div class="recommendation-main">
        <div id="recommendation">读取中</div>
        <button id="llm-action-button" type="button">模型建议</button>
      </div>
      <div class="llm-action" id="llm-action-result">未请求模型建议</div>
    </div>
    <div class="operator-focus" id="operator-focus">
      <div class="operator-focus-head">
        <span>运行焦点</span>
        <span class="focus-primary-action" id="focus-primary-action">等待数据</span>
      </div>
      <div class="focus-grid">
        <div class="focus-card">
          <span class="focus-label">后台循环</span>
          <strong class="focus-value" id="focus-daemon">unknown</strong>
          <span class="focus-detail" id="focus-daemon-detail">等待数据</span>
        </div>
        <div class="focus-card">
          <span class="focus-label">需要看</span>
          <strong class="focus-value" id="focus-needs-attention">0</strong>
          <span class="focus-detail" id="focus-needs-attention-detail">暂无</span>
        </div>
        <div class="focus-card">
          <span class="focus-label">工作中</span>
          <strong class="focus-value" id="focus-working">0</strong>
          <span class="focus-detail" id="focus-working-detail">暂无</span>
        </div>
        <div class="focus-card">
          <span class="focus-label">当前目标</span>
          <strong class="focus-value" id="focus-active-goals">0</strong>
          <span class="focus-detail" id="focus-active-goals-detail">暂无</span>
        </div>
      </div>
      <div class="focus-list" id="focus-list"></div>
    </div>
    <div class="control-center" id="control-center">
      <div class="control-center-head">
        <span>Supervisor 控制台</span>
        <span class="control-message" id="control-message">等待数据</span>
      </div>
      <div class="control-center-body">
        <div class="control-service">
          <div class="control-service-title">
            <span>daemon 后台循环</span>
            <span class="badge" id="control-daemon-state">unknown</span>
          </div>
          <div class="control-service-detail" id="control-daemon-detail">等待数据</div>
          <div class="control-service-actions">
            <button type="button" data-service-endpoint="/daemon/start">启动 daemon</button>
            <button type="button" data-service-endpoint="/daemon/stop">停止 daemon</button>
          </div>
        </div>
        <div class="control-service">
          <div class="control-service-title">
            <span>watcher 看门进程</span>
            <span class="badge" id="control-watcher-state">unknown</span>
          </div>
          <div class="control-service-detail" id="control-watcher-detail">等待数据</div>
          <div class="control-service-actions">
            <button type="button" data-service-endpoint="/watcher/start">启动 watcher</button>
            <button type="button" data-service-endpoint="/watcher/stop">停止 watcher</button>
            <button type="button" id="control-refresh">刷新状态</button>
          </div>
        </div>
      </div>
    </div>
    <div class="goal-queue-panel" id="goal-queue-panel">
      <div class="goal-queue-head">
        <span>目标队列</span>
        <span class="count" id="goal-queue-count">0</span>
      </div>
      <div class="goal-add-form">
        <textarea id="goal-add-text" aria-label="新增目标" placeholder="新增目标"></textarea>
        <div class="goal-add-actions">
          <button type="button" id="goal-plan-button">规划目标</button>
          <button type="button" id="goal-add-button">直接新增</button>
        </div>
      </div>
      <div class="goal-add-message" id="goal-add-message">等待输入目标</div>
      <div class="goal-plan-actions" id="goal-plan-actions">
        <button type="button" id="goal-plan-write-button">写入规划目标</button>
      </div>
      <div class="goal-plan-preview" id="goal-plan-preview"></div>
      <div class="goal-queue-list" id="goal-queue-list"></div>
    </div>
    <div class="night-overview" id="night-overview">
      <div class="overview-card" id="overview-card-daemon" data-state="attention">
        <span class="overview-label">daemon running</span>
        <strong class="overview-value" id="overview-daemon">unknown</strong>
        <span class="overview-detail" id="overview-daemon-detail">等待数据</span>
      </div>
      <div class="overview-card" id="overview-card-watcher" data-state="attention">
        <span class="overview-label">watcher running</span>
        <strong class="overview-value" id="overview-watcher">unknown</strong>
        <span class="overview-detail" id="overview-watcher-detail">等待数据</span>
      </div>
      <div class="overview-card" id="overview-card-active-goals" data-state="working">
        <span class="overview-label">active goals</span>
        <strong class="overview-value" id="overview-active-goals">0</strong>
        <span class="overview-detail" id="overview-active-goals-detail">当前目标</span>
      </div>
      <div class="overview-card" id="overview-card-running-workers" data-state="working">
        <span class="overview-label">running workers</span>
        <strong class="overview-value" id="overview-running-workers">0</strong>
        <span class="overview-detail" id="overview-running-workers-detail">托管 worker</span>
      </div>
      <div class="overview-card" id="overview-card-ready-to-integrate" data-state="ready">
        <span class="overview-label">ready_to_integrate</span>
        <strong class="overview-value" id="overview-ready-to-integrate">0</strong>
        <span class="overview-detail" id="overview-ready-to-integrate-detail">等待合入</span>
      </div>
      <div class="overview-card" id="overview-card-merge-worker" data-state="attention">
        <span class="overview-label">merge worker</span>
        <strong class="overview-value" id="overview-merge-worker">none</strong>
        <span class="overview-detail" id="overview-merge-worker-detail">未发现</span>
      </div>
    </div>
    <div class="current-list" id="current-list">
      <div class="current-list-head">
        <span>当前批次</span>
        <span class="count" id="current-count">0</span>
      </div>
      <div class="current-grid">
        <div>
          <div class="current-subhead">当前目标</div>
          <div class="current-items" id="current-goals"></div>
        </div>
        <div>
          <div class="current-subhead">托管 worker</div>
          <div class="current-items" id="current-workers"></div>
        </div>
      </div>
      <div class="dependency-batch" id="dependency-batch"></div>
    </div>
    <div class="worker-detail-list" id="worker-detail-panel">
      <div class="worker-detail-list-head">
        <span>Worker 详情</span>
        <span class="count" id="worker-detail-count">0</span>
      </div>
      <div class="worker-detail-body" id="worker-detail-list"></div>
    </div>
    <div class="multi-worker-panel" id="multi-worker-panel">
      <div class="multi-worker-head">
        <span>多 Worker 状态</span>
        <span class="count" id="multi-worker-count">0</span>
      </div>
      <div class="multi-worker-summary" id="multi-worker-summary"></div>
      <div class="multi-worker-body" id="multi-worker-list"></div>
    </div>
    <div class="grid">
      <section data-group="needs_attention">
        <div class="group-head"><h2>需要看</h2><span class="count" id="count-needs_attention">0</span></div>
        <div class="lane-list" id="group-needs_attention"></div>
      </section>
      <section data-group="working">
        <div class="group-head"><h2>工作中</h2><span class="count" id="count-working">0</span></div>
        <div class="lane-list" id="group-working"></div>
      </section>
      <section data-group="done">
        <div class="group-head"><h2>已完成</h2><span class="count" id="count-done">0</span></div>
        <div class="lane-list" id="group-done"></div>
      </section>
    </div>
    <div class="notification-list" id="notification-list">
      <div class="notification-list-head">
        <span>通知列表</span>
        <span>
          <button type="button" id="notification-toggle">展开通知</button>
          <span class="count" id="notification-count">0</span>
        </span>
      </div>
      <div class="notification-list-body" id="notifications"></div>
    </div>
    <div class="decision-list" id="decision-list">
      <div class="decision-list-head">
        <span>等待拍板列表</span>
        <span class="count" id="decision-count">0</span>
      </div>
      <div class="decision-list-body" id="decision-requests"></div>
    </div>
  </main>
'''
