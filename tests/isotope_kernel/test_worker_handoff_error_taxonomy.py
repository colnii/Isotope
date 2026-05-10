from __future__ import annotations

import pytest

from isotope_kernel.errors import KernelError
from isotope_kernel.refs import make_artifact_ref
from isotope_kernel.server import InProcessServer


def _server_with_run(tmp_path):
    api = InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="worker handoff error taxonomy")
    return api, run["run_id"]


def _delegation_intent() -> dict:
    return {
        "parent_agent_id": "agent_supervisor",
        "requested_worker_role": "worker",
        "requested_capabilities": {
            "tools": ["write_artifact_tool"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        },
    }


def _source_artifact_ref(api: InProcessServer, run_id: str):
    result = api.create_source_artifact(
        run_id,
        summary="worker handoff error taxonomy source",
        content="deterministic source artifact",
    )
    return result["artifact_ref"]


def _worker_events(api: InProcessServer, run_id: str):
    return [event for event in api.get_events(run_id) if event.event_type.startswith(("delegation.", "worker."))]


def _assert_no_partial_worker_events(api: InProcessServer, run_id: str, before_events):
    assert api.get_events(run_id) == before_events
    assert _worker_events(api, run_id) == []


def _assert_kernel_error(
    error: BaseException,
    *,
    code: str,
    category: str,
    retryable: bool = False,
    http_status: int,
    detail_keys: set[str],
):
    assert isinstance(error, KernelError)
    assert error.code == code
    assert error.category == category
    assert error.retryable is retryable
    assert error.http_status == http_status
    assert detail_keys.issubset(error.details)
    assert "content" not in error.details
    assert "raw_payload" not in error.details
    assert "secret" not in error.details


def test_worker_handoff_non_dict_intent_raises_structured_validation_without_partial_events(tmp_path):
    api, run_id = _server_with_run(tmp_path)
    artifact_ref = _source_artifact_ref(api, run_id)
    before_events = list(api.get_events(run_id))

    with pytest.raises(KernelError) as exc_info:
        api.submit_worker_handoff(
            run_id,
            delegation_intent="not-a-dict",  # type: ignore[arg-type]
            artifact_ref=artifact_ref,
            summary="worker handoff should fail before append",
        )

    _assert_kernel_error(
        exc_info.value,
        code="worker_handoff_invalid_intent",
        category="validation",
        http_status=400,
        detail_keys={"field"},
    )
    _assert_no_partial_worker_events(api, run_id, before_events)


def test_worker_handoff_forged_grants_raise_structured_policy_error_without_partial_events(tmp_path):
    api, run_id = _server_with_run(tmp_path)
    artifact_ref = _source_artifact_ref(api, run_id)
    intent = _delegation_intent()
    intent["grants"] = {"tools": ["admin_tool"]}
    before_events = list(api.get_events(run_id))

    with pytest.raises(KernelError) as exc_info:
        api.submit_worker_handoff(
            run_id,
            delegation_intent=intent,
            artifact_ref=artifact_ref,
            summary="worker handoff should reject forged grants",
        )

    _assert_kernel_error(
        exc_info.value,
        code="worker_handoff_forged_grants",
        category="policy",
        http_status=403,
        detail_keys={"field"},
    )
    _assert_no_partial_worker_events(api, run_id, before_events)


def test_worker_handoff_unknown_artifact_ref_raises_structured_not_found_without_partial_events(tmp_path):
    api, run_id = _server_with_run(tmp_path)
    before_events = list(api.get_events(run_id))

    with pytest.raises(KernelError) as exc_info:
        api.submit_worker_handoff(
            run_id,
            delegation_intent=_delegation_intent(),
            artifact_ref=make_artifact_ref(run_id, "artifact_missing"),
            summary="worker handoff should reject unknown artifact",
        )

    _assert_kernel_error(
        exc_info.value,
        code="worker_handoff_unknown_artifact",
        category="not_found",
        http_status=404,
        detail_keys={"artifact_id", "run_id"},
    )
    _assert_no_partial_worker_events(api, run_id, before_events)


def test_worker_handoff_policy_denial_preserves_permission_error_compatibility_and_structured_attrs(
    tmp_path,
):
    api, run_id = _server_with_run(tmp_path)
    artifact_ref = _source_artifact_ref(api, run_id)
    intent = _delegation_intent()
    intent["requested_capabilities"]["tools"] = []
    before_events = list(api.get_events(run_id))

    with pytest.raises(PermissionError) as exc_info:
        api.submit_worker_handoff(
            run_id,
            delegation_intent=intent,
            artifact_ref=artifact_ref,
            summary="worker handoff should be denied by policy",
        )

    error = exc_info.value
    assert error.args[0] == "worker handoff denied by policy"
    assert getattr(error, "code", None) == "worker_handoff_denied"
    assert getattr(error, "category", None) == "policy"
    assert getattr(error, "retryable", None) is False
    assert getattr(error, "http_status", None) == 403
    assert getattr(error, "details", {}).get("reason_codes") == ["tool_not_requested"]
    _assert_no_partial_worker_events(api, run_id, before_events)
