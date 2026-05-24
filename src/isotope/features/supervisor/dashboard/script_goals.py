"""Goal-planning JavaScript for the local Supervisor dashboard."""

from __future__ import annotations


DASHBOARD_SCRIPT_GOALS = r'''    function renderGoalQueue(current) {
      const goals = current && Array.isArray(current.active_goals) ? current.active_goals : [];
      const target = document.getElementById("goal-queue-list");
      document.getElementById("goal-queue-count").textContent = goals.length;
      target.replaceChildren();
      if (!goals.length) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = "暂无活跃目标";
        target.append(empty);
        return;
      }
      for (const goal of goals) {
        target.append(renderGoalQueueItem(goal));
      }
    }

    function renderGoalQueueItem(goal) {
      const item = document.createElement("div");
      item.className = "goal-queue-item";
      const title = document.createElement("div");
      title.className = "goal-title";
      title.textContent = goal.goal || goal.target_name || goal.goal_id || "目标";
      const detail = document.createElement("div");
      detail.className = "goal-detail";
      detail.textContent = [
        goal.target_name ? "target " + goal.target_name : "",
        goal.goal_id || "",
        goal.last_status ? "状态 " + goal.last_status : "",
        goal.cwd || ""
      ].filter(Boolean).join(" · ");
      item.append(title, detail);
      return item;
    }

    async function submitGoalAdd(button) {
      const textarea = document.getElementById("goal-add-text");
      const message = document.getElementById("goal-add-message");
      const goal = textarea.value.trim();
      if (!goal) {
        message.textContent = "请先填写目标";
        return;
      }
      const label = button.textContent;
      button.disabled = true;
      button.textContent = "写入中";
      message.textContent = "正在写入目标";
      try {
        const response = await fetch("/goal/add", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ goal })
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error ? payload.error.message : "写入失败");
        textarea.value = "";
        message.textContent = "已写入目标：" + text(payload.goal && payload.goal.target_name);
        await loadDashboard();
      } catch (error) {
        message.textContent = "写入失败：" + text(error.message);
      } finally {
        button.disabled = false;
        button.textContent = label;
      }
    }

    async function submitGoalPlan(button, write) {
      const textarea = document.getElementById("goal-add-text");
      const message = document.getElementById("goal-add-message");
      const goal = textarea.value.trim() || latestGoalPlanSeed;
      if (!goal) {
        message.textContent = "请先填写目标";
        return;
      }
      const label = button.textContent;
      button.disabled = true;
      button.textContent = write ? "写入中" : "规划中";
      message.textContent = write ? "正在写入规划目标" : "正在让模型规划目标";
      try {
        const response = await fetch("/goal/plan", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(goalPlanRequestBody(goal, write))
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error ? payload.error.message : "规划失败");
        latestGoalPlanSeed = goal;
        latestGoalPlanPayload = write ? null : payload;
        renderGoalPlanPreview(payload);
        message.textContent = write
          ? "已写入规划目标：" + String((payload.written_goals || []).length)
          : "已生成规划：" + String((payload.candidates || []).length) + " 个目标";
        if (write) {
          textarea.value = "";
          latestGoalPlanSeed = "";
          latestGoalPlanPayload = null;
          await loadDashboard();
        }
      } catch (error) {
        message.textContent = (write ? "写入失败：" : "规划失败：") + text(error.message);
      } finally {
        button.disabled = false;
        button.textContent = label;
      }
    }

    function goalPlanRequestBody(goal, write) {
      const body = { goal, write };
      if (write && latestGoalPlanPayload && Array.isArray(latestGoalPlanPayload.candidates)) {
        Object.assign(body, collectEditedGoalPlanPayload());
      }
      return body;
    }

    function collectEditedGoalPlanPayload() {
      const preview = document.getElementById("goal-plan-preview");
      const candidates = Array.from(preview.querySelectorAll(".goal-plan-candidate"))
        .map((item) => ({
          target_name: fieldValue(item, "target_name"),
          goal: fieldValue(item, "goal"),
          reason: fieldValue(item, "reason")
        }))
        .filter((item) => item.goal);
      const parallel = Array.from(preview.querySelectorAll(".goal-plan-parallel"))
        .map((item) => ({
          batch: fieldValue(item, "batch"),
          targets: splitTargets(fieldValue(item, "targets")),
          reason: fieldValue(item, "reason")
        }))
        .filter((item) => item.batch || item.targets.length || item.reason);
      return {
        candidates,
        plan_summary: latestGoalPlanPayload ? latestGoalPlanPayload.plan_summary : null,
        phases: latestGoalPlanPayload ? latestGoalPlanPayload.phases : [],
        parallel_recommendations: parallel,
        stop_conditions: latestGoalPlanPayload ? latestGoalPlanPayload.stop_conditions : [],
        acceptance_conditions: latestGoalPlanPayload ? latestGoalPlanPayload.acceptance_conditions : []
      };
    }

    function fieldValue(container, name) {
      const field = container.querySelector('[data-goal-plan-field="' + name + '"]');
      return field ? field.value.trim() : "";
    }

    function splitTargets(value) {
      return value.split(/[\n,，/]+/).map((item) => item.trim()).filter(Boolean);
    }

    function renderGoalPlanPreview(payload) {
      const target = document.getElementById("goal-plan-preview");
      const actions = document.getElementById("goal-plan-actions");
      target.replaceChildren();
      const candidates = Array.isArray(payload.candidates) ? payload.candidates : [];
      actions.dataset.visible = candidates.length && payload.mode !== "write" ? "true" : "false";
      if (payload.plan_summary) {
        target.append(renderGoalPlanCard("规划摘要", payload.plan_summary));
      }
      const parallel = Array.isArray(payload.parallel_recommendations)
        ? payload.parallel_recommendations
        : [];
      for (const item of parallel) {
        target.append(renderEditableParallelRecommendation(item));
      }
      for (const item of candidates) {
        target.append(renderEditableGoalCandidate(item));
      }
    }

    function renderGoalPlanCard(titleText, detailText) {
      const item = document.createElement("div");
      item.className = "goal-plan-card";
      const title = document.createElement("div");
      title.className = "goal-plan-title";
      title.textContent = titleText;
      const detail = document.createElement("div");
      detail.className = "goal-plan-detail";
      detail.textContent = detailText;
      item.append(title, detail);
      return item;
    }

    function renderEditableGoalCandidate(item) {
      const card = document.createElement("div");
      card.className = "goal-plan-card goal-plan-candidate";
      const title = document.createElement("div");
      title.className = "goal-plan-title";
      title.textContent = item.target_name || "目标";
      const grid = document.createElement("div");
      grid.className = "goal-plan-edit-grid";
      grid.append(
        goalPlanInput("target_name", "目标名", item.target_name || ""),
        goalPlanTextarea("goal", "目标内容", item.goal || ""),
        goalPlanTextarea("reason", "依据", item.reason || "")
      );
      card.append(title, grid, goalPlanMoveActions(card));
      return card;
    }

    function renderEditableParallelRecommendation(item) {
      const card = document.createElement("div");
      card.className = "goal-plan-card goal-plan-parallel";
      const title = document.createElement("div");
      title.className = "goal-plan-title";
      title.textContent = "并行建议";
      const targets = Array.isArray(item.targets) ? item.targets.join("\n") : "";
      const grid = document.createElement("div");
      grid.className = "goal-plan-edit-grid";
      grid.append(
        goalPlanInput("batch", "批次", item.batch || ""),
        goalPlanTextarea("targets", "目标名列表", targets),
        goalPlanTextarea("reason", "并行原因", item.reason || "")
      );
      card.append(title, grid, goalPlanMoveActions(card));
      return card;
    }

    function goalPlanInput(name, labelText, value) {
      const label = document.createElement("label");
      label.textContent = labelText;
      const input = document.createElement("input");
      input.type = "text";
      input.value = value;
      input.dataset.goalPlanField = name;
      label.append(input);
      return label;
    }

    function goalPlanTextarea(name, labelText, value) {
      const label = document.createElement("label");
      label.textContent = labelText;
      const textarea = document.createElement("textarea");
      textarea.value = value;
      textarea.dataset.goalPlanField = name;
      label.append(textarea);
      return label;
    }

    function goalPlanMoveActions(card) {
      const actions = document.createElement("div");
      actions.className = "goal-plan-card-actions";
      const up = document.createElement("button");
      up.type = "button";
      up.textContent = "上移";
      up.addEventListener("click", () => moveGoalPlanCard(card, -1));
      const down = document.createElement("button");
      down.type = "button";
      down.textContent = "下移";
      down.addEventListener("click", () => moveGoalPlanCard(card, 1));
      actions.append(up, down);
      return actions;
    }

    function moveGoalPlanCard(card, direction) {
      const parent = card.parentElement;
      if (!parent) return;
      const selector = card.classList.contains("goal-plan-parallel")
        ? ".goal-plan-parallel"
        : ".goal-plan-candidate";
      const cards = Array.from(parent.querySelectorAll(selector));
      const index = cards.indexOf(card);
      const swap = cards[index + direction];
      if (!swap) return;
      if (direction < 0) {
        parent.insertBefore(card, swap);
      } else {
        parent.insertBefore(swap, card);
      }
    }

    function renderServiceControl(key, service) {
      document.getElementById("control-" + key + "-state").textContent = text(service && service.status);
      document.getElementById("control-" + key + "-detail").textContent = serviceDetail(service);
    }

    async function sendSupervisorServiceAction(endpoint, button) {
      const label = button.textContent;
      const message = document.getElementById("control-message");
      button.disabled = true;
      button.textContent = "执行中";
      message.textContent = "正在执行 " + endpoint;
      try {
        const response = await fetch(endpoint, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: "{}"
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error ? payload.error.message : "操作失败");
        const service = payload.service || {};
        message.textContent = text(payload.target) + " " + text(payload.action) + "：" + text(service.status);
        await loadDashboard();
      } catch (error) {
        message.textContent = "操作失败：" + text(error.message);
      } finally {
        button.disabled = false;
        button.textContent = label;
      }
    }

    function renderOverviewItem(key, value, detail, state) {
      document.getElementById("overview-" + key).textContent = value;
      document.getElementById("overview-" + key + "-detail").textContent = detail;
      document.getElementById("overview-card-" + key).dataset.state = state;
    }

    function serviceIsRunning(item) {
      return item && item.status === "running";
    }

    function serviceDetail(item) {
      if (!item) return "无状态";
      const pid = item.pid ? "pid " + item.pid : "无 pid";
      return text(item.status) + " · " + pid;
    }

    function isTerminalWorker(item) {
      const status = String(item.supervisor_status || item.status || "").toLowerCase();
      return ["archived", "completed", "done", "exited", "stale"].includes(status);
    }

    function readyToIntegrateItems(current) {
      const candidates = current.automation_candidates || {};
      const reviews = current.worker_reviews || {};
      const reviewCandidates = reviews.automation_candidates || {};
      const direct = Array.isArray(candidates.ready_to_integrate) ? candidates.ready_to_integrate : [];
      const reviewed = Array.isArray(reviewCandidates.ready_to_integrate)
        ? reviewCandidates.ready_to_integrate
        : [];
      return [...direct, ...reviewed];
    }

    function mergeWorkerStatus(workers) {
      const worker = workers.find((item) => {
        const label = [
          item.name,
          item.display_title,
          item.managed_display_title,
          item.target_name,
          item.session_id
        ].filter(Boolean).join(" ").toLowerCase();
        return label.includes("merge");
      });
      if (!worker) {
        return { value: "none", detail: "未发现", state: "attention" };
      }
      const status = text(worker.supervisor_status || worker.status_label || worker.status);
      return {
        value: status,
        detail: text(worker.name || worker.display_title || worker.session_id),
        state: status === "done" ? "ready" : "working"
      };
    }

    function goalNames(items) {
      return items.map((item) => item.target_name || item.goal_id || item.goal || "目标").slice(0, 3).join(" / ");
    }

    function workerNames(items) {
      return items.map((item) => item.name || item.display_title || item.target_name || item.record_id || "worker").slice(0, 3).join(" / ");
    }

'''
