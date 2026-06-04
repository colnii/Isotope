"""Run and approval route handlers for the in-process HTTP facade."""

from __future__ import annotations

from typing import Any

from ...platform.errors import IsotopeError
from .types import HttpResponse


class HttpRunRouteMixin:
    """Handle session, run, approval, event, and agent-loop routes."""

    def _dispatch_run_route(
        self,
        method: str,
        parts: list[str],
        json_body: dict[str, Any] | None,
    ) -> HttpResponse | None:
        if method == "POST" and parts == ["sessions"]:
            return self._json(201, self.server.create_session())
        if method == "POST" and len(parts) == 3 and parts[0] == "sessions" and parts[2] == "runs":
            body = self._require_body(json_body, required_fields=("goal",))
            if parts[1] not in self.server._sessions:
                return self._isotope_error_response(
                    IsotopeError(
                        "session not found",
                        code="unknown_session",
                        category="not_found",
                        retryable=False,
                        http_status=404,
                        details={"session_id": parts[1]},
                    )
                )
            return self._json(
                201,
                self.server.create_run(parts[1], goal=body["goal"]),
            )
        if method == "POST" and len(parts) == 3 and parts[0] == "runs" and parts[2] == "input":
            body = self._require_body(json_body, required_fields=("text",))
            if not self._run_exists(parts[1]):
                return self._isotope_error_response(
                    IsotopeError(
                        "run not found",
                        code="unknown_run",
                        category="not_found",
                        retryable=False,
                        http_status=404,
                        details={"run_id": parts[1]},
                    )
                )
            requires_approval = False
            if isinstance(json_body, dict):
                requires_approval = json_body.get("requires_approval", False)
            result = self.server.submit_input(
                parts[1],
                text=body["text"],
                requires_approval=requires_approval,
            )
            return self._json(200, self._submit_result_to_dict(result))
        if (
            method == "POST"
            and len(parts) == 3
            and parts[0] == "runs"
            and parts[2] == "agent-loop-step"
        ):
            if not self._run_exists(parts[1]):
                return self._error(404, "not_found", "run not found")
            return self._json(200, self.server.run_agent_loop_step(parts[1], json_body))
        if (
            method == "POST"
            and len(parts) == 3
            and parts[0] == "runs"
            and parts[2] == "agent-loop-planner-step"
        ):
            if not self._run_exists(parts[1]):
                return self._error(404, "not_found", "run not found")
            return self._json(200, self.server.run_agent_loop_planner_step(parts[1], json_body))
        if (
            method == "POST"
            and len(parts) == 3
            and parts[0] == "runs"
            and parts[2] == "agent-loop-tick"
        ):
            if not self._run_exists(parts[1]):
                return self._error(404, "not_found", "run not found")
            body = self._agent_loop_tick_body(json_body)
            return self._json(
                200,
                self.server.run_agent_loop_tick(
                    parts[1],
                    body["planner_output"],
                    tick_budget=body["tick_budget"],
                    user_pause=body["user_pause"],
                ),
            )
        if (
            method == "POST"
            and len(parts) == 4
            and parts[0] == "runs"
            and parts[2] == "memory"
            and parts[3] == "query"
        ):
            if not self._run_exists(parts[1]):
                return self._error(404, "not_found", "run not found")
            body = json_body if isinstance(json_body, dict) else {}
            query = body.get("query")
            if not isinstance(query, str) or not query.strip():
                return self._error(400, "bad_request", "query must be a non-empty string")
            state = self.server.get_run_state(parts[1])
            result = self.server.memory_query_service.query(
                parts[1],
                query,
                grants=body.get("grants", {"memory": {"query": True}}),
                caller_context=body.get(
                    "caller_context",
                    {
                        "run_id": parts[1],
                        "session_id": state.session_id,
                        "caller": "http_api",
                        "purpose": "memory_query",
                    },
                ),
                controlled_expand=bool(body.get("controlled_expand", False)),
                scope=body.get("scope"),
                session_id=state.session_id,
                limit=body.get("limit", 20),
            )
            return self._json(200, result)
        if method == "GET" and len(parts) == 3 and parts[0] == "runs" and parts[2] == "approvals":
            if not self._run_exists(parts[1]):
                return self._error(404, "not_found", "run not found")
            return self._json(
                200,
                {
                    "status": "ok",
                    "pending_approvals": self.server.get_pending_approvals(parts[1]),
                },
            )
        if method == "POST" and len(parts) == 3 and parts[0] == "runs" and parts[2] == "approvals":
            if not self._run_exists(parts[1]):
                return self._error(404, "not_found", "run not found")
            body = self._require_body(json_body, required_fields=("text",))
            result = self.server.submit_input(
                parts[1],
                text=body["text"],
                requires_approval=True,
            )
            return self._json(202, self._submit_result_to_dict(result))
        if (
            method == "GET"
            and len(parts) == 4
            and parts[0] == "runs"
            and parts[2] == "approvals"
        ):
            if not self._run_exists(parts[1]):
                return self._error(404, "not_found", "run not found")
            try:
                approval = self.server.get_approval(parts[1], parts[3])
            except ValueError as exc:
                if "unknown approval" in str(exc):
                    return self._error(404, "not_found", "approval not found")
                raise
            return self._json(200, {"status": "ok", "approval": approval})
        if (
            method == "POST"
            and len(parts) == 5
            and parts[0] == "runs"
            and parts[2] == "approvals"
            and parts[4] == "resolve"
        ):
            if not self._approval_known_for_run(parts[3], parts[1]):
                return self._error(404, "not_found", "approval not found")
            result = self.server.resolve_approval(parts[3], json_body)
            if result.get("run_state") is not None and result["run_state"].run_id != parts[1]:
                return self._error(404, "not_found", "approval not found")
            return self._json(200, self._submit_result_to_dict(result))
        if method == "GET" and len(parts) == 2 and parts[0] == "runs":
            if not self._run_exists(parts[1]):
                return self._error(404, "not_found", "run not found")
            return self._json(200, self._run_state_to_dict(self.server.get_run_state(parts[1])))
        if (
            method == "GET"
            and len(parts) == 3
            and parts[0] == "runs"
            and parts[2] == "agent-loop-control"
        ):
            if not self._run_exists(parts[1]):
                return self._error(404, "not_found", "run not found")
            return self._json(200, self.server.get_agent_loop_control(parts[1]))
        if (
            method == "GET"
            and len(parts) == 3
            and parts[0] == "runs"
            and parts[2] == "agent-loop-tick-policy"
        ):
            if not self._run_exists(parts[1]):
                return self._error(404, "not_found", "run not found")
            controls = self._agent_loop_tick_policy_controls(json_body)
            return self._json(200, self.server.get_agent_loop_tick_policy(parts[1], **controls))
        if method == "GET" and len(parts) == 3 and parts[0] == "runs" and parts[2] == "events":
            if not self._run_exists(parts[1]):
                return self._error(404, "not_found", "run not found")
            return self._json(200, [event.to_dict() for event in self.server.get_events(parts[1])])
        if (
            method == "GET"
            and len(parts) == 4
            and parts[0] == "runs"
            and parts[2] == "events"
            and parts[3] == "stream"
        ):
            if not self._run_exists(parts[1]):
                return self._error(404, "not_found", "run not found")
            return self._json(
                200,
                {
                    "status": "ok",
                    "stream": [event.to_dict() for event in self.server.get_events(parts[1])],
                },
            )
        return None
