"""Core JavaScript helpers for the local Supervisor dashboard."""

from __future__ import annotations


DASHBOARD_SCRIPT_CORE = r'''    const groups = ["needs_attention", "done", "working"];
    let latestLlmAction = null;
    let latestGoalPlanSeed = "";
    let latestGoalPlanPayload = null;
    let notificationsExpanded = false;
    const terminalScrollState = new Map();

    function text(value) {
      return value === null || value === undefined || value === "" ? "无" : String(value);
    }

    function renderLane(item) {
      const lane = document.createElement("article");
      lane.className = "lane";

      const title = document.createElement("div");
      title.className = "lane-title";
      const name = document.createElement("span");
      name.className = "lane-name";
      name.textContent = item.display_title || item.name || item.short_session_id || item.session_id;
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = item.supervisor_status || item.status_label || item.status;
      title.append(name, badge);

      const summary = document.createElement("div");
      summary.className = "summary";
      summary.textContent = item.supervisor_summary || item.reason;

      const evidence = document.createElement("div");
      evidence.className = "evidence";
      if (item.status_evidence) {
        evidence.textContent = "依据：" + item.status_evidence.label + " - " + item.status_evidence.detail;
      } else {
        evidence.textContent = "依据：无";
      }

      const path = document.createElement("div");
      path.className = "path";
      path.textContent = [
        item.short_session_id ? "#" + item.short_session_id : "",
        item.managed_display_title ? "托管 " + item.managed_display_title : "",
        item.agent_nickname ? item.agent_nickname : "",
        item.agent_role ? item.agent_role : "",
        item.cwd,
        item.git_branch ? "分支 " + item.git_branch : ""
      ]
        .filter(Boolean)
        .join(" · ");

      lane.append(title, summary, evidence, path);
      lane.append(renderCardSource(item));
      const protocol = renderSupervisorProtocol(item);
      if (protocol) lane.append(protocol);
      const managedDetails = renderManagedDetails(item);
      if (managedDetails) lane.append(managedDetails);
      const actions = document.createElement("div");
      actions.className = "actions";
      appendLaneActions(actions, item);
      lane.append(actions);
      return lane;
    }

    function appendLaneActions(actions, item) {
      actions.append(renderResumeButton(item));
      for (const command of item.control_commands || []) {
        actions.append(renderCopyControlButton(command));
        if (isManagedSendCommand(command)) {
          actions.append(renderManagedSendButton(item, command));
        }
      }
    }

    function renderResumeButton(item) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "复制 resume";
      button.addEventListener("click", () => copyResumeCommand(item, button));
      return button;
    }

    function renderCopyControlButton(command) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = copyControlLabel(command);
      button.addEventListener("click", () => copyControlCommand(command, button));
      return button;
    }

    function renderManagedSendButton(item, command) {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.action = "send";
      button.dataset.commandKind = command.kind;
      button.dataset.laneName = item.name || "";
      button.textContent = command.kind === "send_status" ? "请求状态" : "继续";
      button.addEventListener("click", () => sendManagedCommand(item, command, button));
      return button;
    }

    function isManagedSendCommand(command) {
      return command.kind === "send_status" || command.kind === "send_continue";
    }

    function renderCurrentItem(title, detail) {
      const item = document.createElement("div");
      item.className = "current-item";
      const titleNode = document.createElement("div");
      titleNode.className = "current-title";
      titleNode.textContent = title;
      const detailNode = document.createElement("div");
      detailNode.className = "current-detail";
      detailNode.textContent = detail;
      item.append(titleNode, detailNode);
      return item;
    }

    function renderCurrentBucket(target, items, emptyText, mapper) {
      target.replaceChildren();
      if (!items.length) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = emptyText;
        target.append(empty);
        return;
      }
      for (const item of items) {
        const mapped = mapper(item);
        target.append(renderCurrentItem(mapped.title, mapped.detail));
      }
    }

    function renderNightOverview(payload) {
      const current = payload.current || {};
      const goals = Array.isArray(current.active_goals) ? current.active_goals : [];
      const workers = Array.isArray(current.managed_workers) ? current.managed_workers : [];
      const runningWorkers = workers.filter((item) => !isTerminalWorker(item));
      const readyItems = readyToIntegrateItems(current);
      const mergeWorker = mergeWorkerStatus(workers);

      renderOverviewItem(
        "daemon",
        serviceIsRunning(payload.daemon) ? "yes" : "no",
        serviceDetail(payload.daemon),
        serviceIsRunning(payload.daemon) ? "running" : "attention"
      );
      renderOverviewItem(
        "watcher",
        serviceIsRunning(payload.watcher) ? "yes" : "no",
        serviceDetail(payload.watcher),
        serviceIsRunning(payload.watcher) ? "running" : "attention"
      );
      renderOverviewItem(
        "active-goals",
        String(goals.length),
        goals.length ? goalNames(goals) : "暂无当前目标",
        goals.length ? "working" : "ready"
      );
      renderOverviewItem(
        "running-workers",
        String(runningWorkers.length),
        runningWorkers.length ? workerNames(runningWorkers) : "暂无运行 worker",
        runningWorkers.length ? "working" : "ready"
      );
      renderOverviewItem(
        "ready-to-integrate",
        String(readyItems.length),
        readyItems.length ? workerNames(readyItems) : "暂无待合入 worker",
        readyItems.length ? "attention" : "ready"
      );
      renderOverviewItem(
        "merge-worker",
        mergeWorker.value,
        mergeWorker.detail,
        mergeWorker.state
      );
    }

    function renderOperatorFocus(payload) {
      const current = payload.current || {};
      const grouped = payload.groups || {};
      const needs = Array.isArray(grouped.needs_attention) ? grouped.needs_attention : [];
      const working = Array.isArray(grouped.working) ? grouped.working : [];
      const focusedNeeds = preferredWorkspaceItems(needs, payload.workspace_cwd);
      const focusedWorking = preferredWorkspaceItems(working, payload.workspace_cwd);
      const goals = Array.isArray(current.active_goals) ? current.active_goals : [];
      document.getElementById("focus-primary-action").textContent = payload.recommendation
        ? payload.recommendation.label
        : "等待数据";
      document.getElementById("focus-daemon").textContent = serviceIsRunning(payload.daemon)
        ? "运行中"
        : "未运行";
      document.getElementById("focus-daemon-detail").textContent = serviceDetail(payload.daemon);
      document.getElementById("focus-needs-attention").textContent = focusCount(focusedNeeds.length, needs.length);
      document.getElementById("focus-needs-attention-detail").textContent = needs.length
        ? focusNames(focusedNeeds)
        : "暂无需要处理的窗口";
      document.getElementById("focus-working").textContent = focusCount(focusedWorking.length, working.length);
      document.getElementById("focus-working-detail").textContent = working.length
        ? focusNames(focusedWorking)
        : "暂无运行窗口";
      document.getElementById("focus-active-goals").textContent = String(goals.length);
      document.getElementById("focus-active-goals-detail").textContent = goals.length
        ? goalNames(goals)
        : "暂无活跃目标";

      const target = document.getElementById("focus-list");
      target.replaceChildren();
      const limit = 3;
      const focusItems = focusedNeeds
        .slice(0, limit)
        .concat(focusedWorking.slice(0, Math.max(0, limit - focusedNeeds.length)));
      if (!focusItems.length) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = "暂无需要立即处理的 Codex 窗口";
        target.append(empty);
        return;
      }
      for (const item of focusItems) {
        target.append(renderFocusItem(item));
      }
    }

    function renderFocusItem(item) {
      const focus = document.createElement("div");
      focus.className = "focus-item";
      const title = document.createElement("div");
      title.className = "focus-title";
      title.textContent = item.display_title || item.name || item.short_session_id || item.session_id || "Codex 窗口";
      const detail = document.createElement("div");
      detail.className = "focus-detail";
      detail.textContent = [
        item.status_label || item.supervisor_status || item.status,
        item.status_evidence ? item.status_evidence.label + " - " + item.status_evidence.detail : "",
        item.cwd || ""
      ].filter(Boolean).join(" · ");
      focus.append(title, detail);
      return focus;
    }

    function focusNames(items) {
      return items
        .map((item) => item.display_title || item.name || item.short_session_id || item.session_id || "窗口")
        .slice(0, 3)
        .join(" / ");
    }

    function preferredWorkspaceItems(items, workspaceCwd) {
      const local = items.filter((item) => itemInWorkspace(item, workspaceCwd));
      return local.length ? local : items;
    }

    function itemInWorkspace(item, workspaceCwd) {
      if (!workspaceCwd || !item || !item.cwd) return false;
      const cwd = String(item.cwd);
      const workspace = String(workspaceCwd).replace(/\/+$/, "");
      return cwd === workspace || cwd.startsWith(workspace + "/");
    }

    function focusCount(localCount, totalCount) {
      if (localCount === totalCount) return String(totalCount);
      return String(localCount) + "/" + String(totalCount);
    }

    function renderControlCenter(payload) {
      renderServiceControl("daemon", payload.daemon);
      renderServiceControl("watcher", payload.watcher);
      document.getElementById("control-message").textContent = "状态已刷新";
    }

'''
