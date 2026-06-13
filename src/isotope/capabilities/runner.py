"""Thin capability runner shell over the public capability catalog.

This module intentionally stays small: catalog metadata remains the source of
truth, and execution is limited to deterministic in-process demo scenarios.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .artifact_outputs import (
    ARTIFACT_CHANGED_FILES_CAPABILITY,
    ARTIFACT_DIFF_RESULT_CAPABILITY,
    is_artifact_output_capability,
    run_artifact_changed_files,
    run_artifact_diff_result,
    validate_artifact_output_inputs,
)
from .catalog import CapabilityCatalog
from .coding import (
    CODING_TASK_PLAN_CAPABILITY,
    is_coding_capability,
    run_coding_task_plan,
    validate_coding_inputs,
)
from .coding_apply import (
    CODING_TASK_APPLY_REVIEWED_DIFF_CAPABILITY,
    is_coding_apply_capability,
    run_coding_task_apply_reviewed_diff,
    validate_coding_apply_inputs,
)
from .coding_execute import (
    CODING_TASK_EXECUTE_CAPABILITY,
    is_coding_execute_capability,
    run_coding_task_execute,
    validate_coding_execute_inputs,
)
from .coding_run import (
    CODING_TASK_RUN_CAPABILITY,
    is_coding_run_capability,
    reject_direct_coding_task_run,
    validate_coding_run_inputs,
)
from .code_access import (
    CODE_READ_CAPABILITY,
    CODE_SEARCH_CAPABILITY,
    is_code_access_capability,
    run_code_read,
    run_code_search,
    validate_code_access_inputs,
)
from .code_edit import (
    CODE_APPLY_PATCH_CAPABILITY,
    is_code_edit_capability,
    run_code_apply_patch,
    validate_code_edit_inputs,
)
from .extensions import (
    is_extension_capability,
    run_extension_capability,
    validate_extension_inputs,
)
from .memory import (
    MEMORY_PROMOTION_PREVIEW_CAPABILITY,
    MEMORY_QUERY_CAPABILITY,
    MEMORY_RECALL_CAPABILITY,
    is_memory_projection_capability,
    run_memory_promotion_preview,
    run_memory_query,
    run_memory_recall,
    validate_memory_projection_inputs,
)
from .read import (
    FILE_READ_CAPABILITY,
    is_file_read_capability,
    run_file_read,
    validate_file_read_inputs,
)
from .research import (
    RESEARCH_PROMOTE_CAPABILITY,
    RESEARCH_RECALL_CAPABILITY,
    RESEARCH_SEARCH_CAPABILITY,
    is_research_capability,
    run_research_promote,
    run_research_recall,
    run_research_search,
    validate_research_inputs,
)
from .screen import (
    SCREEN_CONTROL_CAPABILITY,
    SCREEN_OBSERVE_CAPABILITY,
    SCREEN_REPORT_CAPABILITY,
    is_screen_capability,
    is_screen_projection_capability,
    run_screen_control,
    run_screen_observe,
    run_screen_report,
    validate_screen_inputs,
)
from .self_repair import (
    ISOTOPE_SELF_REPAIR_CAPABILITY,
    is_self_repair_capability,
    run_isotope_self_repair,
    validate_self_repair_inputs,
)
from .supervisor import (
    SUPERVISOR_CODEX_OPERATION_CAPABILITY,
    SUPERVISOR_INTEGRATION_REVIEW_CAPABILITY,
    SUPERVISOR_PROJECT_STATUS_CAPABILITY,
    SUPERVISOR_REQUEST_CONTEXT_CAPABILITY,
    SUPERVISOR_WORKER_REVIEW_CAPABILITY,
    is_supervisor_projection_capability,
    normalize_supervisor_state_root_inputs,
    run_supervisor_codex_operation,
    run_supervisor_integration_review,
    run_supervisor_project_status,
    run_supervisor_request_context,
    run_supervisor_worker_review,
    validate_supervisor_projection_inputs,
)
from .supervisor_goal_plan import (
    SUPERVISOR_GOAL_PLAN_CAPABILITY,
    is_supervisor_goal_plan_capability,
    run_supervisor_goal_plan,
    validate_supervisor_goal_plan_inputs,
)
from .testing import (
    TEST_RUN_CAPABILITY,
    is_test_run_capability,
    run_test_run,
    validate_test_run_inputs,
)
from .tools.terminal import (
    TERMINAL_EXEC_CAPABILITY,
    is_terminal_exec_capability,
    run_terminal_exec,
    validate_terminal_exec_inputs,
)
from .vcs import (
    VCS_DIFF_CAPABILITY,
    VCS_STATUS_CAPABILITY,
    is_vcs_capability,
    run_vcs_diff,
    run_vcs_status,
    validate_vcs_inputs,
)
from .workspace import (
    WORKSPACE_ISOLATED_RW_CAPABILITY,
    WORKSPACE_LEASE_CREATE_CAPABILITY,
    WORKSPACE_MATERIALIZE_CAPABILITY,
    is_workspace_capability,
    run_workspace_isolated_rw,
    run_workspace_lease_create,
    run_workspace_materialize,
    validate_workspace_inputs,
)
from .workspace_files import (
    WORKSPACE_CHANGED_FILES_CAPABILITY,
    WORKSPACE_RELEASE_CAPABILITY,
    is_workspace_file_capability,
    run_workspace_changed_files,
    run_workspace_release,
    validate_workspace_file_inputs,
)
from ..demo import run_demo
from ..platform.schemas.input_contract import (
    contract_properties,
    contract_value_violation,
    missing_required_input_keys,
    required_contract_keys,
    unexpected_contract_keys,
)


_CAPABILITY_SCENARIOS = {
    "approval.tool.runner": "approval-tool-runner",
    "artifact.review": "artifact-review",
    "external.snapshot.review": "external-snapshot-review",
}

_SUMMARY_KEYS = (
    "run_status",
    "memory_status",
    "event_count",
    "http_api_ok",
    "approval_ok",
    "artifact_content_policy_ok",
    "http_full_content_route_status",
    "external_ingestion_route_status",
    "external_observation_count",
    "conflict_diagnostic_count",
)


class CapabilityRunner:
    def __init__(self, *, catalog: CapabilityCatalog | None = None):
        if catalog is None:
            catalog = CapabilityCatalog.default()
        if not isinstance(catalog, CapabilityCatalog):
            raise ValueError("catalog must be a CapabilityCatalog")
        self._catalog = catalog

    def list_capabilities(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self._catalog.list_capabilities(**kwargs)

    def search_capabilities(
        self,
        *,
        query: str = "",
        shelf: str | None = None,
        include_diagnostics: bool = False,
        include_experimental: bool = False,
        env: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(query, str):
            raise ValueError("query must be a string")
        normalized_query = query.strip().lower()
        capabilities = []
        for capability in self._catalog.list_capabilities(
            shelf=shelf,
            include_diagnostics=include_diagnostics,
            include_experimental=include_experimental,
        ):
            haystack = " ".join(
                [
                    capability["capability_id"],
                    capability["title"],
                    capability["description"],
                    capability["shelf"],
                    *capability["domain_tags"],
                ]
            ).lower()
            if normalized_query and normalized_query not in haystack:
                continue
            capabilities.append(
                {
                    "capability_id": capability["capability_id"],
                    "title": capability["title"],
                    "description": capability["description"],
                    "shelf": capability["shelf"],
                    "domain_tags": list(capability["domain_tags"]),
                    "readiness": self._catalog.get_capability_status(
                        capability["capability_id"], env=env
                    ),
                }
            )
        return {
            "kind": "capability_search_result",
            "query": query,
            "capabilities": capabilities,
        }

    def describe_capability(self, capability_id: str) -> dict[str, Any]:
        return dict(self._lookup_capability(capability_id))

    def get_capability_status(
        self, capability_id: str, *, env: Mapping[str, str] | None = None
    ) -> dict[str, Any]:
        return self._catalog.get_capability_status(capability_id, env=env)

    def plan_capability_run(
        self,
        capability_id: str,
        *,
        inputs: Mapping[str, Any] | None = None,
        env: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            capability = self._lookup_capability(capability_id)
        except ValueError:
            return _unknown_launch_plan(capability_id)

        input_mapping = _input_mapping(inputs)
        if (
            is_supervisor_projection_capability(capability_id)
            or is_supervisor_goal_plan_capability(capability_id)
        ):
            input_mapping = normalize_supervisor_state_root_inputs(input_mapping)
        status = self._catalog.get_capability_status(capability_id, env=env)
        scenario = _CAPABILITY_SCENARIOS.get(capability_id)
        required_inputs = _required_inputs(capability)
        missing_inputs = _missing_inputs(required_inputs, input_mapping)
        validate_memory_projection_inputs(
            capability_id=capability_id,
            inputs=input_mapping,
            missing_inputs=missing_inputs,
        )
        validate_screen_inputs(
            capability_id=capability_id,
            inputs=input_mapping,
            missing_inputs=missing_inputs,
        )
        validate_research_inputs(
            capability_id=capability_id,
            inputs=input_mapping,
            missing_inputs=missing_inputs,
        )
        validate_supervisor_projection_inputs(
            capability_id=capability_id,
            inputs=input_mapping,
            missing_inputs=missing_inputs,
        )
        validate_supervisor_goal_plan_inputs(
            capability_id=capability_id,
            inputs=input_mapping,
            missing_inputs=missing_inputs,
        )
        validate_coding_inputs(
            capability_id=capability_id,
            inputs=input_mapping,
            missing_inputs=missing_inputs,
        )
        validate_coding_execute_inputs(
            capability_id=capability_id,
            inputs=input_mapping,
            missing_inputs=missing_inputs,
        )
        validate_coding_apply_inputs(
            capability_id=capability_id,
            inputs=input_mapping,
            missing_inputs=missing_inputs,
        )
        if is_coding_run_capability(capability_id) and not missing_inputs:
            input_mapping = validate_coding_run_inputs(input_mapping)
        validate_code_access_inputs(
            capability_id=capability_id,
            inputs=input_mapping,
            missing_inputs=missing_inputs,
        )
        validate_file_read_inputs(
            capability_id=capability_id,
            inputs=input_mapping,
            missing_inputs=missing_inputs,
        )
        validate_code_edit_inputs(
            capability_id=capability_id,
            inputs=input_mapping,
            missing_inputs=missing_inputs,
        )
        validate_test_run_inputs(
            capability_id=capability_id,
            inputs=input_mapping,
            missing_inputs=missing_inputs,
        )
        validate_terminal_exec_inputs(
            capability_id=capability_id,
            inputs=input_mapping,
            missing_inputs=missing_inputs,
        )
        validate_vcs_inputs(
            capability_id=capability_id,
            inputs=input_mapping,
            missing_inputs=missing_inputs,
        )
        validate_workspace_inputs(
            capability_id=capability_id,
            inputs=input_mapping,
            missing_inputs=missing_inputs,
        )
        validate_workspace_file_inputs(
            capability_id=capability_id,
            inputs=input_mapping,
            missing_inputs=missing_inputs,
        )
        validate_artifact_output_inputs(
            capability_id=capability_id,
            inputs=input_mapping,
            missing_inputs=missing_inputs,
        )
        validate_self_repair_inputs(
            capability_id=capability_id,
            inputs=input_mapping,
            missing_inputs=missing_inputs,
        )
        validate_extension_inputs(
            capability_id=capability_id,
            inputs=input_mapping,
            missing_inputs=missing_inputs,
        )
        _validate_inputs_against_contract(capability, inputs=input_mapping)
        runner_kind = _runner_kind(capability, scenario=scenario)
        blocking_reasons: list[str] = []
        can_launch = False
        launch_status = "launchable"

        if not status["ready"]:
            launch_status = "not_ready"
            if status["status"] == "missing_configuration":
                blocking_reasons.append("missing_configuration")
            else:
                blocking_reasons.append(status["status"])
        elif capability["shelf"] in {"diagnostic", "experimental"}:
            launch_status = "not_allowlisted"
            blocking_reasons.append("not_allowlisted")
        elif missing_inputs:
            launch_status = "missing_inputs"
            blocking_reasons.append("missing_inputs")
        elif (
            scenario is None
            and not is_memory_projection_capability(capability_id)
            and not is_research_capability(capability_id)
            and not is_screen_capability(capability_id)
            and not is_supervisor_projection_capability(capability_id)
            and not is_supervisor_goal_plan_capability(capability_id)
            and not is_coding_capability(capability_id)
            and not is_coding_apply_capability(capability_id)
            and not is_coding_execute_capability(capability_id)
            and not is_coding_run_capability(capability_id)
            and not is_code_access_capability(capability_id)
            and not is_file_read_capability(capability_id)
            and not is_code_edit_capability(capability_id)
            and not is_test_run_capability(capability_id)
            and not is_terminal_exec_capability(capability_id)
            and not is_vcs_capability(capability_id)
            and not is_workspace_capability(capability_id)
            and not is_workspace_file_capability(capability_id)
            and not is_artifact_output_capability(capability_id)
            and not is_self_repair_capability(capability_id)
            and not is_extension_capability(capability_id)
        ):
            launch_status = "not_allowlisted"
            blocking_reasons.append("not_allowlisted")
        else:
            can_launch = True

        if not can_launch and runner_kind == "deterministic_demo" and scenario is None:
            runner_kind = "queued"

        return {
            "kind": "capability_launch_plan",
            "capability_id": capability_id,
            "capability_title": capability["title"],
            "can_launch": can_launch,
            "status": launch_status,
            "runner_kind": runner_kind,
            "scenario": scenario if can_launch else None,
            "blocking_reasons": blocking_reasons,
            "required_inputs": required_inputs,
            "missing_inputs": missing_inputs,
            "required_env": list(capability.get("required_env", [])),
            "missing_env": list(status.get("missing_env", [])),
            "network_required": bool(capability.get("network_required")),
            "provider": capability.get("provider"),
            "model": capability.get("model"),
            "shelf": capability["shelf"],
            "safety_boundaries": list(capability.get("safety_boundaries", [])),
            "output_policy": _output_policy(),
        }

    def run_capability(
        self,
        capability_id: str,
        *,
        root_path: Path | str | None = None,
        inputs: Mapping[str, Any] | None = None,
        env: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        capability = self._lookup_capability(capability_id)
        input_mapping = _input_mapping(inputs)
        if (
            is_supervisor_projection_capability(capability_id)
            or is_supervisor_goal_plan_capability(capability_id)
        ):
            input_mapping = normalize_supervisor_state_root_inputs(input_mapping)
        if (
            is_memory_projection_capability(capability_id)
            or is_research_capability(capability_id)
            or is_screen_capability(capability_id)
            or is_supervisor_projection_capability(capability_id)
            or is_supervisor_goal_plan_capability(capability_id)
            or is_coding_capability(capability_id)
            or is_coding_apply_capability(capability_id)
            or is_coding_execute_capability(capability_id)
            or is_coding_run_capability(capability_id)
            or is_code_access_capability(capability_id)
            or is_code_edit_capability(capability_id)
            or is_test_run_capability(capability_id)
            or is_terminal_exec_capability(capability_id)
            or is_vcs_capability(capability_id)
            or is_workspace_capability(capability_id)
            or is_workspace_file_capability(capability_id)
            or is_artifact_output_capability(capability_id)
            or is_self_repair_capability(capability_id)
            or is_extension_capability(capability_id)
        ):
            required_inputs = _required_inputs(capability)
            missing_inputs = _missing_inputs(required_inputs, input_mapping)
            validate_memory_projection_inputs(
                capability_id=capability_id,
                inputs=input_mapping,
                missing_inputs=missing_inputs,
            )
            validate_screen_inputs(
                capability_id=capability_id,
                inputs=input_mapping,
                missing_inputs=missing_inputs,
            )
            validate_research_inputs(
                capability_id=capability_id,
                inputs=input_mapping,
                missing_inputs=missing_inputs,
            )
            validate_supervisor_projection_inputs(
                capability_id=capability_id,
                inputs=input_mapping,
                missing_inputs=missing_inputs,
            )
            validate_supervisor_goal_plan_inputs(
                capability_id=capability_id,
                inputs=input_mapping,
                missing_inputs=missing_inputs,
            )
            validate_coding_inputs(
                capability_id=capability_id,
                inputs=input_mapping,
                missing_inputs=missing_inputs,
            )
            validate_coding_execute_inputs(
                capability_id=capability_id,
                inputs=input_mapping,
                missing_inputs=missing_inputs,
            )
            validate_coding_apply_inputs(
                capability_id=capability_id,
                inputs=input_mapping,
                missing_inputs=missing_inputs,
            )
            if is_coding_run_capability(capability_id):
                input_mapping = validate_coding_run_inputs(
                    input_mapping,
                    missing_inputs=missing_inputs,
                )
            validate_code_access_inputs(
                capability_id=capability_id,
                inputs=input_mapping,
                missing_inputs=missing_inputs,
            )
            validate_file_read_inputs(
                capability_id=capability_id,
                inputs=input_mapping,
                missing_inputs=missing_inputs,
            )
            validate_code_edit_inputs(
                capability_id=capability_id,
                inputs=input_mapping,
                missing_inputs=missing_inputs,
            )
            validate_test_run_inputs(
                capability_id=capability_id,
                inputs=input_mapping,
                missing_inputs=missing_inputs,
            )
            validate_terminal_exec_inputs(
                capability_id=capability_id,
                inputs=input_mapping,
                missing_inputs=missing_inputs,
            )
            validate_vcs_inputs(
                capability_id=capability_id,
                inputs=input_mapping,
                missing_inputs=missing_inputs,
            )
            validate_workspace_inputs(
                capability_id=capability_id,
                inputs=input_mapping,
                missing_inputs=missing_inputs,
            )
            validate_workspace_file_inputs(
                capability_id=capability_id,
                inputs=input_mapping,
                missing_inputs=missing_inputs,
            )
            validate_artifact_output_inputs(
                capability_id=capability_id,
                inputs=input_mapping,
                missing_inputs=missing_inputs,
            )
            validate_self_repair_inputs(
                capability_id=capability_id,
                inputs=input_mapping,
                missing_inputs=missing_inputs,
            )
            validate_extension_inputs(
                capability_id=capability_id,
                inputs=input_mapping,
                missing_inputs=missing_inputs,
            )
        _validate_inputs_against_contract(capability, inputs=input_mapping)
        shelf = capability["shelf"]
        if shelf in {"diagnostic", "experimental"}:
            raise PermissionError(f"{shelf} capability cannot run by default")

        status = self._catalog.get_capability_status(capability_id, env=env)
        if not status["ready"]:
            raise PermissionError(f"capability not ready: {status['status']}")

        if capability_id == MEMORY_QUERY_CAPABILITY:
            return run_memory_query(inputs=input_mapping)
        if capability_id == MEMORY_RECALL_CAPABILITY:
            return run_memory_recall(inputs=input_mapping)
        if capability_id == MEMORY_PROMOTION_PREVIEW_CAPABILITY:
            return run_memory_promotion_preview(inputs=input_mapping)
        if capability_id == RESEARCH_PROMOTE_CAPABILITY:
            return run_research_promote(inputs=input_mapping)
        if capability_id == RESEARCH_RECALL_CAPABILITY:
            return run_research_recall(inputs=input_mapping)
        if capability_id == RESEARCH_SEARCH_CAPABILITY:
            return run_research_search(inputs=input_mapping)
        if capability_id == SCREEN_CONTROL_CAPABILITY:
            return run_screen_control(root_path=root_path, inputs=input_mapping)
        if capability_id == SCREEN_OBSERVE_CAPABILITY:
            return run_screen_observe(root_path=root_path, inputs=input_mapping)
        if capability_id == SCREEN_REPORT_CAPABILITY:
            return run_screen_report(inputs=input_mapping)
        if capability_id == SUPERVISOR_CODEX_OPERATION_CAPABILITY:
            return run_supervisor_codex_operation(inputs=input_mapping)
        if capability_id == SUPERVISOR_REQUEST_CONTEXT_CAPABILITY:
            return run_supervisor_request_context(inputs=input_mapping)
        if capability_id == SUPERVISOR_INTEGRATION_REVIEW_CAPABILITY:
            return run_supervisor_integration_review(inputs=input_mapping)
        if capability_id == SUPERVISOR_PROJECT_STATUS_CAPABILITY:
            return run_supervisor_project_status(inputs=input_mapping)
        if capability_id == SUPERVISOR_WORKER_REVIEW_CAPABILITY:
            return run_supervisor_worker_review(inputs=input_mapping)
        if capability_id == SUPERVISOR_GOAL_PLAN_CAPABILITY:
            return run_supervisor_goal_plan(inputs=input_mapping)
        if capability_id == CODING_TASK_PLAN_CAPABILITY:
            return run_coding_task_plan(inputs=input_mapping)
        if capability_id == CODING_TASK_EXECUTE_CAPABILITY:
            return run_coding_task_execute(inputs=input_mapping)
        if capability_id == CODING_TASK_APPLY_REVIEWED_DIFF_CAPABILITY:
            return run_coding_task_apply_reviewed_diff(inputs=input_mapping)
        if capability_id == CODING_TASK_RUN_CAPABILITY:
            return reject_direct_coding_task_run()
        if capability_id == FILE_READ_CAPABILITY:
            return run_file_read(inputs=input_mapping)
        if capability_id == CODE_READ_CAPABILITY:
            return run_code_read(inputs=input_mapping)
        if capability_id == CODE_SEARCH_CAPABILITY:
            return run_code_search(inputs=input_mapping)
        if capability_id == CODE_APPLY_PATCH_CAPABILITY:
            return run_code_apply_patch(inputs=input_mapping)
        if capability_id == TEST_RUN_CAPABILITY:
            return run_test_run(inputs=input_mapping)
        if capability_id == TERMINAL_EXEC_CAPABILITY:
            return run_terminal_exec(inputs=input_mapping)
        if capability_id == VCS_STATUS_CAPABILITY:
            return run_vcs_status(inputs=input_mapping)
        if capability_id == VCS_DIFF_CAPABILITY:
            return run_vcs_diff(inputs=input_mapping)
        if capability_id == WORKSPACE_ISOLATED_RW_CAPABILITY:
            return run_workspace_isolated_rw(inputs=input_mapping)
        if capability_id == WORKSPACE_LEASE_CREATE_CAPABILITY:
            return run_workspace_lease_create(inputs=input_mapping)
        if capability_id == WORKSPACE_MATERIALIZE_CAPABILITY:
            return run_workspace_materialize(inputs=input_mapping)
        if capability_id == WORKSPACE_CHANGED_FILES_CAPABILITY:
            return run_workspace_changed_files(inputs=input_mapping)
        if capability_id == WORKSPACE_RELEASE_CAPABILITY:
            return run_workspace_release(inputs=input_mapping)
        if capability_id == ARTIFACT_CHANGED_FILES_CAPABILITY:
            return run_artifact_changed_files(inputs=input_mapping)
        if capability_id == ARTIFACT_DIFF_RESULT_CAPABILITY:
            return run_artifact_diff_result(inputs=input_mapping)
        if capability_id == ISOTOPE_SELF_REPAIR_CAPABILITY:
            return run_isotope_self_repair(inputs=input_mapping)
        if is_extension_capability(capability_id):
            return run_extension_capability(capability_id, inputs=input_mapping)

        try:
            scenario = _CAPABILITY_SCENARIOS[capability_id]
        except KeyError as exc:
            raise PermissionError(f"capability is not allowlisted: {capability_id}") from exc

        demo_result = run_demo(root_path=root_path, scenario=scenario)
        summary = {
            key: demo_result[key] for key in _SUMMARY_KEYS if key in demo_result
        }
        return {
            "kind": "capability_run_result",
            "capability_id": capability_id,
            "status": "completed",
            "scenario": scenario,
            "replay_ok": bool(demo_result.get("replay_ok")),
            "checkpoint_ok": bool(demo_result.get("checkpoint_ok")),
            "summary": summary,
        }

    def _lookup_capability(self, capability_id: str) -> dict[str, Any]:
        return self._catalog.describe_capability(capability_id)


def default_runner() -> CapabilityRunner:
    return CapabilityRunner()


def list_capabilities(**kwargs: Any) -> list[dict[str, Any]]:
    return default_runner().list_capabilities(**kwargs)


def describe_capability(capability_id: str) -> dict[str, Any]:
    return default_runner().describe_capability(capability_id)


def get_capability_status(capability_id: str, **kwargs: Any) -> dict[str, Any]:
    return default_runner().get_capability_status(capability_id, **kwargs)


def search_capabilities(**kwargs: Any) -> dict[str, Any]:
    return default_runner().search_capabilities(**kwargs)


def plan_capability_run(capability_id: str, **kwargs: Any) -> dict[str, Any]:
    return default_runner().plan_capability_run(capability_id, **kwargs)


def run_capability(capability_id: str, **kwargs: Any) -> dict[str, Any]:
    return default_runner().run_capability(capability_id, **kwargs)


def _input_mapping(inputs: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if inputs is None:
        return {}
    if not isinstance(inputs, Mapping):
        raise ValueError("inputs must be a mapping")
    return inputs


def _required_inputs(capability: Mapping[str, Any]) -> list[str]:
    return required_contract_keys(capability.get("input_contract", {}))


def _missing_inputs(
    required_inputs: list[str], inputs: Mapping[str, Any] | None
) -> list[str]:
    return missing_required_input_keys(inputs, required_inputs)


def _validate_inputs_against_contract(
    capability: Mapping[str, Any], *, inputs: Mapping[str, Any] | None
) -> None:
    if not inputs:
        return
    properties = contract_properties(capability.get("input_contract", {}))
    if not properties:
        return
    unexpected = unexpected_contract_keys(inputs, properties)
    if unexpected:
        raise ValueError(
            "capability inputs not allowed by input_contract: "
            + ", ".join(unexpected)
        )
    for name, value in inputs.items():
        schema = properties.get(name)
        if not isinstance(schema, Mapping):
            continue
        violation = contract_value_violation(value, schema)
        if violation == "type":
            expected_type = schema.get("type")
            raise ValueError(
                f"capability input {name} does not match input_contract type: "
                f"{expected_type}"
            )
        if violation == "enum":
            raise ValueError(
                f"capability input {name} is not allowed by input_contract enum"
            )


def _runner_kind(capability: Mapping[str, Any], *, scenario: str | None) -> str:
    if capability.get("network_required") or capability.get("provider"):
        return "provider_required"
    if scenario is not None:
        return "deterministic_demo"
    if is_memory_projection_capability(str(capability.get("capability_id", ""))):
        return "deterministic_projection"
    if is_research_capability(str(capability.get("capability_id", ""))):
        return "deterministic_local"
    if capability.get("capability_id") in {
        SCREEN_CONTROL_CAPABILITY,
        SCREEN_OBSERVE_CAPABILITY,
    }:
        return "deterministic_local"
    if is_screen_projection_capability(str(capability.get("capability_id", ""))):
        return "deterministic_projection"
    if is_supervisor_projection_capability(str(capability.get("capability_id", ""))):
        return "deterministic_projection"
    if is_supervisor_goal_plan_capability(str(capability.get("capability_id", ""))):
        return "supervisor_goal_plan"
    if is_coding_capability(str(capability.get("capability_id", ""))):
        return "native_coding_plan"
    if is_coding_execute_capability(str(capability.get("capability_id", ""))):
        return "deterministic_local"
    if is_coding_apply_capability(str(capability.get("capability_id", ""))):
        return "deterministic_local"
    if is_coding_run_capability(str(capability.get("capability_id", ""))):
        return "agent_loop_entrypoint"
    if is_code_access_capability(str(capability.get("capability_id", ""))):
        return "deterministic_projection"
    if is_code_edit_capability(str(capability.get("capability_id", ""))):
        return "deterministic_local"
    if is_test_run_capability(str(capability.get("capability_id", ""))):
        return "deterministic_local"
    if is_terminal_exec_capability(str(capability.get("capability_id", ""))):
        return "runtime_terminal"
    if is_vcs_capability(str(capability.get("capability_id", ""))):
        return "deterministic_projection"
    if capability.get("capability_id") == WORKSPACE_MATERIALIZE_CAPABILITY:
        return "deterministic_local"
    if is_workspace_capability(str(capability.get("capability_id", ""))):
        return "deterministic_action_handoff"
    if capability.get("capability_id") == WORKSPACE_CHANGED_FILES_CAPABILITY:
        return "deterministic_projection"
    if capability.get("capability_id") == WORKSPACE_RELEASE_CAPABILITY:
        return "deterministic_local"
    if is_artifact_output_capability(str(capability.get("capability_id", ""))):
        return "deterministic_local"
    if is_self_repair_capability(str(capability.get("capability_id", ""))):
        return "codex_assisted"
    if is_extension_capability(str(capability.get("capability_id", ""))):
        return "extension_bridge"
    return "queued"


def _output_policy() -> dict[str, bool]:
    return {
        "returns_full_content": False,
        "returns_artifact_refs": True,
        "public_result_metadata": True,
    }


def _unknown_launch_plan(capability_id: str) -> dict[str, Any]:
    return {
        "kind": "capability_launch_plan",
        "capability_id": capability_id,
        "capability_title": None,
        "can_launch": False,
        "status": "unknown",
        "runner_kind": "unknown",
        "scenario": None,
        "blocking_reasons": ["unknown_capability"],
        "required_inputs": [],
        "missing_inputs": [],
        "required_env": [],
        "missing_env": [],
        "network_required": False,
        "provider": None,
        "model": None,
        "shelf": None,
        "safety_boundaries": [],
        "output_policy": _output_policy(),
    }


from .runner_cli import _build_parser, _json_object_argument, main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
