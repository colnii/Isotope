from __future__ import annotations

import pytest

from isotope.features.supervisor.planner.goal_queue import record_supervisor_goal


def test_desktop_route_helpers_parse_public_desktop_paths():
    from isotope.features.supervisor.web.routes.desktop import (
        desktop_approval_resolve_id,
        desktop_chat_history,
        desktop_terminal_allowed_commands,
        desktop_terminal_approval_mode,
    )
    from isotope.features.supervisor.web.routes.desktop_artifacts import (
        desktop_screen_artifact_content_id,
    )

    assert (
        desktop_approval_resolve_id("/desktop/approvals/approval%201/resolve")
        == "approval 1"
    )
    assert desktop_approval_resolve_id("/desktop/approvals/bad%2Fid/resolve") is None
    assert (
        desktop_screen_artifact_content_id("/desktop/artifacts/artifact%201/screen-content")
        == "artifact 1"
    )
    assert (
        desktop_screen_artifact_content_id("/desktop/artifacts/bad%2Fid/screen-content")
        is None
    )
    assert desktop_chat_history(
        [
            {"role": "system", "content": "ignored"},
            {"role": "user", "content": "  hello  "},
            {"role": "assistant", "content": ""},
            {"role": "assistant", "content": "ok"},
        ]
    ) == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "ok"},
    ]
    assert desktop_terminal_approval_mode(None) == "allowlist"
    assert desktop_terminal_approval_mode("yolo") == "yolo"
    assert desktop_terminal_allowed_commands([" python3 ", "python3", "git"]) == [
        "python3",
        "git",
    ]
    with pytest.raises(ValueError, match="terminal_approval_mode"):
        desktop_terminal_approval_mode("unsafe")
    with pytest.raises(ValueError, match="terminal_allowed_commands"):
        desktop_terminal_allowed_commands([""])


def test_goal_route_helpers_validate_candidate_write_payloads():
    from isotope.features.supervisor.web.routes.goals import goal_plan_candidates

    assert goal_plan_candidates(
        {
            "candidates": [
                {"goal": "  Ship screen viewer  ", "target_name": " desktop "},
                {"goal": ""},
                "ignored",
            ]
        }
    ) == [{"goal": "Ship screen viewer", "target_name": "desktop"}]
    with pytest.raises(ValueError, match="candidates must not be empty"):
        goal_plan_candidates({"candidates": []})


def test_service_action_routes_have_their_own_route_inventory():
    from isotope.features.supervisor.web.routes.service_actions import SERVICE_ACTION_PATHS

    assert SERVICE_ACTION_PATHS == {
        "/daemon/start",
        "/daemon/stop",
        "/watcher/start",
        "/watcher/stop",
    }


def test_dashboard_route_helpers_own_state_projection_payloads(tmp_path):
    from isotope.features.supervisor.web.routes.dashboard import active_goal_dicts_for_codex_home

    goal = record_supervisor_goal(
        codex_home=tmp_path,
        cwd=tmp_path,
        goal="Split supervisor web routes",
    )

    assert active_goal_dicts_for_codex_home(tmp_path)[0]["goal_id"] == goal.goal_id
