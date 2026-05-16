"""Local web view for Codex Supervisor dashboard."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .flow import CodexSupervisorFlow
from .runner import _dashboard_payload


class SupervisorDashboardServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        *,
        codex_home: Path,
        limit: int,
        stale_after_seconds: int,
        active_within_seconds: int,
    ) -> None:
        super().__init__(server_address, _DashboardRequestHandler)
        self.codex_home = codex_home
        self.limit = limit
        self.stale_after_seconds = stale_after_seconds
        self.active_within_seconds = active_within_seconds

    def dashboard_payload(self) -> dict[str, Any]:
        report = CodexSupervisorFlow(codex_home=self.codex_home).scan(
            limit=self.limit,
            stale_after_seconds=self.stale_after_seconds,
            active_within_seconds=self.active_within_seconds,
        )
        return _dashboard_payload(report)


def create_dashboard_server(
    *,
    codex_home: Path | str,
    host: str,
    port: int,
    limit: int,
    stale_after_seconds: int,
    active_within_seconds: int,
) -> SupervisorDashboardServer:
    return SupervisorDashboardServer(
        (host, port),
        codex_home=Path(codex_home),
        limit=limit,
        stale_after_seconds=stale_after_seconds,
        active_within_seconds=active_within_seconds,
    )


class _DashboardRequestHandler(BaseHTTPRequestHandler):
    server: SupervisorDashboardServer

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            self._send_text(dashboard_page_html(), content_type="text/html; charset=utf-8")
            return
        if path == "/dashboard.json":
            payload = self.server.dashboard_payload()
            self._send_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                content_type="application/json; charset=utf-8",
            )
            return
        self.send_error(404, "not found")

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_text(self, text: str, *, content_type: str) -> None:
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def dashboard_page_html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Codex Supervisor</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #1f2933;
      --muted: #667085;
      --line: #d9dee7;
      --attention: #b42318;
      --done: #067647;
      --working: #175cd3;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }
    header {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-end;
      padding: 24px 28px 16px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 { margin: 0; font-size: 24px; font-weight: 700; }
    .meta { color: var(--muted); font-size: 13px; text-align: right; }
    main { padding: 20px 28px 28px; }
    .recommendation {
      margin-bottom: 18px;
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-left: 4px solid var(--working);
      border-radius: 6px;
      background: var(--panel);
      font-size: 14px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
    }
    section {
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel);
      overflow: hidden;
    }
    .group-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
    }
    h2 { margin: 0; font-size: 16px; font-weight: 700; }
    .count {
      min-width: 28px;
      text-align: center;
      border-radius: 999px;
      background: #edf1f7;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      padding: 3px 8px;
    }
    .lane-list {
      display: grid;
      gap: 0;
      min-height: 72px;
    }
    .lane {
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
    }
    .lane:last-child { border-bottom: 0; }
    .lane-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 6px;
      font-weight: 700;
      min-width: 0;
    }
    .lane-name {
      overflow-wrap: anywhere;
      min-width: 0;
    }
    .badge {
      flex: 0 0 auto;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 12px;
      background: #edf1f7;
      color: var(--muted);
    }
    .summary,
    .path,
    .command {
      color: var(--muted);
      font-size: 13px;
      overflow-wrap: anywhere;
    }
    .command {
      margin-top: 8px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }
    button {
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #ffffff;
      color: var(--text);
      cursor: pointer;
      font-size: 12px;
      padding: 6px 9px;
    }
    button:hover { background: #f2f4f7; }
    [data-group="needs_attention"] .group-head { border-top: 3px solid var(--attention); }
    [data-group="done"] .group-head { border-top: 3px solid var(--done); }
    [data-group="working"] .group-head { border-top: 3px solid var(--working); }
    .empty {
      padding: 18px 14px;
      color: var(--muted);
      font-size: 13px;
    }
    @media (max-width: 900px) {
      header { display: block; }
      .meta { text-align: left; margin-top: 6px; }
      main { padding: 16px; }
      .grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Codex Supervisor</h1>
    <div class="meta">
      <div id="generated-at">等待数据</div>
      <div id="refresh-state">自动刷新中</div>
    </div>
  </header>
  <main>
    <div class="recommendation" id="recommendation">读取中</div>
    <div class="grid">
      <section data-group="needs_attention">
        <div class="group-head"><h2>需要看</h2><span class="count" id="count-needs_attention">0</span></div>
        <div class="lane-list" id="group-needs_attention"></div>
      </section>
      <section data-group="done">
        <div class="group-head"><h2>已完成</h2><span class="count" id="count-done">0</span></div>
        <div class="lane-list" id="group-done"></div>
      </section>
      <section data-group="working">
        <div class="group-head"><h2>工作中</h2><span class="count" id="count-working">0</span></div>
        <div class="lane-list" id="group-working"></div>
      </section>
    </div>
  </main>
  <script>
    const groups = ["needs_attention", "done", "working"];

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

      const path = document.createElement("div");
      path.className = "path";
      path.textContent = [
        item.short_session_id ? "#" + item.short_session_id : "",
        item.agent_nickname ? item.agent_nickname : "",
        item.agent_role ? item.agent_role : "",
        item.cwd,
        item.git_branch ? "分支 " + item.git_branch : ""
      ]
        .filter(Boolean)
        .join(" · ");

      lane.append(title, summary, path);
      const actions = document.createElement("div");
      actions.className = "actions";
      const copyResume = document.createElement("button");
      copyResume.type = "button";
      copyResume.textContent = "复制 resume";
      copyResume.addEventListener("click", () => copyResumeCommand(item, copyResume));
      actions.append(copyResume);
      lane.append(actions);
      if (item.managed_tmux_session) {
        const command = document.createElement("div");
        command.className = "command";
        command.textContent = "tmux attach -t " + item.managed_tmux_session;
        lane.append(command);
      }
      return lane;
    }

    async function copyResumeCommand(item, button) {
      const command = item.resume_command || ("codex resume " + item.session_id);
      try {
        await navigator.clipboard.writeText(command);
        button.textContent = "已复制";
      } catch (error) {
        button.textContent = command;
      }
      setTimeout(() => {
        button.textContent = "复制 resume";
      }, 1600);
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
    }

    async function loadDashboard() {
      const response = await fetch("/dashboard.json", { cache: "no-store" });
      const payload = await response.json();
      document.getElementById("generated-at").textContent = payload.generated_at;
      document.getElementById("recommendation").textContent = payload.recommendation.label;
      for (const key of groups) renderGroup(key, payload.groups[key] || []);
      document.getElementById("refresh-state").textContent = "最近刷新 " + new Date().toLocaleTimeString();
    }

    loadDashboard().catch((error) => {
      document.getElementById("refresh-state").textContent = "刷新失败：" + text(error.message);
    });
    setInterval(loadDashboard, 5000);
  </script>
</body>
</html>
"""
