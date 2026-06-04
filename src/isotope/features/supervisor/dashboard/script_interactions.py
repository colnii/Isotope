"""Interaction JavaScript for the local Supervisor dashboard."""

from __future__ import annotations


DASHBOARD_SCRIPT_INTERACTIONS = r'''    async function copyResumeCommand(item, button) {
      const command = item.resume_command || ("codex resume " + item.session_id);
      await copyText(command, button, "复制 resume");
    }

    function copyControlLabel(command) {
      if (command.kind === "tmux_attach") return "复制 attach";
      if (command.kind === "send_status") return "复制状态";
      if (command.kind === "send_continue") return "复制继续";
      if (command.kind === "archive") return "复制归档";
      return "复制命令";
    }

    async function copyControlCommand(command, button) {
      const label = copyControlLabel(command);
      await copyText(command.command, button, label);
    }

    async function copyWorkerLifecycleExecutionCommand(button) {
      await copyText(button.dataset.command || "", button, "复制执行命令");
    }

    async function copyText(textValue, button, label) {
      try {
        await navigator.clipboard.writeText(textValue);
        button.textContent = "已复制";
      } catch (error) {
        button.textContent = textValue;
      }
      setTimeout(() => {
        button.textContent = label;
      }, 1600);
    }

    async function sendManagedCommand(item, command, button) {
      button.disabled = true;
      const label = button.textContent;
      button.textContent = "发送中";
      try {
        const response = await fetch("/managed/send", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ name: item.name, kind: command.kind })
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error ? payload.error.message : "发送失败");
        button.textContent = "已发送";
      } catch (error) {
        button.textContent = text(error.message);
      }
      setTimeout(() => {
        button.disabled = false;
        button.textContent = label;
      }, 1800);
    }

    function renderLlmAction(action) {
      const result = document.getElementById("llm-action-result");
      const kind = action.kind || "monitor";
      result.className = "llm-action";
      result.replaceChildren();
      if (kind === "ask_user") {
        result.append(renderDecisionRequest(action));
        latestLlmAction = action;
        applyLlmActionHighlight();
        return;
      }
      const target = action.target_name ? " / " + action.target_name : "";
      const command = action.command_suggestion ? " / " + action.command_suggestion.label : "";
      result.textContent = "模型建议：" + kind + target + command + "。原因：" + text(action.reason);
      latestLlmAction = action;
      applyLlmActionHighlight();
    }

    function renderDecisionRequest(action) {
      const card = document.createElement("div");
      const result = document.getElementById("llm-action-result");
      result.className = "llm-action decision-request";

      const title = document.createElement("div");
      title.className = "decision-title";
      title.textContent = "等待拍板";
      card.append(title);

      const question = document.createElement("div");
      question.className = "decision-line";
      question.textContent = "问题：" + text(action.question);
      card.append(question);

      const target = document.createElement("div");
      target.className = "decision-line";
      target.textContent = "目标：" + text(action.target_name || action.session_id);
      card.append(target);

      const context = document.createElement("div");
      context.className = "decision-line";
      context.textContent = "context_status：" + text(action.context_status);
      card.append(context);

      const reason = document.createElement("div");
      reason.className = "decision-line";
      reason.textContent = "原因：" + text(action.reason);
      card.append(reason);

      return card;
    }

    function renderNotifications(notifications, counts) {
      const count = document.getElementById("notification-count");
      const list = document.getElementById("notifications");
      const toggle = document.getElementById("notification-toggle");
      const unread = counts && Number.isInteger(counts.unread)
        ? counts.unread
        : notifications.filter((item) => item.unread).length;
      count.textContent = unread + "/" + notifications.length;
      toggle.textContent = notificationsExpanded ? "收起通知" : "展开通知";
      list.replaceChildren();
      if (notifications.length === 0) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = "暂无";
        list.append(empty);
        return;
      }
      if (!notificationsExpanded) {
        list.append(renderNotificationSummary(notifications, unread));
        return;
      }
      for (const notification of notifications.slice(0, 50)) {
        list.append(renderNotificationItem(notification));
      }
      if (notifications.length > 50) {
        const more = document.createElement("div");
        more.className = "notification-summary";
        more.textContent = "已展开最近 50 条，剩余 " + String(notifications.length - 50) + " 条未显示。";
        list.append(more);
      }
    }

    function renderNotificationSummary(notifications, unread) {
      const wrapper = document.createElement("div");
      wrapper.className = "notification-summary";
      const latest = notifications.slice(0, 5).map((item) => {
        return text(item.title) + "（" + text(item.type) + " / " + notificationSourceSummary(item.source_ref) + "）";
      });
      wrapper.textContent = "默认折叠：未读 " + String(unread) + " / 总计 " + String(notifications.length)
        + "。最近：" + (latest.length ? latest.join("；") : "无");
      return wrapper;
    }

    function renderNotificationItem(notification) {
        const item = document.createElement("div");
        item.className = "notification-list-item";

        const title = document.createElement("div");
        title.className = "notification-title-line";
        const state = document.createElement("span");
        state.className = "badge";
        state.textContent = notification.unread ? "未读" : "已读";
        const type = document.createElement("span");
        type.className = "badge";
        type.textContent = text(notification.type);
        const name = document.createElement("span");
        name.textContent = text(notification.title);
        title.append(state, type, name);
        item.append(title);

        const source = document.createElement("div");
        source.className = "notification-source";
        source.textContent = "来源：" + notificationSourceSummary(notification.source_ref);
        item.append(source);
        return item;
    }

    function notificationSourceSummary(sourceRef) {
      const source = sourceRef || {};
      return [source.ref_type, source.status, source.goal_id, source.run_id]
        .filter(Boolean)
        .join(" · ") || "无";
    }

    function renderDecisionRequests(requests) {
      const count = document.getElementById("decision-count");
      const list = document.getElementById("decision-requests");
      count.textContent = requests.length;
      list.replaceChildren();
      if (requests.length === 0) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = "暂无";
        list.append(empty);
        return;
      }
      for (const request of requests) {
        const item = document.createElement("div");
        item.className = "decision-list-item";
        const target = request.target_name || request.session_id || "未知";
        const line = document.createElement("div");
        line.textContent = text(request.question) + " · context_status=" + text(request.context_status) + " · " + target;
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = "复制归档拍板";
        button.addEventListener("click", () => copyDecisionArchiveCommand(request, button));
        const form = renderDecisionAnswerForm(request);
        item.append(line, form, button);
        list.append(item);
      }
    }

    function renderDecisionAnswerForm(request) {
      const form = document.createElement("div");
      form.className = "decision-answer-form";

      const textarea = document.createElement("textarea");
      textarea.placeholder = "填写答案";
      textarea.setAttribute("aria-label", "填写答案");
      form.append(textarea);

      const actions = document.createElement("div");
      actions.className = "decision-answer-actions";

      const submit = document.createElement("button");
      submit.type = "button";
      submit.textContent = "提交答案";
      const message = document.createElement("span");
      message.className = "decision-answer-message";
      submit.addEventListener("click", () => submitDecisionAnswer(request, textarea, submit, message));
      actions.append(submit, message);
      form.append(actions);

      return form;
    }

    async function submitDecisionAnswer(request, textarea, button, message) {
      const answer = textarea.value.trim();
      if (!answer) {
        message.textContent = "请先填写答案";
        return;
      }
      button.disabled = true;
      const label = button.textContent;
      button.textContent = "提交中";
      message.textContent = "";
      try {
        const response = await fetch("/decision/answer", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ request_id: request.request_id, answer })
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error ? payload.error.message : "提交失败");
        message.textContent = "已记录答案";
        textarea.value = "";
        await loadDashboard();
      } catch (error) {
        message.textContent = text(error.message);
      } finally {
        button.disabled = false;
        button.textContent = label;
      }
    }

    async function copyDecisionArchiveCommand(request, button) {
      const command = "isotope-supervisor decision archive --request-id " + text(request.request_id);
      await copyText(command, button, "复制归档拍板");
    }

    function applyLlmActionHighlight() {
      document.querySelectorAll("button.suggested-action").forEach((button) => {
        button.classList.remove("suggested-action");
        button.removeAttribute("title");
      });
      if (!latestLlmAction || !latestLlmAction.target_name) return;
      const selector = [
        'button[data-action="send"]',
        '[data-command-kind="' + latestLlmAction.kind + '"]',
        '[data-lane-name="' + latestLlmAction.target_name + '"]'
      ].join("");
      const target = document.querySelector(selector);
      if (!target) return;
      target.classList.add("suggested-action");
      target.title = "模型建议：" + text(latestLlmAction.reason);
    }

    async function requestLlmAction(button) {
      const label = button.textContent;
      const result = document.getElementById("llm-action-result");
      button.disabled = true;
      button.textContent = "分析中";
      result.textContent = "正在请求模型建议";
      try {
        const response = await fetch("/llm-action", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: "{}"
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error ? payload.error.message : "模型建议失败");
        renderLlmAction(payload.llm_action);
      } catch (error) {
        result.textContent = "模型建议失败：" + text(error.message);
      } finally {
        button.disabled = false;
        button.textContent = label;
      }
    }

    function renderGroup(key, items) {
      document.getElementById("count-" + key).textContent = items.length;
      const target = document.getElementById("group-" + key);
      target.replaceChildren();
      if (items.length === 0) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = "暂无";
        target.append(empty);
        return;
      }
      for (const item of items) target.append(renderLane(item));
      applyLlmActionHighlight();
    }

    async function loadDashboard() {
      const response = await fetch("/dashboard.json", { cache: "no-store" });
      const payload = await response.json();
      renderDashboardPayload(payload);
    }

    function renderDashboardPayload(payload) {
      document.getElementById("generated-at").textContent = payload.generated_at;
      const snapshotMeta = payload.state_snapshot_meta || {};
      let snapshotMetaText = "读模型：" + text(snapshotMeta.schema_label);
      if (snapshotMeta.schema_status === "degraded") {
        snapshotMetaText += " / degraded";
        if (snapshotMeta.schema_reason) snapshotMetaText += " / " + text(snapshotMeta.schema_reason);
      }
      document.getElementById("snapshot-meta").textContent = snapshotMetaText;
      document.getElementById("recommendation").textContent = payload.recommendation.label;
      renderWorkerLifecycle(payload.worker_lifecycle || {});
      renderWorkerLifecycleExecution(payload.worker_lifecycle_execution || {});
      renderOperatorFocus(payload);
      renderControlCenter(payload);
      renderGoalQueue(payload.current || {});
      renderNightOverview(payload);
      renderCurrentBatch(payload.current || {});
      renderWorkerDetails(payload.current || {});
      renderMultiWorkerStatus(payload.multi_worker || {});
      renderNotifications(payload.notifications || [], payload.notification_counts || {});
      renderDecisionRequests(payload.decision_requests || []);
      for (const key of groups) renderGroup(key, payload.groups[key] || []);
      document.getElementById("refresh-state").textContent = "最近刷新 " + new Date().toLocaleTimeString();
    }

    document.getElementById("llm-action-button").addEventListener("click", (event) => {
      requestLlmAction(event.currentTarget);
    });
    document.querySelectorAll("[data-service-endpoint]").forEach((button) => {
      button.addEventListener("click", () => {
        sendSupervisorServiceAction(button.dataset.serviceEndpoint, button);
      });
    });
    document.getElementById("control-refresh").addEventListener("click", () => {
      loadDashboard();
    });
    document.getElementById("goal-add-button").addEventListener("click", (event) => {
      submitGoalAdd(event.currentTarget);
    });
    document.getElementById("goal-plan-button").addEventListener("click", (event) => {
      submitGoalPlan(event.currentTarget, false);
    });
    document.getElementById("goal-plan-write-button").addEventListener("click", (event) => {
      submitGoalPlan(event.currentTarget, true);
    });
    document.getElementById("worker-lifecycle-execution-copy").addEventListener("click", (event) => {
      copyWorkerLifecycleExecutionCommand(event.currentTarget);
    });
    document.getElementById("notification-toggle").addEventListener("click", () => {
      notificationsExpanded = !notificationsExpanded;
      loadDashboard();
    });

    function connectSupervisorEvents() {
      if (!window.EventSource) return;
      const source = new EventSource("/events");
      source.addEventListener("bell", () => {
        loadDashboard().catch((error) => {
          document.getElementById("refresh-state").textContent = "bell 刷新失败：" + text(error.message);
        });
      });
      source.onerror = () => {
        document.getElementById("refresh-state").textContent = "事件通道等待重连";
      };
    }

    loadDashboard().catch((error) => {
      document.getElementById("refresh-state").textContent = "刷新失败：" + text(error.message);
    });
    connectSupervisorEvents();
    setInterval(loadDashboard, 5000);
'''
