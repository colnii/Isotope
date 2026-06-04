"""Managed-worker JavaScript rendering for the local Supervisor dashboard."""

from __future__ import annotations


DASHBOARD_SCRIPT_MANAGED = r'''    function renderMultiWorkerStatus(multiWorker) {
      const summary = multiWorker && multiWorker.summary ? multiWorker.summary : {};
      const workers = multiWorker && Array.isArray(multiWorker.workers) ? multiWorker.workers : [];
      document.getElementById("multi-worker-count").textContent = workers.length;
      const summaryTarget = document.getElementById("multi-worker-summary");
      summaryTarget.replaceChildren();
      summaryTarget.append(
        multiWorkerStat("workers", summary.worker_count || 0),
        multiWorkerStat("memory", summary.memory_records_total || 0),
        multiWorkerStat("events", summary.worker_events_total || 0),
        multiWorkerStat("capacity calls", summary.capacity_calls_total || 0)
      );
      const list = document.getElementById("multi-worker-list");
      list.replaceChildren();
      if (!workers.length) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = "暂无多 worker 状态";
        list.append(empty);
        return;
      }
      for (const worker of workers) list.append(renderMultiWorkerCard(worker));
    }

    function multiWorkerStat(label, value) {
      const item = document.createElement("div");
      item.className = "multi-worker-stat";
      const labelNode = document.createElement("span");
      labelNode.textContent = label;
      const valueNode = document.createElement("strong");
      valueNode.textContent = String(value);
      item.append(labelNode, valueNode);
      return item;
    }

    function renderMultiWorkerCard(worker) {
      const card = document.createElement("article");
      card.className = "multi-worker-card";
      const title = document.createElement("div");
      title.className = "multi-worker-title";
      title.textContent = worker.name || "worker";
      const stats = document.createElement("div");
      stats.className = "multi-worker-detail";
      stats.textContent = [
        "memory " + (worker.memory_records_total || 0),
        "in " + (worker.incoming_events_total || 0),
        "out " + (worker.outgoing_events_total || 0),
        "capacity " + (worker.capacity_calls_total || 0)
      ].join(" · ");
      card.append(title, stats);
      if (Array.isArray(worker.capacity_ids) && worker.capacity_ids.length) {
        const capacities = document.createElement("div");
        capacities.className = "multi-worker-detail";
        capacities.textContent = "capacity_id: " + worker.capacity_ids.join(", ");
        card.append(capacities);
      }
      if (worker.recent_capacity_result) {
        const capacity = document.createElement("div");
        capacity.className = "multi-worker-detail";
        capacity.textContent = "最近能力：" + capacityRunDetailText(capacityRunFromWorker(worker));
        card.append(capacity);
      }
      if (worker.recent_event) {
        const event = document.createElement("div");
        event.className = "multi-worker-detail";
        event.textContent = "最近事件：" + [
          worker.recent_event.from_worker || "unknown",
          "->",
          worker.recent_event.to_worker || "*",
          "/",
          worker.recent_event.event_type || "message",
          "/",
          worker.recent_event.message || ""
        ].join(" ");
        card.append(event);
      }
      if (worker.recent_memory) {
        const memory = document.createElement("div");
        memory.className = "multi-worker-detail";
        memory.textContent = "最近记忆：" + [
          worker.recent_memory.record_id || "unknown",
          worker.recent_memory.summary || ""
        ].filter(Boolean).join(" / ");
        card.append(memory);
      }
      return card;
    }

    function capacityRunFromWorker(worker) {
      const recent = worker && worker.recent_capacity_result
        ? worker.recent_capacity_result
        : {};
      return {
        worker: worker ? worker.name : null,
        capacity_id: recent.capacity_id,
        agent_loop_result: recent.agent_loop_result
      };
    }

    function renderCardSource(item) {
      const source = document.createElement("div");
      source.className = "source-line";
      if (item.managed) {
        const lane = item.managed_tmux_session || item.name || item.managed_backend || "未知";
        const linked = item.linked_short_session_id ? "，身份来自 #" + item.linked_short_session_id : "";
        source.textContent = "卡片来源：托管窗口 " + lane + linked;
      } else {
        source.textContent = "卡片来源：普通历史会话";
      }
      return source;
    }

    function renderSupervisorProtocol(item) {
      if (!item.supervisor_status && !item.supervisor_summary && !item.supervisor_next) return null;
      const protocol = document.createElement("div");
      protocol.className = "protocol-card";

      const title = document.createElement("div");
      title.className = "protocol-title";
      title.textContent = "状态汇报";
      protocol.append(title);

      const status = document.createElement("div");
      status.className = "protocol-line";
      status.textContent = "状态：" + text(item.supervisor_status);
      protocol.append(status);

      if (item.supervisor_summary) {
        const summary = document.createElement("div");
        summary.className = "protocol-line";
        summary.textContent = "摘要：" + item.supervisor_summary;
        protocol.append(summary);
      }

      if (item.supervisor_next) {
        const next = document.createElement("div");
        next.className = "protocol-line";
        next.textContent = "下一步：" + item.supervisor_next;
        protocol.append(next);
      }

      return protocol;
    }

    function renderManagedDetails(item) {
      if (!item.managed) return null;
      const details = document.createElement("div");
      details.className = "managed-details";

      const title = document.createElement("div");
      title.className = "managed-details-title";
      title.textContent = "托管窗口";
      details.append(title);

      const bell = document.createElement("div");
      bell.className = "managed-line";
      bell.textContent = "bell：" + bellEventText(item.managed_bell_event_at);
      details.append(bell);

      const bellHook = document.createElement("div");
      bellHook.className = "managed-line";
      bellHook.textContent = "bell hook：" + bellHookText(item.managed_bell_hook_installed);
      details.append(bellHook);

      const terminalReady = document.createElement("div");
      terminalReady.className = "managed-line";
      terminalReady.textContent = "终端状态：" + terminalReadyText(item.managed_terminal_ready);
      details.append(terminalReady);

      if (item.linked_session_id) {
        const linked = document.createElement("div");
        linked.className = "managed-line";
        linked.textContent = "关联 session：" + item.linked_session_id;
        details.append(linked);
      }

      const linkedMatch = renderLinkedMatch(item);
      if (linkedMatch) details.append(linkedMatch);

      const outputTitle = document.createElement("div");
      outputTitle.className = "managed-line";
      outputTitle.textContent = "最近输出";
      details.append(outputTitle);

      const excerpt = document.createElement("pre");
      excerpt.className = "terminal-excerpt";
      excerpt.dataset.scrollKey = terminalExcerptScrollKey(item);
      excerpt.textContent = item.managed_terminal_excerpt || "暂无可读输出";
      excerpt.addEventListener("scroll", () => rememberTerminalExcerptScroll(excerpt));
      details.append(excerpt);
      restoreTerminalExcerptScroll(excerpt);

      return details;
    }

    function bellHookText(value) {
      if (value === true) return "已安装";
      if (value === false) return "未安装";
      return "未确认";
    }

    function bellEventText(value) {
      return value ? "收到于 " + value : "未收到";
    }

    function terminalReadyText(value) {
      return value ? "可输入" : "运行中";
    }

    function renderLinkedMatch(item) {
      if (!item.linked_match) return null;
      const match = item.linked_match;
      const line = document.createElement("div");
      line.className = "managed-line";
      const score = match.score === null || match.score === undefined ? "?" : String(match.score);
      line.textContent = "绑定依据：" + text(match.label) + "（分数 " + score + "）";
      return line;
    }

    function terminalExcerptScrollKey(item) {
      return item.session_id || item.name || item.managed_tmux_session || "";
    }

    function rememberTerminalExcerptScroll(excerpt) {
      const key = excerpt.dataset.scrollKey;
      if (!key) return;
      terminalScrollState.set(key, {
        scrollTop: excerpt.scrollTop,
        nearBottom: isTerminalExcerptNearBottom(excerpt)
      });
    }

    function restoreTerminalExcerptScroll(excerpt) {
      const key = excerpt.dataset.scrollKey;
      const state = key ? terminalScrollState.get(key) : null;
      if (!state || state.nearBottom) {
        scrollTerminalExcerptToBottom(excerpt);
        return;
      }
      window.requestAnimationFrame(() => {
        excerpt.scrollTop = Math.min(state.scrollTop, excerpt.scrollHeight);
        rememberTerminalExcerptScroll(excerpt);
      });
    }

    function scrollTerminalExcerptToBottom(excerpt) {
      window.requestAnimationFrame(() => {
        excerpt.scrollTop = excerpt.scrollHeight;
        rememberTerminalExcerptScroll(excerpt);
      });
    }

    function isTerminalExcerptNearBottom(excerpt) {
      return excerpt.scrollHeight - excerpt.scrollTop - excerpt.clientHeight <= 8;
    }

'''
