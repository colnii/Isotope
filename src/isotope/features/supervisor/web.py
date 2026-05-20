"""Local web view for Codex Supervisor dashboard."""

from __future__ import annotations

import json
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .bell_events import default_bell_events_path, read_latest_bell_events
from .context import read_recent_context_results
from .decision_requests import (
    read_active_decision_requests,
    read_recent_decision_answers,
    record_decision_answer,
)
from .flow import CodexSupervisorFlow, _tmux_capture_pane
from .lane_state import record_lane_prompt
from .llm_summary import (
    SummaryProvider,
    generate_llm_action_decision,
    resolve_summary_provider_from_env,
)
from .registry import TmuxBellHookRepair, repair_tmux_bell_hooks, send_to_managed_codex
from .runner import (
    EXECUTABLE_ADVICE_KINDS,
    EXECUTABLE_ADVICE_TEXT,
    _advice_payload,
    _dashboard_payload,
    _notification_dicts,
)


class SupervisorDashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        *,
        codex_home: Path,
        limit: int,
        stale_after_seconds: int,
        active_within_seconds: int,
        send_run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        repair_run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        llm_action_provider: SummaryProvider | None = None,
    ) -> None:
        super().__init__(server_address, _DashboardRequestHandler)
        self.codex_home = codex_home
        self.limit = limit
        self.stale_after_seconds = stale_after_seconds
        self.active_within_seconds = active_within_seconds
        self.send_run = send_run
        self.llm_action_provider = llm_action_provider
        self.bell_events_path = default_bell_events_path(self.codex_home)
        self.bell_hook_repairs: tuple[TmuxBellHookRepair, ...] = repair_tmux_bell_hooks(
            codex_home=self.codex_home,
            run=repair_run,
        )

    def _scan_report(self) -> Any:
        return CodexSupervisorFlow(
            codex_home=self.codex_home,
            tmux_pane_reader=_tmux_capture_pane,
        ).scan(
            limit=self.limit,
            stale_after_seconds=self.stale_after_seconds,
            active_within_seconds=self.active_within_seconds,
        )

    def dashboard_payload(self) -> dict[str, Any]:
        report = self._scan_report()
        return _dashboard_payload(
            report,
            decision_requests=_decision_request_dicts(self.codex_home),
            notifications=_notification_dicts(self.codex_home),
        )

    def llm_action_payload(self) -> dict[str, Any]:
        report = self._scan_report()
        payload = _advice_payload(report)
        recent_context_results = _recent_context_results_for_report(
            codex_home=self.codex_home,
            report=report,
        )
        payload["recent_context_results"] = recent_context_results
        provider = self.llm_action_provider or resolve_summary_provider_from_env(
            agent_name="supervisor"
        )
        payload["llm_action"] = generate_llm_action_decision(
            report,
            payload["command_suggestions"],
            provider,
            recent_context_results,
            None,
            _decision_answer_dicts(self.codex_home),
        )
        return payload

    def bell_event_stamp(self) -> tuple[int, int]:
        try:
            stat = self.bell_events_path.stat()
        except OSError:
            return (0, 0)
        return (stat.st_mtime_ns, stat.st_size)

    def latest_bell_event_payload(self) -> dict[str, Any]:
        events = read_latest_bell_events(self.bell_events_path)
        if not events:
            return {"event": "bell"}
        latest = max(events.values(), key=lambda event: event.created_at)
        return latest.to_dict()


def create_dashboard_server(
    *,
    codex_home: Path | str,
    host: str,
    port: int,
    limit: int,
    stale_after_seconds: int,
    active_within_seconds: int,
    send_run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    repair_run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    llm_action_provider: SummaryProvider | None = None,
) -> SupervisorDashboardServer:
    return SupervisorDashboardServer(
        (host, port),
        codex_home=Path(codex_home),
        limit=limit,
        stale_after_seconds=stale_after_seconds,
        active_within_seconds=active_within_seconds,
        send_run=send_run,
        repair_run=repair_run,
        llm_action_provider=llm_action_provider,
    )


