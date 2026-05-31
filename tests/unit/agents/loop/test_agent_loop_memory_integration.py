from __future__ import annotations

from typing import Any

import isotope.runtime.in_process as server


FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "raw_artifact_content",
    "raw_content",
}


def _new_run(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="remember turn state across loop ticks")
    return api, session["session_id"], run["run_id"]


def _assert_no_forbidden_content_keys(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_CONTENT_KEYS.intersection(value)
        assert forbidden == set()
        for nested in value.values():
            _assert_no_forbidden_content_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_content_keys(nested)


def test_agent_loop_records_turn_memory_and_queries_it_after_restart(tmp_path):
    api, session_id, run_id = _new_run(tmp_path)
    source = api.run_agent_loop_step(
        run_id,
        {
            "step": "create_source_artifact",
            "summary": "turn planning note",
            "content": "The next loop should resume from the memory integration boundary.",
        },
    )

    recorded = api.run_agent_loop_step(
        run_id,
        {
            "step": "record_turn_memory",
            "scope": "run",
            "summary": "Resume from the memory integration boundary.",
            "content": {
                "kind": "turn_state",
                "text": "The next loop should resume from the memory integration boundary.",
            },
            "source_refs": [source["action_result"]["artifact_ref"]],
            "quality": "candidate",
        },
    )

    assert recorded["step"] == "record_turn_memory"
    assert recorded["status"] == "completed"
    assert recorded["action_result"]["record_id"].startswith("mem_")
    assert recorded["control"]["phase"] == "ready"
    assert recorded["control"]["progress"]["memory_records_total"] == 1

    restarted = server.InProcessServer(tmp_path)
    before_query_events = list(restarted.get_events(run_id))
    recalled = restarted.run_agent_loop_step(
        run_id,
        {
            "step": "query_memory",
            "query": "integration boundary",
            "scope": "run",
        },
    )

    assert recalled["step"] == "query_memory"
    assert recalled["status"] == "completed"
    assert recalled["action_result"]["status"] == "ok"
    assert restarted.get_events(run_id) == before_query_events
    assert recalled["action_result"]["results"] == [
        {
            "record_id": recorded["action_result"]["record_id"],
            "scope": "run",
            "summary": "Resume from the memory integration boundary.",
            "source_refs": [source["action_result"]["artifact_ref"]],
            "provenance": {
                "run_id": run_id,
                "session_id": session_id,
                "execution_id": recorded["action_result"]["execution_id"],
                "action_type": "write_memory",
            },
            "quality": "candidate",
        }
    ]
    assert recalled["control"]["progress"]["memory_records_total"] == 1
    _assert_no_forbidden_content_keys(recalled)


def test_agent_loop_query_memory_materializes_controlled_expand_after_grant(tmp_path):
    api, session_id, run_id = _new_run(tmp_path)
    recorded = api.run_agent_loop_step(
        run_id,
        {
            "step": "record_turn_memory",
            "scope": "run",
            "summary": "Resume from controlled expand metadata.",
            "content": {
                "kind": "turn_state",
                "text": "Hidden full memory payload must not leak.",
            },
            "source_refs": [],
            "quality": "candidate",
        },
    )

    recalled = api.run_agent_loop_step(
        run_id,
        {
            "step": "query_memory",
            "query": "controlled expand metadata",
            "scope": "run",
            "controlled_expand": True,
            "expand_budget": 100,
        },
    )

    assert recalled["action_result"]["status"] == "ok"
    controlled_expand = recalled["action_result"]["controlled_expand"]
    assert controlled_expand["status"] == "materialized"
    assert controlled_expand["budget"] == 100
    assert controlled_expand["content_policy"] == "controlled_expand_memory_record_content_only"
    assert controlled_expand["materialized_results"] == [
        {
            "record_id": recorded["action_result"]["record_id"],
            "scope": "run",
            "encoding": "json",
            "materialized_text": (
                '{"kind": "turn_state", '
                '"text": "Hidden full memory payload must not leak."}'
            ),
            "used": controlled_expand["used"],
            "truncated": False,
            "source_refs": [],
            "provenance": {
                "run_id": run_id,
                "session_id": session_id,
                "execution_id": recorded["action_result"]["execution_id"],
                "action_type": "write_memory",
            },
        }
    ]
    assert recalled["action_result"]["results"][0]["record_id"] == recorded["action_result"]["record_id"]
    _assert_no_forbidden_content_keys(recalled)


def test_agent_loop_promotes_run_memory_to_session_memory_for_later_run(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    source_run = api.create_run(session["session_id"], goal="capture durable preference")
    source = api.run_agent_loop_step(
        source_run["run_id"],
        {
            "step": "record_turn_memory",
            "scope": "run",
            "summary": "Prefer summary-only memory recall for planner context.",
            "content": {
                "kind": "turn_state",
                "text": "SECRET_SESSION_PROMOTION_PAYLOAD",
            },
            "source_refs": [],
            "quality": "candidate",
        },
    )

    promoted = api.run_agent_loop_step(
        source_run["run_id"],
        {
            "step": "promote_run_memory",
            "source_record_id": source["action_result"]["record_id"],
            "summary": "Prefer summary-only memory recall for planner context.",
            "reason": "carry durable preference to later runs in the same session",
            "quality": "candidate",
        },
    )
    later_run = api.create_run(session["session_id"], goal="plan with durable preference")

    recalled = api.run_agent_loop_step(
        later_run["run_id"],
        {
            "step": "query_memory",
            "scope": "session",
            "query": "summary-only planner context",
        },
    )

    assert promoted["step"] == "promote_run_memory"
    assert promoted["status"] == "completed"
    assert promoted["action_result"]["scope"] == "session"
    assert recalled["action_result"]["status"] == "ok"
    assert recalled["action_result"]["results"] == [
        {
            "record_id": promoted["action_result"]["record_id"],
            "scope": "session",
            "summary": "Prefer summary-only memory recall for planner context.",
            "source_refs": [],
            "provenance": {
                "run_id": source_run["run_id"],
                "session_id": session["session_id"],
                "execution_id": promoted["action_result"]["execution_id"],
                "action_type": "write_memory",
                "promotion_source_record_id": source["action_result"]["record_id"],
                "promotion_source_scope": "run",
            },
            "quality": "candidate",
        }
    ]
    assert "SECRET_SESSION_PROMOTION_PAYLOAD" not in repr(recalled)
    _assert_no_forbidden_content_keys(recalled)


def test_agent_loop_session_memory_query_does_not_cross_sessions(tmp_path):
    api = server.InProcessServer(tmp_path)
    first_session = api.create_session()
    first_run = api.create_run(first_session["session_id"], goal="capture durable preference")
    source = api.run_agent_loop_step(
        first_run["run_id"],
        {
            "step": "record_turn_memory",
            "scope": "run",
            "summary": "Only the first session should recall this preference.",
            "content": {"kind": "turn_state", "text": "private first session preference"},
            "source_refs": [],
            "quality": "candidate",
        },
    )
    api.run_agent_loop_step(
        first_run["run_id"],
        {
            "step": "promote_run_memory",
            "source_record_id": source["action_result"]["record_id"],
            "summary": "Only the first session should recall this preference.",
            "reason": "session-local continuity only",
        },
    )
    second_session = api.create_session()
    second_run = api.create_run(second_session["session_id"], goal="another session")

    recalled = api.run_agent_loop_step(
        second_run["run_id"],
        {
            "step": "query_memory",
            "scope": "session",
            "query": "first session preference",
        },
    )

    assert recalled["action_result"]["status"] == "ok"
    assert recalled["action_result"]["results"] == []
