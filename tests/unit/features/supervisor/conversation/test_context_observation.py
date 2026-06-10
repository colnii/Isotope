from __future__ import annotations

from pathlib import Path

from isotope.features.supervisor.commands.capacity.capacity_result import (
    agent_loop_json_result,
)
from isotope.features.supervisor.conversation_observations import (
    model_observation_from_agent_loop,
)


def test_request_context_projects_low_sensitive_model_observation(tmp_path) -> None:
    agent_loop = _agent_loop(
        {
            "capability_id": "supervisor.request_context",
            "status": "completed",
            "context_result": {
                "result_id": "ctx_123",
                "cwd": str(tmp_path),
                "query": "conversation loop request context",
                "backend": "bm25",
                "item_count": 1,
                "items": [
                    {
                        "path": "src/isotope/features/supervisor/conversation_loop.py",
                        "line": 157,
                        "title": "conversation_loop.py",
                        "text": "raw implementation text should not be projected",
                        "snippet": "repeated capacity handling lives in conversation_loop",
                        "score": 8.5,
                        "match_reason": "query terms matched",
                        "source_group": "source",
                    }
                ],
            },
        }
    )

    observation = model_observation_from_agent_loop(
        capacity_id="supervisor.request_context",
        status="ok",
        result={"agent_loop_executed": True},
        agent_loop=agent_loop,
        state_root=Path(tmp_path),
    )

    assert observation["result"] == {
        "kind": "request_context",
        "status": "completed",
        "query": "conversation loop request context",
        "backend": "bm25",
        "item_count": 1,
        "items": [
            {
                "path": "src/isotope/features/supervisor/conversation_loop.py",
                "line": 157,
                "title": "conversation_loop.py",
                "snippet": "repeated capacity handling lives in conversation_loop",
                "match_reason": "query terms matched",
                "source_group": "source",
            }
        ],
    }
    assert "raw implementation text" not in repr(observation)


def test_request_context_projects_public_agent_loop_result(tmp_path) -> None:
    result = agent_loop_json_result(
        {
            "agent_loop": _agent_loop(
                {
                    "capability_id": "supervisor.request_context",
                    "status": "completed",
                    "context_result": {
                        "result_id": "ctx_123",
                        "cwd": str(tmp_path),
                        "query": "project context",
                        "backend": "bm25",
                        "item_count": 1,
                        "items": [
                            {
                                "path": "README.md",
                                "line": 12,
                                "title": "README",
                                "text": "full text should not be projected",
                                "snippet": "Isotope is a local-first workbench.",
                                "score": 3.0,
                                "match_reason": "anchor",
                                "source_group": "docs",
                            }
                        ],
                    },
                }
            )
        }
    )

    assert result["agent_loop_request_context_status"] == "completed"
    assert result["agent_loop_request_context_query"] == "project context"
    assert result["agent_loop_request_context_backend"] == "bm25"
    assert result["agent_loop_request_context_item_count"] == 1
    assert result["agent_loop_request_context_items"] == [
        {
            "path": "README.md",
            "line": 12,
            "title": "README",
            "snippet": "Isotope is a local-first workbench.",
            "match_reason": "anchor",
            "source_group": "docs",
        }
    ]
    assert "full text" not in repr(result)


def _agent_loop(capability_run: dict) -> dict:
    return {
        "tick_result": {
            "tick_status": "executed",
            "planner_result": {
                "step_result": {
                    "action_result": {
                        "capability_run": capability_run,
                    }
                }
            },
        }
    }
