"""LLM route handlers for the in-process HTTP facade."""

from __future__ import annotations

from typing import Any

from ...platform.errors import IsotopeError
from .types import HttpResponse


class HttpLlmRouteMixin:
    """Handle Codex task and product-chat LLM routes."""

    def _dispatch_llm_route(
        self,
        method: str,
        parts: list[str],
        json_body: dict[str, Any] | None,
    ) -> HttpResponse | None:
        if method == "POST" and len(parts) == 3 and parts[0] == "runs" and parts[2] == "codex-tasks":
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
            body = self._require_body(json_body, required_fields=("prompt",))
            intent = {
                "action": "delegate_agent_task",
                "tool": "codex_task",
                "prompt": body["prompt"],
                "summary": self._optional_summary(json_body),
            }
            result = self.server.submit_action(
                parts[1],
                intent,
                requires_approval=True,
                complete_run=self._optional_complete_run(json_body),
            )
            status_code = 202 if result["status"] == "pending_user_approval" else 200
            return self._json(status_code, self._submit_result_to_dict(result))
        if (
            method == "POST"
            and len(parts) == 4
            and parts[0] == "runs"
            and parts[2] == "llm"
            and parts[3] == "tool-calls"
        ):
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
            if self.llm_tool_call_provider is None:
                return self._error(
                    501,
                    "not_enabled",
                    "llm_provider_tool_call is not enabled",
                    capability="llm_provider_tool_call",
                )
            body = self._require_llm_provider_body(json_body)
            from ...llm.provider import submit_llm_tool_call

            result = submit_llm_tool_call(
                self,
                parts[1],
                self.llm_tool_call_provider,
                body["messages"],
                max_tokens=body["max_tokens"],
                tool_names=self.llm_tool_names,
                complete_run=body["complete_run"],
            )
            status_code = 202 if result["status"] == "pending_user_approval" else 200
            return self._json(status_code, self._llm_provider_result_to_dict(result))
        if (
            method == "POST"
            and len(parts) == 4
            and parts[0] == "runs"
            and parts[2] == "llm"
            and parts[3] == "tool-result-followups"
        ):
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
            if self.llm_tool_call_provider is None:
                return self._error(
                    501,
                    "not_enabled",
                    "llm_provider_tool_result_followup is not enabled",
                    capability="llm_provider_tool_result_followup",
                )
            body = self._require_llm_tool_result_followup_body(json_body)
            from ...llm.provider import submit_llm_tool_result_followup

            result = submit_llm_tool_result_followup(
                self,
                parts[1],
                self.llm_tool_call_provider,
                body["messages"],
                body["llm_result"],
                body["tool_execution_result"],
                max_tokens=body["max_tokens"],
                tool_names=self.llm_tool_names,
                complete_run=body["complete_run"],
            )
            status_code = 202 if result["status"] == "pending_user_approval" else 200
            return self._json(status_code, self._llm_provider_result_to_dict(result))
        if (
            method == "POST"
            and len(parts) == 4
            and parts[0] == "runs"
            and parts[2] == "llm"
            and parts[3] == "chat-turns"
        ):
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
            if self.llm_tool_call_provider is None:
                return self._error(
                    501,
                    "not_enabled",
                    "llm_product_chat_route is not enabled",
                    capability="llm_product_chat_route",
                )
            body = self._require_llm_product_chat_body(json_body)
            from ...llm.provider import submit_llm_chat_turn

            result = submit_llm_chat_turn(
                self,
                parts[1],
                self.llm_tool_call_provider,
                body["messages"],
                body.get("llm_result"),
                body.get("tool_execution_result"),
                max_tokens=body["max_tokens"],
                tool_names=self.llm_tool_names,
                complete_run=body["complete_run"],
            )
            result["turn_kind"] = body["turn_kind"]
            status_code = 202 if result["status"] == "pending_user_approval" else 200
            return self._json(status_code, self._llm_product_chat_result_to_dict(result))
        return None
