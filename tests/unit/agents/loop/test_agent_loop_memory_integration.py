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
    return api, run["run_id"]


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
    api, run_id = _new_run(tmp_path)
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
                "execution_id": recorded["action_result"]["execution_id"],
                "action_type": "write_memory",
            },
            "quality": "candidate",
        }
    ]
    assert recalled["control"]["progress"]["memory_records_total"] == 1
    _assert_no_forbidden_content_keys(recalled)


def test_agent_loop_query_memory_surfaces_controlled_expand_deferred_metadata(tmp_path):
    api, run_id = _new_run(tmp_path)
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
            "expand_budget": 2,
        },
    )

    assert recalled["action_result"]["status"] == "ok"
    assert recalled["action_result"]["controlled_expand"] == {
        "status": "deferred",
        "budget": 2,
        "content_policy": "summary_refs_provenance_only",
    }
    assert recalled["action_result"]["results"][0]["record_id"] == recorded["action_result"]["record_id"]
    assert "Hidden full memory payload" not in repr(recalled)
    _assert_no_forbidden_content_keys(recalled)
