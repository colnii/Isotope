"""Batch and worker-detail JavaScript for the local Supervisor dashboard."""

from __future__ import annotations


DASHBOARD_SCRIPT_BATCHES = r'''    function renderCurrentBatch(current) {
      const goals = current && Array.isArray(current.active_goals) ? current.active_goals : [];
      const workers = current && Array.isArray(current.managed_workers) ? current.managed_workers : [];
      document.getElementById("current-count").textContent = goals.length + workers.length;
      renderCurrentBucket(
        document.getElementById("current-goals"),
        goals,
        "暂无当前目标",
        (item) => ({
          title: item.target_name || item.goal_id,
          detail: [item.goal, item.cwd].filter(Boolean).join(" · ")
        })
      );
      renderCurrentBucket(
        document.getElementById("current-workers"),
        workers,
        "暂无托管 worker",
        (item) => ({
          title: item.name || item.display_title || item.session_id,
          detail: [item.status_label || item.status, item.cwd].filter(Boolean).join(" · ")
        })
      );
      renderDependencyBatch(current ? current.dependency_batch : null);
    }

    function renderDependencyBatch(batch) {
      const target = document.getElementById("dependency-batch");
      target.replaceChildren();
      if (!batch || !batch.summary) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = "暂无依赖批次";
        target.append(empty);
        return;
      }
      const head = document.createElement("div");
      head.className = "dependency-batch-head";
      const title = document.createElement("span");
      title.textContent = "依赖批次";
      const summary = document.createElement("span");
      summary.className = "dependency-batch-summary";
      summary.textContent = dependencyBatchSummary(batch);
      head.append(title, summary);

      const grid = document.createElement("div");
      grid.className = "dependency-batch-grid";
      grid.append(
        renderDependencyBucket("可启动", batch.ready_goals, dependencyReadyDetail),
        renderDependencyBucket("工作中", batch.running_goals, dependencyRunningDetail),
        renderDependencyBucket("等待依赖", batch.blocked_goals, dependencyBlockedDetail),
        renderDependencyBucket("需要处理", batch.attention_goals, dependencyAttentionDetail)
      );
      target.append(head, grid);
    }

    function dependencyBatchSummary(batch) {
      const summary = batch.summary || {};
      return [
        "状态 " + text(batch.status),
        "ready " + text(summary.ready),
        "running " + text(summary.running),
        "blocked " + text(summary.blocked),
        "attention " + text(summary.attention),
        "limit " + text(summary.limit)
      ].join(" · ");
    }

    function renderDependencyBucket(titleText, items, detailMapper) {
      const bucket = document.createElement("div");
      bucket.className = "dependency-bucket";
      const title = document.createElement("div");
      title.className = "dependency-bucket-title";
      const values = Array.isArray(items) ? items : [];
      title.textContent = titleText + " " + String(values.length);
      bucket.append(title);
      if (!values.length) {
        const empty = document.createElement("div");
        empty.className = "dependency-bucket-item";
        empty.textContent = "无";
        bucket.append(empty);
        return bucket;
      }
      for (const item of values.slice(0, 6)) {
        const row = document.createElement("div");
        row.className = "dependency-bucket-item";
        row.textContent = detailMapper(item);
        bucket.append(row);
      }
      return bucket;
    }

    function dependencyGoalName(item) {
      return text(item && (item.target_name || item.goal_id || item.name));
    }

    function dependencyReadyDetail(item) {
      return dependencyGoalName(item);
    }

    function dependencyRunningDetail(item) {
      return dependencyGoalName(item) + " · " + text(item && item.status);
    }

    function dependencyBlockedDetail(item) {
      return dependencyGoalName(item) + " <- " + text(item && item.dependency);
    }

    function dependencyAttentionDetail(item) {
      return dependencyGoalName(item) + " · " + text(item && item.status);
    }

    function renderWorkerDetails(current) {
      const workers = current && Array.isArray(current.managed_workers) ? current.managed_workers : [];
      const target = document.getElementById("worker-detail-list");
      document.getElementById("worker-detail-count").textContent = workers.length;
      target.replaceChildren();
      if (!workers.length) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = "暂无托管 worker";
        target.append(empty);
        return;
      }
      for (const worker of workers) {
        target.append(renderWorkerDetailCard(worker));
      }
    }

    function renderWorkerDetailCard(worker) {
      const card = document.createElement("article");
      card.className = "worker-detail-card";

      const head = document.createElement("div");
      head.className = "worker-detail-head";
      const titleBox = document.createElement("div");
      const title = document.createElement("div");
      title.className = "worker-detail-title";
      title.textContent = workerTitle(worker);
      const meta = document.createElement("div");
      meta.className = "worker-detail-meta";
      meta.textContent = workerMeta(worker);
      titleBox.append(title, meta);
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = workerStatus(worker);
      head.append(titleBox, badge);
      card.append(head);

      const grid = document.createElement("div");
      grid.className = "worker-detail-grid";
      grid.append(...workerDetailFields(worker));
      card.append(grid);

      const protocol = renderSupervisorProtocol(worker);
      if (protocol) card.append(protocol);

      const output = document.createElement("pre");
      output.className = "worker-detail-output";
      output.dataset.scrollKey = "worker-detail:" + terminalExcerptScrollKey(worker);
      output.textContent = workerOutput(worker);
      output.addEventListener("scroll", () => rememberTerminalExcerptScroll(output));
      card.append(output);
      restoreTerminalExcerptScroll(output);
      return card;
    }

    function workerTitle(worker) {
      return worker.display_title || worker.name || worker.target_name || worker.session_id || "worker";
    }

    function workerMeta(worker) {
      return [
        worker.name ? "托管 " + worker.name : "",
        worker.short_session_id ? "#" + worker.short_session_id : "",
        worker.cwd || "",
        worker.git_branch ? "分支 " + worker.git_branch : ""
      ].filter(Boolean).join(" · ");
    }

    function workerStatus(worker) {
      return worker.supervisor_status || worker.status_label || worker.status || "unknown";
    }

    function workerDetailFields(worker) {
      return [
        workerDetailField("目标", worker.goal || worker.target_name || worker.goal_id),
        workerDetailField("工作区", worker.cwd),
        workerDetailField("worktree", worker.worktree || worker.worktree_path),
        workerDetailField("branch", worker.git_branch || worker.branch),
        workerDetailField("状态依据", workerStatusEvidence(worker)),
        workerDetailField("下一步", worker.supervisor_next)
      ];
    }

    function workerStatusEvidence(worker) {
      if (!worker.status_evidence) return null;
      return worker.status_evidence.label + " - " + worker.status_evidence.detail;
    }

    function workerOutput(worker) {
      return worker.managed_terminal_excerpt
        || worker.last_assistant_message
        || worker.last_user_message
        || "暂无可读输出";
    }

    function workerDetailField(label, value) {
      const field = document.createElement("div");
      field.className = "worker-detail-field";
      const labelNode = document.createElement("div");
      labelNode.className = "worker-detail-label";
      labelNode.textContent = label;
      const valueNode = document.createElement("div");
      valueNode.className = "worker-detail-value";
      valueNode.textContent = text(value);
      field.append(labelNode, valueNode);
      return field;
    }

'''
