"""Model-facing capacity observations for Supervisor conversation loop."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from isotope.platform.schemas.refs import make_artifact_ref
from isotope.workspace.artifacts import ArtifactStore
from .notifications.context.projection import request_context_model_observation


def capacity_observation_from_event_payload(
    *,
    payload: dict[str, Any],
    private: dict[str, Any],
) -> dict[str, Any]:
    observation = private.get("model_observation")
    if isinstance(observation, dict):
        return observation
    return {
        "kind": "capacity_observation",
        "capacity_id": payload["capacity_id"],
        "status": payload["status"],
        "result": payload.get("result", {}),
    }


def capacity_observation_message_content(
    observations: list[dict[str, Any]],
) -> str | list[dict[str, Any]]:
    text_observations = [
        {
            key: value
            for key, value in observation.items()
            if key != "image_urls"
        }
        for observation in observations
    ]
    text = _json_context_message(
        "capacity_observation",
        {"kind": "capacity_observations", "items": text_observations},
    )
    image_urls = [
        image_url
        for observation in observations
        for image_url in observation.get("image_urls", [])
        if isinstance(image_url, str) and image_url
    ]
    if not image_urls:
        return text
    return [
        {"type": "text", "text": text},
        *[
            {
                "type": "image_url",
                "image_url": {"url": image_url},
            }
            for image_url in image_urls
        ],
    ]


def model_observation_from_agent_loop(
    *,
    capacity_id: str,
    status: str,
    result: dict[str, Any],
    agent_loop: dict[str, Any],
    state_root: Path,
) -> dict[str, Any]:
    observation = {
        "kind": "capacity_observation",
        "capacity_id": capacity_id,
        "status": status,
        "result": result,
    }
    result = _capability_result_observation(
        capacity_id=capacity_id,
        agent_loop=agent_loop,
    )
    if result is not None:
        observation["result"] = result
    if capacity_id == "coding_task.run":
        reviewed_apply = agent_loop.get("reviewed_apply_request")
        if isinstance(reviewed_apply, dict):
            arguments = reviewed_apply.get("arguments")
            if isinstance(arguments, dict):
                observation["suggested_next_call"] = {
                    "capacity_id": "coding_task.apply_reviewed_diff",
                    "arguments": {
                        "review_handle_id": arguments.get("review_handle_id"),
                    },
                    "requires_user_approval": True,
                }
    image_urls = _screen_observation_image_urls(agent_loop, state_root=state_root)
    if image_urls:
        observation["image_urls"] = image_urls
    return observation


def screen_artifact_detail_from_agent_loop(
    agent_loop: dict[str, Any],
) -> dict[str, Any] | None:
    capability_run = _agent_loop_capability_run(agent_loop)
    if not isinstance(capability_run, dict):
        return None
    screen_report = capability_run.get("screen_report")
    if not isinstance(screen_report, dict):
        return None
    artifacts = screen_report.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return None
    safe_artifacts = [
        _safe_screen_artifact_record(artifact)
        for artifact in artifacts
        if isinstance(artifact, dict)
    ]
    safe_artifacts = [artifact for artifact in safe_artifacts if artifact is not None]
    if not safe_artifacts:
        return None
    return {
        "label": "Screen artifacts",
        "kind": "json",
        "content": {
            "artifacts": safe_artifacts,
        },
    }


def research_artifact_detail_from_agent_loop(
    agent_loop: dict[str, Any],
) -> dict[str, Any] | None:
    capability_run = _agent_loop_capability_run(agent_loop)
    if not isinstance(capability_run, dict):
        return None
    if capability_run.get("capability_id") != "research.search":
        return None
    research_search = capability_run.get("research_search")
    if not isinstance(research_search, dict):
        return None
    artifacts = research_search.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return None
    safe_artifacts = [
        _safe_research_artifact_record(artifact)
        for artifact in artifacts
        if isinstance(artifact, dict)
    ]
    safe_artifacts = [artifact for artifact in safe_artifacts if artifact is not None]
    if not safe_artifacts:
        return None
    return {
        "label": "Research artifacts",
        "kind": "json",
        "content": {
            "artifacts": safe_artifacts,
        },
    }


def capability_result_detail_from_agent_loop(
    *,
    capacity_id: str,
    agent_loop: dict[str, Any],
) -> dict[str, Any] | None:
    result = _capability_result_observation(
        capacity_id=capacity_id,
        agent_loop=agent_loop,
    )
    if result is None:
        return None
    return {
        "label": _capability_result_detail_label(capacity_id),
        "kind": "json",
        "content": result,
    }


def _capability_result_detail_label(capacity_id: str) -> str:
    labels = {
        "memory.query": "Memory query result",
        "memory.recall": "Memory recall result",
        "code.search": "Code search result",
        "code.read": "Code read result",
        "code.apply_patch": "Patch result",
        "artifact.diff_result": "Artifact result",
        "supervisor.project_status": "Project status summary",
        "skills.search": "Skills search result",
        "skills.describe": "Skill description",
        "mcp.servers.list": "MCP servers",
        "mcp.tools.search": "MCP tools",
        "mcp.tool.call": "MCP tool result",
    }
    return labels.get(capacity_id, "Capability result")


def _json_context_message(label: str, value: dict[str, Any]) -> str:
    return f"{label}:\n" + json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
    )


def _capability_result_observation(
    *,
    capacity_id: str,
    agent_loop: dict[str, Any],
) -> dict[str, Any] | None:
    capability_run = _agent_loop_capability_run(agent_loop)
    if not isinstance(capability_run, dict):
        return None
    if capacity_id in {"memory.query", "memory.recall"}:
        return _memory_query_observation(capability_run)
    if capacity_id == "code.search":
        return _code_search_observation(capability_run)
    if capacity_id == "code.read":
        return _code_read_observation(capability_run)
    if capacity_id == "code.apply_patch":
        return _patch_result_observation(capability_run)
    if capacity_id == "artifact.diff_result":
        return _artifact_result_observation(capability_run)
    if capacity_id == "supervisor.project_status":
        return _project_status_observation(capability_run)
    if capacity_id == "supervisor.request_context":
        return request_context_model_observation(capability_run)
    if capacity_id == "isotope.self_repair":
        return _self_repair_observation(capability_run)
    if capacity_id == "supervisor.goal_plan":
        return _goal_plan_observation(capability_run)
    if capacity_id == "skills.search":
        return _skills_search_observation(capability_run)
    if capacity_id == "skills.describe":
        return _skill_description_observation(capability_run)
    if capacity_id == "mcp.servers.list":
        return _mcp_servers_observation(capability_run)
    if capacity_id == "mcp.tools.search":
        return _mcp_tools_observation(capability_run)
    if capacity_id == "mcp.tool.call":
        return _mcp_tool_call_observation(capability_run)
    return None


def _memory_query_observation(capability_run: dict[str, Any]) -> dict[str, Any] | None:
    memory_query = capability_run.get("memory_query")
    kind = "memory_query"
    if not isinstance(memory_query, dict):
        memory_query = capability_run.get("memory_recall")
        kind = "memory_recall"
    if not isinstance(memory_query, dict):
        return None
    results = memory_query.get("results")
    safe_results: list[dict[str, Any]] = []
    if isinstance(results, list):
        for result in results:
            if not isinstance(result, dict):
                continue
            safe_result = _safe_memory_query_result(result)
            if safe_result is not None:
                safe_results.append(safe_result)
    return {
        "kind": kind,
        "status": (
            memory_query.get("status")
            if isinstance(memory_query.get("status"), str)
            else ""
        ),
        "content_policy": (
            memory_query.get("content_policy")
            if isinstance(memory_query.get("content_policy"), str)
            else ""
        ),
        "result_count": len(results) if isinstance(results, list) else 0,
        "results": safe_results,
    }


def _goal_plan_observation(capability_run: dict[str, Any]) -> dict[str, Any] | None:
    goal_plan = capability_run.get("goal_plan")
    if not isinstance(goal_plan, dict):
        return None
    candidates = [
        _safe_goal_candidate(candidate)
        for candidate in goal_plan.get("candidates", [])
        if isinstance(candidate, dict)
    ]
    candidates = [candidate for candidate in candidates if candidate is not None]
    written_goals = goal_plan.get("written_goals")
    return {
        key: value
        for key, value in {
            "status": goal_plan.get("status"),
            "mode": goal_plan.get("mode"),
            "planning_trigger": goal_plan.get("planning_trigger"),
            "plan_summary": goal_plan.get("plan_summary"),
            "candidate_count": len(candidates),
            "written_count": (
                len(written_goals) if isinstance(written_goals, list) else 0
            ),
            "candidates": candidates,
        }.items()
        if value not in (None, "", [], {})
    }


def _safe_goal_candidate(candidate: dict[str, Any]) -> dict[str, str] | None:
    goal = candidate.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        return None
    item = {"goal": _clip_text(goal.strip(), limit=240)}
    for key in ("target_name", "reason", "stage", "scope"):
        value = candidate.get(key)
        if isinstance(value, str) and value.strip():
            item[key] = _clip_text(value.strip(), limit=180)
    return item


def _clip_text(text: str, *, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


def _safe_memory_query_result(result: dict[str, Any]) -> dict[str, Any] | None:
    record_id = result.get("record_id")
    summary = result.get("summary")
    if not isinstance(record_id, str) or not isinstance(summary, str):
        return None
    safe_result: dict[str, Any] = {
        "record_id": record_id,
        "summary": summary,
    }
    scope = result.get("scope")
    if isinstance(scope, str):
        safe_result["scope"] = scope
    source_refs = result.get("source_refs")
    if isinstance(source_refs, list):
        safe_result["source_refs"] = [
            ref for ref in source_refs if isinstance(ref, dict)
        ]
    provenance = result.get("provenance")
    if isinstance(provenance, dict):
        safe_result["provenance"] = dict(provenance)
    quality = result.get("quality")
    if isinstance(quality, str):
        safe_result["quality"] = quality
    return safe_result


def _skills_search_observation(
    capability_run: dict[str, Any],
) -> dict[str, Any] | None:
    if capability_run.get("kind") != "skill_search_result":
        return None
    return {
        "kind": "skill_search_result",
        "status": _string_value(capability_run.get("status")),
        "runner_kind": _string_value(capability_run.get("runner_kind")),
        "query": _string_value(capability_run.get("query")),
        "skill_count": _int_value(capability_run.get("skill_count")),
        "skills": [
            safe_skill
            for skill in _dict_list_value(capability_run.get("skills"))
            if (safe_skill := _safe_skill_metadata(skill)) is not None
        ],
        "skipped": _safe_mapping_list(capability_run.get("skipped"), limit=20),
    }


def _skill_description_observation(
    capability_run: dict[str, Any],
) -> dict[str, Any] | None:
    if capability_run.get("kind") != "skill_description":
        return None
    skill = capability_run.get("skill")
    safe_skill = _safe_skill_metadata(skill) if isinstance(skill, dict) else None
    return {
        "kind": "skill_description",
        "status": _string_value(capability_run.get("status")),
        "runner_kind": _string_value(capability_run.get("runner_kind")),
        "skill": safe_skill or {},
        "body": _string_value(capability_run.get("body")),
        "body_truncated": bool(capability_run.get("body_truncated")),
        "linked_paths": _string_list_value(capability_run.get("linked_paths")),
    }


def _safe_skill_metadata(skill: dict[str, Any]) -> dict[str, Any] | None:
    skill_id = skill.get("skill_id")
    name = skill.get("name")
    description = skill.get("description")
    if not isinstance(skill_id, str) or not isinstance(name, str):
        return None
    if not isinstance(description, str):
        return None
    return {
        key: value
        for key, value in {
            "skill_id": skill_id,
            "name": name,
            "description": description,
            "relative_path": _string_value(skill.get("relative_path")),
            "readiness": _string_value(skill.get("readiness")),
            "source_kind": _string_value(skill.get("source_kind")),
        }.items()
        if value not in (None, "", [], {})
    }


def _mcp_servers_observation(
    capability_run: dict[str, Any],
) -> dict[str, Any] | None:
    if capability_run.get("kind") != "mcp_server_list":
        return None
    return {
        "kind": "mcp_server_list",
        "status": _string_value(capability_run.get("status")),
        "runner_kind": _string_value(capability_run.get("runner_kind")),
        "servers": [
            safe_server
            for server in _dict_list_value(capability_run.get("servers"))
            if (safe_server := _safe_mcp_server(server)) is not None
        ],
    }


def _safe_mcp_server(server: dict[str, Any]) -> dict[str, Any] | None:
    server_id = server.get("server_id")
    if not isinstance(server_id, str):
        return None
    return {
        "server_id": server_id,
        "transport": _string_value(server.get("transport")),
        "command_summary": _string_value(server.get("command_summary")),
        "enabled": bool(server.get("enabled")),
        "readiness": _string_value(server.get("readiness")),
        "allowed_operations": _string_list_value(server.get("allowed_operations")),
        "source_kind": _string_value(server.get("source_kind")),
    }


def _mcp_tools_observation(
    capability_run: dict[str, Any],
) -> dict[str, Any] | None:
    if capability_run.get("kind") != "mcp_tool_search_result":
        return None
    return {
        "kind": "mcp_tool_search_result",
        "status": _string_value(capability_run.get("status")),
        "runner_kind": _string_value(capability_run.get("runner_kind")),
        "server_id": _string_value(capability_run.get("server_id")),
        "query": _string_value(capability_run.get("query")),
        "tools": [
            safe_tool
            for tool in _dict_list_value(capability_run.get("tools"))
            if (safe_tool := _safe_mcp_tool(tool)) is not None
        ],
    }


def _safe_mcp_tool(tool: dict[str, Any]) -> dict[str, Any] | None:
    tool_name = tool.get("tool_name")
    if not isinstance(tool_name, str):
        return None
    return {
        "server_id": _string_value(tool.get("server_id")),
        "tool_name": tool_name,
        "title": _string_value(tool.get("title")),
        "description": _string_value(tool.get("description")),
        "input_schema": _safe_mapping(tool.get("input_schema")),
        "readiness": _string_value(tool.get("readiness")),
    }


def _mcp_tool_call_observation(
    capability_run: dict[str, Any],
) -> dict[str, Any] | None:
    if capability_run.get("kind") != "mcp_tool_call_result":
        return None
    return {
        "kind": "mcp_tool_call_result",
        "status": _string_value(capability_run.get("status")),
        "runner_kind": _string_value(capability_run.get("runner_kind")),
        "server_id": _string_value(capability_run.get("server_id")),
        "tool_name": _string_value(capability_run.get("tool_name")),
        "structured_content": _safe_mapping(capability_run.get("structured_content")),
        "content_summary": [
            _clip_text(item, limit=2000)
            for item in _string_list_value(capability_run.get("content_summary"))
        ],
        "is_error": bool(capability_run.get("is_error")),
        "error_summary": _clip_text(
            _string_value(capability_run.get("error_summary")),
            limit=2000,
        ),
    }


def _code_search_observation(capability_run: dict[str, Any]) -> dict[str, Any] | None:
    code_search = capability_run.get("code_search")
    if not isinstance(code_search, dict):
        return None
    return {
        "kind": "code_search",
        "status": _string_value(code_search.get("status")),
        "query": _string_value(code_search.get("query")),
        "include_paths": _string_list_value(code_search.get("include_paths")),
        "match_count": _int_value(code_search.get("match_count")),
        "total_match_count": _int_value(code_search.get("total_match_count")),
        "truncated": bool(code_search.get("truncated")),
        "content_policy": _string_value(code_search.get("content_policy")),
        "matches": [
            safe_match
            for match in _dict_list_value(code_search.get("matches"))
            if (safe_match := _safe_code_search_match(match)) is not None
        ],
    }


def _safe_code_search_match(match: dict[str, Any]) -> dict[str, Any] | None:
    path = match.get("path")
    line_number = match.get("line_number")
    excerpt = match.get("excerpt")
    if not isinstance(path, str) or not isinstance(line_number, int):
        return None
    if not isinstance(excerpt, str):
        return None
    return {
        "path": path,
        "line_number": line_number,
        "excerpt": excerpt,
        "truncated": bool(match.get("truncated")),
        "code_ref": _string_dict_value(match.get("code_ref")),
    }


def _code_read_observation(capability_run: dict[str, Any]) -> dict[str, Any] | None:
    code_read = capability_run.get("code_read")
    if not isinstance(code_read, dict):
        return None
    return {
        "kind": "code_read",
        "status": _string_value(code_read.get("status")),
        "path": _string_value(code_read.get("path")),
        "line_count": _int_value(code_read.get("line_count")),
        "excerpt": _string_value(code_read.get("excerpt")),
        "truncated": bool(code_read.get("truncated")),
        "code_ref": _string_dict_value(code_read.get("code_ref")),
        "content_policy": _string_value(code_read.get("content_policy")),
    }


def _patch_result_observation(capability_run: dict[str, Any]) -> dict[str, Any] | None:
    patch_result = capability_run.get("patch_result")
    if not isinstance(patch_result, dict):
        return None
    return {
        "kind": "patch_result",
        "status": _string_value(patch_result.get("status")),
        "changed_files": _string_list_value(patch_result.get("changed_files")),
        "file_count": _int_value(patch_result.get("file_count")),
        "hunk_count": _int_value(patch_result.get("hunk_count")),
        "write_policy": _string_value(patch_result.get("write_policy")),
        "content_policy": _string_value(patch_result.get("content_policy")),
    }


def _artifact_result_observation(
    capability_run: dict[str, Any],
) -> dict[str, Any] | None:
    artifact = capability_run.get("artifact")
    if not isinstance(artifact, dict):
        return None
    return {
        "kind": "artifact_result",
        "artifact_id": _string_value(artifact.get("artifact_id")),
        "artifact_type": _string_value(artifact.get("artifact_type")),
        "summary": _string_value(artifact.get("summary")),
        "ref": _string_dict_value(artifact.get("ref")),
        "artifact_write": _string_value(artifact.get("artifact_write")),
        "content_policy": _string_value(artifact.get("content_policy")),
    }


def _string_value(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _int_value(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _string_list_value(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _dict_list_value(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_dict_value(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        key: item
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, str)
    }


def _project_status_observation(capability_run: dict[str, Any]) -> dict[str, Any] | None:
    summary = capability_run.get("project_state")
    if not isinstance(summary, dict):
        return None
    activities = summary.get("activities")
    approvals = summary.get("approvals")
    artifacts = summary.get("artifacts")
    active_goal = _safe_mapping(summary.get("active_goal"))
    active_agent = _safe_mapping(summary.get("active_agent"))
    return {
        "kind": "project_state",
        "status": capability_run.get("status"),
        "project_state": {
            "snapshot_id": summary.get("snapshot_id"),
            "generated_at": summary.get("generated_at"),
            "active_goal": _compact_project_state_node(active_goal),
            "active_agent": _compact_project_state_node(active_agent),
            "counts": _safe_mapping(summary.get("counts")),
            "activity_count": len(activities) if isinstance(activities, list) else 0,
            "approval_count": len(approvals) if isinstance(approvals, list) else 0,
            "artifact_count": len(artifacts) if isinstance(artifacts, list) else 0,
            "self_repair_workers": _safe_mapping_list(
                summary.get("self_repair_workers"),
                limit=3,
            ),
            "latest_self_repair": _safe_mapping(summary.get("latest_self_repair")),
            "open_capability_gaps": _safe_mapping_list(
                summary.get("open_capability_gaps"),
                limit=3,
            ),
        },
    }


def _compact_project_state_node(value: dict[str, Any]) -> dict[str, Any]:
    if not value:
        return {}
    return {
        key: _clip_text(text.strip(), limit=180)
        for key in ("id", "kind", "status", "title")
        if isinstance((text := value.get(key)), str) and text.strip()
    }


def _self_repair_observation(capability_run: dict[str, Any]) -> dict[str, Any] | None:
    self_repair = capability_run.get("self_repair")
    if not isinstance(self_repair, dict):
        return None
    managed = self_repair.get("managed")
    worktree = self_repair.get("worktree")
    capability_gap = self_repair.get("capability_gap")
    return {
        "kind": "self_repair",
        "status": self_repair.get("status"),
        "runner_kind": capability_run.get("runner_kind"),
        "managed": _self_repair_managed_observation(managed),
        "worktree": _self_repair_worktree_observation(worktree),
        "capability_gap": _safe_mapping(capability_gap),
    }


def _self_repair_managed_observation(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "name": value.get("name"),
        "record_id": value.get("record_id"),
        "pid": value.get("pid"),
        "backend": value.get("backend"),
        "worker_role": value.get("worker_role"),
        "cwd": value.get("cwd"),
        "log_path": value.get("log_path"),
    }


def _self_repair_worktree_observation(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "enabled": value.get("enabled"),
        "source_cwd": value.get("source_cwd"),
        "cwd": value.get("cwd"),
        "worktree_root": value.get("worktree_root"),
        "branch": value.get("branch"),
    }


def _safe_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_mapping_list(value: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value[:limit] if isinstance(item, dict)]


def _screen_observation_image_urls(
    agent_loop: dict[str, Any],
    *,
    state_root: Path,
) -> list[str]:
    capability_run = _agent_loop_capability_run(agent_loop)
    if not isinstance(capability_run, dict):
        return []
    screen_report = capability_run.get("screen_report")
    if not isinstance(screen_report, dict):
        return []
    artifacts = screen_report.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    store = ArtifactStore(_screen_observation_artifact_root(agent_loop, state_root=state_root))
    image_urls: list[str] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        if artifact.get("artifact_type") != "screen_screenshot":
            continue
        ref = artifact.get("ref")
        if not isinstance(ref, dict):
            continue
        run_id = ref.get("run_id")
        artifact_id = ref.get("artifact_id")
        if not isinstance(run_id, str) or not isinstance(artifact_id, str):
            continue
        image_url = _screen_screenshot_data_url(
            store,
            run_id=run_id,
            artifact_id=artifact_id,
        )
        if image_url is not None:
            image_urls.append(image_url)
    return image_urls


def _safe_screen_artifact_record(artifact: dict[str, Any]) -> dict[str, Any] | None:
    artifact_type = artifact.get("artifact_type")
    ref = artifact.get("ref")
    if not isinstance(artifact_type, str) or not isinstance(ref, dict):
        return None
    artifact_id = artifact.get("artifact_id") or ref.get("artifact_id")
    run_id = artifact.get("run_id") or ref.get("run_id")
    if not isinstance(artifact_id, str) or not isinstance(run_id, str):
        return None
    return {
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
        "run_id": run_id,
        "summary": artifact.get("summary") if isinstance(artifact.get("summary"), str) else "",
        "ref": {
            key: value
            for key, value in ref.items()
            if key in {"ref_type", "scope", "run_id", "artifact_id"} and isinstance(value, str)
        },
    }


def _safe_research_artifact_record(artifact: dict[str, Any]) -> dict[str, Any] | None:
    artifact_type = artifact.get("artifact_type")
    ref = artifact.get("ref")
    if (
        not isinstance(artifact_type, str)
        or not artifact_type.startswith("research.")
        or not isinstance(ref, dict)
    ):
        return None
    artifact_id = artifact.get("artifact_id") or ref.get("artifact_id")
    run_id = artifact.get("run_id") or ref.get("run_id")
    if not isinstance(artifact_id, str) or not isinstance(run_id, str):
        return None
    summary = artifact.get("summary")
    return {
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
        "run_id": run_id,
        "summary": summary if isinstance(summary, str) else "",
        "ref": {
            key: value
            for key, value in ref.items()
            if key in {"ref_type", "scope", "run_id", "artifact_id"}
            and isinstance(value, str)
        },
    }


def _screen_observation_artifact_root(agent_loop: dict[str, Any], *, state_root: Path) -> Path:
    step_request = agent_loop.get("step_request")
    inputs = step_request.get("inputs") if isinstance(step_request, dict) else None
    root = inputs.get("root") if isinstance(inputs, dict) else None
    if isinstance(root, str) and root.strip():
        return Path(root).expanduser()
    return state_root / "supervisor" / "conversation-loop-runs"


def _agent_loop_capability_run(agent_loop: dict[str, Any]) -> dict[str, Any] | None:
    tick_result = agent_loop.get("tick_result")
    if not isinstance(tick_result, dict):
        return None
    planner_result = tick_result.get("planner_result")
    if not isinstance(planner_result, dict):
        return None
    step_result = planner_result.get("step_result")
    if not isinstance(step_result, dict):
        return None
    action_result = step_result.get("action_result")
    if not isinstance(action_result, dict):
        return None
    capability_run = action_result.get("capability_run")
    return capability_run if isinstance(capability_run, dict) else None


def _screen_screenshot_data_url(
    store: ArtifactStore,
    *,
    run_id: str,
    artifact_id: str,
) -> str | None:
    content = store.get_content(make_artifact_ref(run_id=run_id, artifact_id=artifact_id))
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("encoding") != "base64":
        return None
    media_type = payload.get("media_type")
    data = payload.get("data")
    if not isinstance(media_type, str) or not media_type.startswith("image/"):
        return None
    if not isinstance(data, str) or not data:
        return None
    return f"data:{media_type};base64,{data}"