def _recent_context_results_for_report(
    *,
    codex_home: Path,
    report: Any,
) -> list[dict[str, Any]]:
    cwd = _context_cwd_for_report(report)
    results = read_recent_context_results(
        codex_home=codex_home,
        cwd=Path(cwd) if cwd else None,
    )
    return [result.to_dict() for result in results]


def _decision_request_dicts(codex_home: Path) -> list[dict[str, Any]]:
    return [
        request.to_dict()
        for request in read_active_decision_requests(codex_home=codex_home)
    ]


def _decision_answer_dicts(codex_home: Path) -> list[dict[str, Any]]:
    return [
        dict(answer)
        for answer in read_recent_decision_answers(codex_home=codex_home)
    ]


def _context_cwd_for_report(report: Any) -> str | None:
    for session in report.sessions:
        cwd = getattr(session, "cwd", None)
        if isinstance(cwd, str) and cwd:
            return cwd
    return None


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
        if path == "/events":
            self._send_events()
            return
        self.send_error(404, "not found")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/managed/send":
            self._send_managed_command()
            return
        if path == "/llm-action":
            self._send_llm_action()
            return
        if path == "/decision/answer":
            self._send_decision_answer()
            return
        self._send_json(
            {
                "status": "error",
                "error": {
                    "code": "codex_supervisor_web_error",
                    "message": "unknown endpoint",
                },
            },
            status_code=404,
        )

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_managed_command(self) -> None:
        try:
            payload = self._read_json_body()
            kind = _required_string(payload.get("kind"), "kind")
            name = _required_string(payload.get("name"), "name")
            if kind not in EXECUTABLE_ADVICE_KINDS:
                supported = ", ".join(sorted(EXECUTABLE_ADVICE_KINDS))
                raise ValueError(f"kind supports only: {supported}")
            result = send_to_managed_codex(
                codex_home=self.server.codex_home,
                name=name,
                text=EXECUTABLE_ADVICE_TEXT[kind],
                run=self.server.send_run,
            )
            lane_state = record_lane_prompt(
                codex_home=self.server.codex_home,
                name=result.record.name,
                tmux_session=result.record.tmux_session,
                status=kind,
            )
        except ValueError as exc:
            self._send_json(
                {
                    "status": "error",
                    "error": {
                        "code": "codex_supervisor_web_error",
                        "message": str(exc),
                    },
                },
                status_code=400,
            )
            return
        self._send_json(
            {
                "status": "ok",
                "kind": kind,
                "text": result.text,
                "managed": {
                    "name": result.record.name,
                    "record_id": result.record.record_id,
                    "tmux_session": result.record.tmux_session,
                },
                "lane_state": lane_state.to_dict(),
            }
        )

    def _send_llm_action(self) -> None:
        try:
            self._read_json_body()
            payload = self.server.llm_action_payload()
        except ValueError as exc:
            self._send_json(
                {
                    "status": "error",
                    "error": {
                        "code": "codex_supervisor_web_error",
                        "message": str(exc),
                    },
                },
                status_code=400,
            )
            return
        self._send_json(payload)

    def _send_decision_answer(self) -> None:
        try:
            payload = self._read_json_body()
            request_id = _required_string(payload.get("request_id"), "request_id")
            answer = _required_string(payload.get("answer"), "answer")
            answered = record_decision_answer(
                codex_home=self.server.codex_home,
                request_id=request_id,
                answer=answer,
            )
        except ValueError as exc:
            self._send_json(
                {
                    "status": "error",
                    "error": {
                        "code": "codex_supervisor_web_error",
                        "message": str(exc),
                    },
                },
                status_code=400,
            )
            return
        self._send_json(
            {
                "status": "ok",
                "answered": answered,
                "decision_requests": _decision_request_dicts(self.server.codex_home),
                "recent_decision_answers": _decision_answer_dicts(self.server.codex_home),
            }
        )

    def _send_events(self) -> None:
        self.send_response(200)
        self.send_header("content-type", "text/event-stream; charset=utf-8")
        self.send_header("cache-control", "no-store")
        self.send_header("connection", "keep-alive")
        self.end_headers()
        self._write_sse("ready", {"status": "ok"})
        previous_stamp = self.server.bell_event_stamp()
        last_heartbeat = time.monotonic()
        while True:
            time.sleep(0.25)
            if time.monotonic() - last_heartbeat >= 15:
                try:
                    self._write_sse("heartbeat", {"status": "ok"})
                except OSError:
                    return
                last_heartbeat = time.monotonic()
            current_stamp = self.server.bell_event_stamp()
            if current_stamp == previous_stamp:
                continue
            previous_stamp = current_stamp
            try:
                self._write_sse("bell", self.server.latest_bell_event_payload())
            except OSError:
                return

    def _write_sse(self, event: str, payload: dict[str, Any]) -> None:
        body = (
            f"event: {event}\n"
            + "data: "
            + json.dumps(payload, ensure_ascii=False, sort_keys=True)
            + "\n\n"
        ).encode("utf-8")
        self.wfile.write(body)
        self.wfile.flush()

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length", "0"))
        raw_body = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(raw_body or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("invalid JSON body") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _send_text(self, text: str, *, content_type: str) -> None:
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict[str, Any], *, status_code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status_code)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def _required_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must not be empty")
    return value.strip()


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
    .recommendation-main {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
    }
    .llm-action {
      margin-top: 8px;
      color: var(--muted);
      font-size: 13px;
      overflow-wrap: anywhere;
    }
    .llm-action.decision-request {
      border: 1px solid #fecdca;
      border-left: 4px solid var(--attention);
      border-radius: 6px;
      background: #fffbfa;
      color: #7a271a;
      padding: 8px;
    }
    .decision-title {
      color: var(--text);
      font-weight: 700;
      margin-bottom: 4px;
    }
    .decision-line {
      margin-top: 2px;
    }
    .decision-list {
      margin-bottom: 18px;
      border: 1px solid #fecdca;
      border-left: 4px solid var(--attention);
      border-radius: 6px;
      background: #fffbfa;
      padding: 12px 14px;
      font-size: 14px;
    }
    .notification-list {
      margin-bottom: 18px;
      border: 1px solid #b2ddff;
      border-left: 4px solid var(--working);
      border-radius: 6px;
      background: #f5fbff;
      padding: 12px 14px;
      font-size: 14px;
    }
    .notification-list-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      font-weight: 700;
    }
    .notification-list-body {
      display: grid;
      gap: 8px;
      margin-top: 8px;
    }
    .notification-list-item {
      color: #1849a9;
      overflow-wrap: anywhere;
    }
    .notification-title-line {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      align-items: center;
      color: var(--text);
      font-weight: 700;
    }
    .notification-source {
      margin-top: 2px;
      color: var(--muted);
      font-size: 12px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    .decision-list-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      font-weight: 700;
    }
    .decision-list-body {
      display: grid;
      gap: 8px;
      margin-top: 8px;
    }
    .decision-list-item {
      color: #7a271a;
      overflow-wrap: anywhere;
    }
    .decision-answer-form {
      display: grid;
      gap: 8px;
      margin-top: 8px;
    }
    .decision-answer-form textarea {
      width: 100%;
      min-height: 72px;
      resize: vertical;
      border: 1px solid #fecdca;
      border-radius: 6px;
      padding: 8px;
      color: var(--text);
      font: inherit;
      line-height: 1.4;
    }
    .decision-answer-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }
    .decision-answer-message {
      color: var(--muted);
      font-size: 12px;
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
    .evidence,
    .path,
    .protocol-card,
    .managed-details,
    .command {
      color: var(--muted);
      font-size: 13px;
      overflow-wrap: anywhere;
    }
    .evidence {
      margin-top: 2px;
      color: #475467;
    }
    .source-line {
      margin-top: 2px;
      color: #344054;
    }
    .command {
      margin-top: 8px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    .protocol-card {
      margin-top: 8px;
      border: 1px solid #fedf89;
      border-left: 4px solid #dc6803;
      border-radius: 6px;
      background: #fffbeb;
      padding: 8px;
    }
    .protocol-title {
      color: var(--text);
      font-weight: 700;
      margin-bottom: 4px;
    }
    .protocol-line {
      margin-top: 2px;
    }
    .managed-details {
      margin-top: 8px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f8fafc;
      padding: 8px;
    }
    .managed-details-title {
      color: var(--text);
      font-weight: 700;
      margin-bottom: 4px;
    }
    .managed-line {
      margin-top: 2px;
    }
    .terminal-excerpt {
      margin: 6px 0 0;
      max-height: 120px;
      overflow: auto;
      white-space: pre-wrap;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      color: #344054;
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
    button[data-action="send"] {
      border-color: #b2ddff;
      color: var(--working);
    }
    button.suggested-action {
      border-color: #175cd3;
      background: #eff8ff;
      box-shadow: 0 0 0 2px rgba(23, 92, 211, 0.14);
      font-weight: 700;
    }
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
    <div class="recommendation">
      <div class="recommendation-main">
        <div id="recommendation">读取中</div>
        <button id="llm-action-button" type="button">模型建议</button>
      </div>
      <div class="llm-action" id="llm-action-result">未请求模型建议</div>
    </div>
    <div class="notification-list" id="notification-list">
      <div class="notification-list-head">
        <span>通知列表</span>
        <span class="count" id="notification-count">0</span>
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
    let latestLlmAction = null;
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
      const copyResume = document.createElement("button");
      copyResume.type = "button";
      copyResume.textContent = "复制 resume";
      copyResume.addEventListener("click", () => copyResumeCommand(item, copyResume));
      actions.append(copyResume);
      for (const command of item.control_commands || []) {
        const copyCommand = document.createElement("button");
        copyCommand.type = "button";
        copyCommand.textContent = copyControlLabel(command);
        copyCommand.addEventListener("click", () => copyControlCommand(command, copyCommand));
        actions.append(copyCommand);
        if (command.kind === "send_status" || command.kind === "send_continue") {
          const sendButton = document.createElement("button");
          sendButton.type = "button";
          sendButton.dataset.action = "send";
          sendButton.dataset.commandKind = command.kind;
          sendButton.dataset.laneName = item.name || "";
          sendButton.textContent = command.kind === "send_status" ? "请求状态" : "继续";
          sendButton.addEventListener("click", () => sendManagedCommand(item, command, sendButton));
          actions.append(sendButton);
        }
      }
      lane.append(actions);
      return lane;
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

    async function copyResumeCommand(item, button) {
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
      const unread = counts && Number.isInteger(counts.unread)
        ? counts.unread
        : notifications.filter((item) => item.unread).length;
      count.textContent = unread + "/" + notifications.length;
      list.replaceChildren();
      if (notifications.length === 0) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = "暂无";
        list.append(empty);
        return;
      }
      for (const notification of notifications) {
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
        source.textContent = "source_ref: " + text(JSON.stringify(notification.source_ref || {}));
        item.append(source);
        list.append(item);
      }
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
      document.getElementById("generated-at").textContent = payload.generated_at;
      document.getElementById("recommendation").textContent = payload.recommendation.label;
      renderNotifications(payload.notifications || [], payload.notification_counts || {});
      renderDecisionRequests(payload.decision_requests || []);
      for (const key of groups) renderGroup(key, payload.groups[key] || []);
      document.getElementById("refresh-state").textContent = "最近刷新 " + new Date().toLocaleTimeString();
    }

    document.getElementById("llm-action-button").addEventListener("click", (event) => {
      requestLlmAction(event.currentTarget);
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
  </script>
</body>
</html>
"""
