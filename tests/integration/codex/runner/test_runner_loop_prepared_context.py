from __future__ import annotations

import json

from ..helpers import _assistant_message, _write_session
from isotope.features.supervisor.planner.decision_requests import record_decision_request
from isotope.features.supervisor.runner import main as supervisor_main


def test_codex_supervisor_loop_prepares_action_context_from_state_root(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_session(
        codex_home,
        "2026/05/16/rollout-blocked.jsonl",
        session_id="blocked-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:20Z",
                "实现路径有冲突，需要用户拍板。",
            )
        ],
    )
    record_decision_request(
        codex_home=codex_home,
        action={
            "session_id": "blocked-session",
            "target_name": "blocked-worker",
            "question": "保留兼容层还是直接迁移？",
            "reason": "Codex 明确请求用户拍板。",
            "context_status": "conflict",
            "codex_requested_decision": True,
            "instructions_exhausted": True,
        },
    )
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)
    seen_prepared_decision_fact = False

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            nonlocal seen_prepared_decision_fact
            payload = json.loads(messages[1]["content"])
            prepared = payload["prepared_action_context"]
            fact_by_kind = {
                fact["kind"]: fact for fact in prepared.get("facts", [])
            }
            assert fact_by_kind["decision_requests"]["target_names"] == [
                "blocked-worker"
            ]
            assert fact_by_kind["decision_requests"]["context_statuses"] == {
                "conflict": 1
            }
            seen_prepared_decision_fact = True
            return json.dumps(
                {
                    "kind": "monitor",
                    "reason": "已读到 prepared action context，等待用户拍板。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: DeterministicProvider(),
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )

    exit_code = supervisor_main(
        [
            "loop",
            "--codex-home",
            str(codex_home),
            "--workspace-root",
            str(workspace),
            "--goal",
            "处理 blocked-worker 的用户拍板。",
            "--iterations",
            "1",
            "--interval",
            "1",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert seen_prepared_decision_fact is True
    assert payload["supervisor_action"]["kind"] == "monitor"
    assert payload["supervisor_action_planner"] == {
        "source": "llm",
        "reason": "prepared_context",
    }
    assert payload["llm_action"] == payload["supervisor_action"]
