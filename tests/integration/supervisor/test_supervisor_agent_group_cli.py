from __future__ import annotations

import json

from isotope.features.supervisor import runner


class FakeSummaryProvider:
    def summarize(self, messages: list[dict[str, str]]) -> str:
        return "CLI fake agent reply."


def test_supervisor_agent_group_create_tick_and_list_cli(
    tmp_path,
    capsys,
    monkeypatch,
):
    monkeypatch.setattr(
        "isotope.features.supervisor.agent_group.runtime.resolve_summary_provider_from_env",
        lambda: FakeSummaryProvider(),
    )

    assert (
        runner.main(
            [
                "agent-group",
                "create",
                "--state-root",
                str(tmp_path),
                "--title",
                "Feature group",
                "--goal",
                "Discuss group chat.",
                "--member",
                "planner:Plan work.:Find first steps.",
                "--member",
                "reviewer:Review work.:Find missing tests.",
                "--message",
                "Start with risks.",
                "--json",
            ]
        )
        == 0
    )
    created = json.loads(capsys.readouterr().out)
    group_id = created["group"]["group_id"]
    assert created["status"] == "ok"
    assert [member["name"] for member in created["members"]] == ["planner", "reviewer"]

    assert (
        runner.main(
            [
                "agent-group",
                "tick",
                "--state-root",
                str(tmp_path),
                "--group",
                group_id,
                "--json",
            ]
        )
        == 0
    )
    ticked = json.loads(capsys.readouterr().out)
    assert ticked["status"] == "ok"
    assert ticked["turn"]["status"] == "selected"

    assert (
        runner.main(
            [
                "agent-group",
                "list",
                "--state-root",
                str(tmp_path),
                "--json",
            ]
        )
        == 0
    )
    listed = json.loads(capsys.readouterr().out)
    assert listed["summary"]["group_count"] == 1
    assert listed["groups"][0]["group_id"] == group_id


def test_supervisor_agent_group_send_cli(tmp_path, capsys):
    assert (
        runner.main(
            [
                "agent-group",
                "create",
                "--state-root",
                str(tmp_path),
                "--goal",
                "Discuss group chat.",
                "--member",
                "planner:Plan work.:Find first steps.",
                "--message",
                "Start.",
                "--json",
            ]
        )
        == 0
    )
    group_id = json.loads(capsys.readouterr().out)["group"]["group_id"]

    assert (
        runner.main(
            [
                "agent-group",
                "send",
                "--state-root",
                str(tmp_path),
                "--group",
                group_id,
                "--message",
                "Focus on the first test.",
                "--json",
            ]
        )
        == 0
    )
    sent = json.loads(capsys.readouterr().out)
    assert sent["message"]["summary"] == "Focus on the first test."
