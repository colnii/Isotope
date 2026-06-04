"""Model-facing capacity observations for Supervisor conversation loop."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from isotope.platform.schemas.refs import make_artifact_ref
from isotope.workspace.artifacts import ArtifactStore


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
        "result_summary": payload.get("result_summary", {}),
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
    result_summary: dict[str, Any],
    agent_loop: dict[str, Any],
    state_root: Path,
) -> dict[str, Any]:
    observation = {
        "kind": "capacity_observation",
        "capacity_id": capacity_id,
        "status": status,
        "result_summary": result_summary,
    }
    result = _capability_result_observation(
        capacity_id=capacity_id,
        agent_loop=agent_loop,
    )
    if result is not None:
        observation["result"] = result
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
    if capacity_id == "memory.query":
        return _memory_query_observation(capability_run)
    return None


def _memory_query_observation(capability_run: dict[str, Any]) -> dict[str, Any] | None:
    memory_query = capability_run.get("memory_query")
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
        "kind": "memory_query",
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
