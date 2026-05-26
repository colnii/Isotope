"""DTO serialization helpers for the in-process HTTP facade."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from typing import Any

from ...features.ask.flow import WorkbenchAskAnswer
from ...features.files.flow import FileSummary
from ...features.projects.flow import ProjectDetail, ProjectSummary
from ...features.projects.workspace import ProjectWorkspace
from ...features.search.flow import SearchResult
from ...features.tasks.flow import TaskSummary
from ...features.workbench.flow import WorkbenchView
from ...platform.schemas.refs import ResourceRef


class HttpSerializationMixin:
    """Convert internal read models into HTTP response dictionaries."""

    def _find_artifact_summary(self, artifact_id: str) -> dict[str, Any] | None:
        runs_root = self.root_path / "runs"
        if not runs_root.exists():
            return None
        for event_path in sorted(runs_root.glob("*/events.jsonl")):
            run_id = event_path.parent.name
            for event in self.server.event_store.list_events(run_id):
                if event.event_type != "artifact.created":
                    continue
                artifact = event.payload.get("artifact")
                if not isinstance(artifact, dict):
                    continue
                ref = artifact.get("ref")
                if not isinstance(ref, dict) or ref.get("artifact_id") != artifact_id:
                    continue
                record = self.server.get_artifact_record(self._artifact_ref_from_dict(ref))
                return {
                    "ref": dict(record["ref"]),
                    "artifact_type": record["artifact_type"],
                    "summary": record["summary"],
                    "provenance": dict(record["provenance"]),
                }
        return None

    def _artifact_ref_from_dict(self, data: dict[str, Any]) -> ResourceRef:
        return ResourceRef(
            ref_type=self._required_artifact_ref_string(data, "ref_type"),
            scope=self._required_artifact_ref_string(data, "scope"),
            run_id=self._required_artifact_ref_string(data, "run_id"),
            artifact_id=self._required_artifact_ref_string(data, "artifact_id"),
        )

    def _required_artifact_ref_string(self, data: dict[str, Any], field_name: str) -> str:
        value = data.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"artifact ref requires {field_name}")
        return value

    def _submit_result_to_dict(self, result: dict[str, Any]) -> dict[str, Any]:
        body: dict[str, Any] = {
            "status": result["status"],
            "run_state": self._run_state_to_dict(result["run_state"]),
        }
        if result.get("proposal_id"):
            body["proposal_id"] = result["proposal_id"]
        if result.get("decision_id"):
            body["decision_id"] = result["decision_id"]
        if result.get("approval_id"):
            body["approval_id"] = result["approval_id"]
        artifact_ref = result.get("artifact_ref")
        if artifact_ref is not None:
            body["artifact_ref"] = artifact_ref.to_dict()
        if result.get("execution_id"):
            body["execution_id"] = result["execution_id"]
        if result.get("tool_execution_status"):
            body["tool_execution_status"] = result["tool_execution_status"]
        return body

    def _llm_provider_result_to_dict(self, result: dict[str, Any]) -> dict[str, Any]:
        tool_result = result.get("tool_result")
        if not isinstance(tool_result, dict):
            tool_result = {}
        body: dict[str, Any] = {
            "status": result.get("status"),
            "provider_status": result.get("provider_status"),
            "provider": result.get("provider"),
            "model": result.get("model"),
            "finish_reason": result.get("finish_reason"),
            "usage": self._safe_metadata_dict(result.get("usage")),
            "tool_name": result.get("tool_name"),
            "provider_tool_call_id": result.get("provider_tool_call_id"),
            "requires_approval": result.get("requires_approval"),
        }
        for key in (
            "previous_provider_tool_call_id",
            "tool_result_status",
            "tool_result_artifact_ref",
            "submission_status",
        ):
            if key in result:
                body[key] = deepcopy(result[key])
        for key in (
            "approval_id",
            "proposal_id",
            "decision_id",
            "execution_id",
            "tool_execution_status",
            "artifact_ref",
            "run_state",
        ):
            if key in tool_result:
                body[key] = deepcopy(tool_result[key])
        if "assistant_message" in result:
            body["assistant_message"] = deepcopy(result["assistant_message"])
        return body

    def _llm_product_chat_result_to_dict(self, result: dict[str, Any]) -> dict[str, Any]:
        body = self._llm_provider_result_to_dict(result)
        body["turn_kind"] = result.get("turn_kind")
        return body

    def _task_summary_to_dict(self, summary: TaskSummary) -> dict[str, Any]:
        return summary.to_dict()

    def _file_summary_to_dict(self, summary: FileSummary) -> dict[str, Any]:
        return summary.to_dict()

    def _project_summary_to_dict(self, summary: ProjectSummary) -> dict[str, Any]:
        return summary.to_dict()

    def _project_detail_to_dict(self, detail: ProjectDetail) -> dict[str, Any]:
        return detail.to_dict()

    def _project_workspace_to_dict(self, workspace: ProjectWorkspace) -> dict[str, Any]:
        return workspace.to_dict()

    def _search_result_to_dict(self, result: SearchResult) -> dict[str, Any]:
        return result.to_dict()

    def _workbench_view_to_dict(self, view: WorkbenchView) -> dict[str, Any]:
        return view.to_dict()

    def _workbench_ask_answer_to_dict(self, answer: WorkbenchAskAnswer) -> dict[str, Any]:
        return answer.to_dict()

    def _run_state_to_dict(self, state: Any) -> dict[str, Any]:
        return asdict(state)

    def _safe_metadata_dict(self, values: Any) -> dict[str, Any]:
        if not isinstance(values, dict):
            return {}
        return {
            key: value
            for key, value in values.items()
            if isinstance(key, str)
            and (isinstance(value, (str, int, float, bool)) or value is None)
        }
