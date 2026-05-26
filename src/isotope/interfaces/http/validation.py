"""Request validation helpers for the in-process HTTP facade."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ...platform.errors import IsotopeError


class HttpValidationMixin:
    """Validate request bodies and lightweight route preconditions."""

    def _agent_loop_tick_policy_controls(self, json_body: dict[str, Any] | None) -> dict[str, Any]:
        if json_body is None:
            return {}
        if not isinstance(json_body, dict):
            raise ValueError("request body must be an object")
        allowed = {"tick_budget", "user_pause"}
        unknown = sorted(set(json_body) - allowed)
        if unknown:
            raise ValueError(f"unsupported agent loop tick policy fields: {', '.join(unknown)}")
        return {
            key: deepcopy(value)
            for key, value in json_body.items()
            if key in allowed
        }

    def _agent_loop_tick_body(self, json_body: dict[str, Any] | None) -> dict[str, Any]:
        if json_body is None:
            json_body = {}
        if not isinstance(json_body, dict):
            raise ValueError("request body must be an object")
        allowed = {"planner_output", "tick_budget", "user_pause"}
        unknown = sorted(set(json_body) - allowed)
        if unknown:
            raise ValueError(f"unsupported agent loop tick fields: {', '.join(unknown)}")
        return {
            "planner_output": deepcopy(json_body.get("planner_output")),
            "tick_budget": deepcopy(json_body.get("tick_budget")),
            "user_pause": deepcopy(json_body.get("user_pause")),
        }

    def _search_options(self, body: dict[str, Any]) -> dict[str, Any]:
        result_types = body.get("types")
        if result_types is not None:
            if not isinstance(result_types, list) or not all(
                isinstance(item, str) for item in result_types
            ):
                raise ValueError("types must be a list of strings")
            result_types = tuple(result_types)
        limit = body.get("limit")
        return {"result_types": result_types, "limit": limit}

    def _workbench_options(self, body: dict[str, Any] | None) -> dict[str, Any]:
        if body is None:
            body = {}
        if not isinstance(body, dict):
            raise ValueError("request body must be an object")
        query = body.get("query")
        if query is not None and not isinstance(query, str):
            raise ValueError("query must be a string")
        search_options = self._search_options(body)
        return {
            "query": query,
            "search_types": search_options["result_types"],
            "search_limit": search_options["limit"],
        }

    def _workbench_ask_options(self, body: dict[str, Any] | None) -> dict[str, Any]:
        validated = self._require_body(body, required_fields=("question",))
        assert body is not None
        search_limit = body.get("limit", 5)
        if search_limit is not None and (
            not isinstance(search_limit, int) or search_limit < 1
        ):
            raise IsotopeError(
                "limit must be a positive integer",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "limit"},
            )
        max_tokens = body.get("max_tokens", 512)
        if not isinstance(max_tokens, int) or max_tokens <= 0:
            raise IsotopeError(
                "max_tokens must be a positive integer",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "max_tokens"},
            )
        return {
            "question": validated["question"],
            "search_limit": search_limit,
            "max_tokens": max_tokens,
        }


    def _validate_llm_tool_names(self, tool_names: tuple[str, ...]) -> tuple[str, ...]:
        if not isinstance(tool_names, tuple) or not tool_names:
            raise ValueError("llm_tool_names must be a non-empty tuple")
        cleaned: list[str] = []
        for index, tool_name in enumerate(tool_names):
            if not isinstance(tool_name, str) or not tool_name:
                raise ValueError(f"llm_tool_names[{index}] must be a non-empty string")
            cleaned.append(tool_name)
        return tuple(cleaned)

    def _require_body(self, body: Any, required_fields: tuple[str, ...]) -> dict[str, str]:
        if not isinstance(body, dict):
            raise IsotopeError(
                "request body must be a JSON object",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "body"},
            )
        validated: dict[str, str] = {}
        for field in required_fields:
            value = body.get(field)
            if not isinstance(value, str) or not value:
                raise IsotopeError(
                    f"missing required request field: {field}",
                    code="invalid_request",
                    category="validation",
                    retryable=False,
                    http_status=400,
                    details={"field": field},
                )
            validated[field] = value
        return validated

    def _require_llm_provider_body(self, body: Any) -> dict[str, Any]:
        if not isinstance(body, dict):
            raise IsotopeError(
                "request body must be a JSON object",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "body"},
            )
        messages = self._require_llm_messages(body.get("messages"))
        max_tokens = body.get("max_tokens", 512)
        if not isinstance(max_tokens, int) or max_tokens <= 0:
            raise IsotopeError(
                "max_tokens must be a positive integer",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "max_tokens"},
            )
        complete_run = self._optional_complete_run(body)
        return {"messages": messages, "max_tokens": max_tokens, "complete_run": complete_run}

    def _require_llm_tool_result_followup_body(self, body: Any) -> dict[str, Any]:
        provider_body = self._require_llm_provider_body(body)
        if not isinstance(body, dict):
            raise IsotopeError(
                "request body must be a JSON object",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "body"},
            )
        llm_result = self._require_object_field(body, "llm_result")
        tool_execution_result = self._require_object_field(body, "tool_execution_result")
        return {
            **provider_body,
            "llm_result": llm_result,
            "tool_execution_result": tool_execution_result,
        }

    def _require_llm_product_chat_body(self, body: Any) -> dict[str, Any]:
        provider_body = self._require_llm_provider_body(body)
        if not isinstance(body, dict):
            raise IsotopeError(
                "request body must be a JSON object",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "body"},
            )
        max_tool_steps = body.get("max_tool_steps", 1)
        if not isinstance(max_tool_steps, int) or max_tool_steps != 1:
            raise IsotopeError(
                "max_tool_steps must be exactly 1 for product chat route first slice",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "max_tool_steps"},
            )
        has_llm_result = "llm_result" in body
        has_tool_execution_result = "tool_execution_result" in body
        if has_llm_result != has_tool_execution_result:
            raise IsotopeError(
                "llm_result and tool_execution_result must be provided together",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "tool_result_context"},
            )
        if has_llm_result:
            return {
                **provider_body,
                "turn_kind": "tool_result_followup",
                "llm_result": self._require_object_field(body, "llm_result"),
                "tool_execution_result": self._require_object_field(body, "tool_execution_result"),
            }
        return {**provider_body, "turn_kind": "initial"}

    def _require_object_field(self, body: dict[str, Any], field: str) -> dict[str, Any]:
        value = body.get(field)
        if not isinstance(value, dict) or not value:
            raise IsotopeError(
                f"{field} must be a non-empty JSON object",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": field},
            )
        return deepcopy(value)

    def _require_llm_messages(self, messages: Any) -> list[dict[str, str]]:
        if not isinstance(messages, list) or not messages:
            raise IsotopeError(
                "messages must be a non-empty list",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "messages"},
            )
        validated: list[dict[str, str]] = []
        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                raise IsotopeError(
                    "message must be a JSON object",
                    code="invalid_request",
                    category="validation",
                    retryable=False,
                    http_status=400,
                    details={"field": f"messages[{index}]"},
                )
            role = message.get("role")
            content = message.get("content")
            if role not in {"system", "user", "assistant", "tool"}:
                raise IsotopeError(
                    "message role must be system, user, assistant, or tool",
                    code="invalid_request",
                    category="validation",
                    retryable=False,
                    http_status=400,
                    details={"field": f"messages[{index}].role"},
                )
            if not isinstance(content, str) or not content.strip():
                raise IsotopeError(
                    "message content must be a non-empty string",
                    code="invalid_request",
                    category="validation",
                    retryable=False,
                    http_status=400,
                    details={"field": f"messages[{index}].content"},
                )
            validated.append({"role": role, "content": content})
        return validated

    def _optional_summary(self, body: Any) -> str:
        if not isinstance(body, dict):
            raise IsotopeError(
                "request body must be a JSON object",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "body"},
            )
        requires_approval = body.get("requires_approval", True)
        if requires_approval is not True:
            raise IsotopeError(
                "codex_task route always requires approval",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "requires_approval"},
            )
        summary = body.get("summary", "HTTP Codex task")
        if not isinstance(summary, str) or not summary:
            raise IsotopeError(
                "summary must be a non-empty string",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "summary"},
            )
        return summary

    def _optional_complete_run(self, body: Any) -> bool:
        if not isinstance(body, dict):
            raise IsotopeError(
                "request body must be a JSON object",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "body"},
            )
        complete_run = body.get("complete_run", True)
        if not isinstance(complete_run, bool):
            raise IsotopeError(
                "complete_run must be a boolean",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "complete_run"},
            )
        return complete_run

    def _run_exists(self, run_id: str) -> bool:
        return run_id in self.server._runs or self.server.event_store.event_path(run_id).exists()

    def _approval_known_for_run(self, approval_id: str, run_id: str) -> bool:
        pending = self.server._pending_approvals.get(approval_id)
        if pending is not None:
            return pending.get("run_id") == run_id
        resolved = self.server._resolved_approvals.get(approval_id)
        if resolved is None:
            return False
        state = resolved.get("run_state")
        return getattr(state, "run_id", None) == run_id
