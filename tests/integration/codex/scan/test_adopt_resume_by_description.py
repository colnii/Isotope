from __future__ import annotations

from pathlib import Path

from ..helpers import _assistant_message, _user_message, _write_session
from isotope.capabilities.runner import CapabilityRunner
from isotope.features.supervisor.registry import adopt_codex_session
from isotope.features.supervisor.registry.records import ManagedCodexRecord
from isotope.features.supervisor.registry.session_matcher import (
    match_codex_sessions_by_description,
)


AI4S_SESSION_ID = "019e9830-8a72-7ff1-8b2e-310b9d66372b"
DOCKER_SESSION_ID = "019dcdca-1d58-7f53-817d-003b9247b881"
MHR_SESSION_ID = "019e97a9-ffbd-7201-a213-4f5d4181a74d"


def _write_candidate_sessions(codex_home: Path, workspace: Path) -> None:
    ai4s = workspace / "AI_Camp_RNA_2026"
    docker = workspace / "AI_Camp_RNA_2026"
    game = workspace / "MonsterHunterRise"
    ai4s.mkdir(parents=True, exist_ok=True)
    game.mkdir(parents=True, exist_ok=True)
    _write_session(
        codex_home,
        "2026/06/05/rollout-ai4s-research.jsonl",
        session_id=AI4S_SESSION_ID,
        cwd=str(ai4s),
        events=[
            _user_message("2026-06-05T14:36:11Z", "复赛科研探索，找 ai4s RNA 全局优化方向"),
            _assistant_message("2026-06-05T15:20:00Z", "继续 P5 复赛联网 MSA 预检和科研队列。"),
        ],
    )
    _write_session(
        codex_home,
        "2026/06/05/rollout-docker-submit.jsonl",
        session_id=DOCKER_SESSION_ID,
        cwd=str(docker),
        events=[
            _user_message("2026-06-05T14:38:01Z", "阿里云镜像仓库 ai_camp_submit 怎么推送"),
            _assistant_message("2026-06-05T15:22:00Z", "Docker push 仍在上传复赛提交镜像。"),
        ],
    )
    _write_session(
        codex_home,
        "2026/06/05/rollout-mhr.jsonl",
        session_id=MHR_SESSION_ID,
        cwd=str(game),
        events=[
            _user_message("2026-06-05T12:03:12Z", "怪物猎人崛起多人 dps 插件"),
            _assistant_message("2026-06-05T12:06:51Z", "MHR Overlay 已配置。"),
        ],
    )


def test_session_matcher_selects_clear_description_match(tmp_path):
    codex_home = tmp_path / ".codex"
    _write_candidate_sessions(codex_home, tmp_path)

    result = match_codex_sessions_by_description(
        codex_home=codex_home,
        description="继续 ai4s 复赛科研探索那个多 agent 会话",
    )

    assert result.status == "clear"
    assert result.selected is not None
    assert result.selected.session_id == AI4S_SESSION_ID
    assert result.selected.score > 0
    assert [candidate.session_id for candidate in result.candidates[:2]] == [
        AI4S_SESSION_ID,
        DOCKER_SESSION_ID,
    ]


def test_session_matcher_returns_ambiguous_for_close_matches(tmp_path):
    codex_home = tmp_path / ".codex"
    _write_candidate_sessions(codex_home, tmp_path)

    result = match_codex_sessions_by_description(
        codex_home=codex_home,
        description="继续 ai camp 复赛",
    )

    assert result.status == "ambiguous"
    assert result.selected is None
    assert {candidate.session_id for candidate in result.candidates[:2]} == {
        AI4S_SESSION_ID,
        DOCKER_SESSION_ID,
    }


def test_session_matcher_returns_no_match_for_unrelated_description(tmp_path):
    codex_home = tmp_path / ".codex"
    _write_candidate_sessions(codex_home, tmp_path)

    result = match_codex_sessions_by_description(
        codex_home=codex_home,
        description="继续修 isotope qq chatbot 表情包",
    )

    assert result.status == "no_match"
    assert result.selected is None


def test_codex_operation_adopts_and_resumes_clear_description_match(
    tmp_path,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    _write_candidate_sessions(codex_home, tmp_path)
    resumed: list[dict[str, object]] = []

    def fake_resume_managed_codex(**kwargs):
        resumed.append(kwargs)
        return ManagedCodexRecord(
            record_id="managed-resume",
            name=kwargs["name"],
            cwd=str(kwargs["cwd"]),
            prompt=kwargs["prompt"],
            command=("codex", "resume", kwargs["session_id"]),
            pid=12345,
            started_at="2026-06-05T15:30:00+00:00",
            log_path=str(codex_home / "supervisor" / "logs" / "managed-resume.log"),
            status="resumed",
            backend="codex_exec_resume",
            resume_session_id=kwargs["session_id"],
        )

    monkeypatch.setattr(
        "isotope.capabilities.supervisor.resume_managed_codex",
        fake_resume_managed_codex,
        raising=False,
    )

    result = CapabilityRunner().run_capability(
        "supervisor.codex_operation",
        inputs={
            "operation": "adopt_resume_by_description",
            "state_root": str(codex_home),
            "description": "继续 ai4s 复赛科研探索那个多 agent 会话",
            "prompt": "继续推进科研探索并汇报状态",
        },
    )

    operation_result = result["operation_result"]
    assert operation_result["status"] == "resumed"
    assert operation_result["matched_session_id"] == AI4S_SESSION_ID
    assert operation_result["adopted"]["resume_session_id"] == AI4S_SESSION_ID
    assert operation_result["resumed"]["resume_session_id"] == AI4S_SESSION_ID
    assert resumed[0]["session_id"] == AI4S_SESSION_ID


def test_codex_operation_returns_ambiguous_candidates_without_resuming(
    tmp_path,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    _write_candidate_sessions(codex_home, tmp_path)
    resumed: list[dict[str, object]] = []

    def fake_resume_managed_codex(**kwargs):
        resumed.append(kwargs)
        raise AssertionError("ambiguous match must not resume")

    monkeypatch.setattr(
        "isotope.capabilities.supervisor.resume_managed_codex",
        fake_resume_managed_codex,
        raising=False,
    )

    result = CapabilityRunner().run_capability(
        "supervisor.codex_operation",
        inputs={
            "operation": "adopt_resume_by_description",
            "state_root": str(codex_home),
            "description": "继续 ai camp 复赛",
        },
    )

    operation_result = result["operation_result"]
    assert operation_result["status"] == "ambiguous"
    assert operation_result["matched_session_id"] is None
    assert {candidate["session_id"] for candidate in operation_result["candidates"][:2]} == {
        AI4S_SESSION_ID,
        DOCKER_SESSION_ID,
    }
    assert resumed == []


def test_codex_operation_reuses_existing_adopted_lane(tmp_path, monkeypatch):
    codex_home = tmp_path / ".codex"
    _write_candidate_sessions(codex_home, tmp_path)
    adopted = adopt_codex_session(
        codex_home=codex_home,
        name="ai4s-research",
        session_id=AI4S_SESSION_ID,
        prompt="接管已有科研会话",
    )
    resumed: list[dict[str, object]] = []

    def fake_resume_managed_codex(**kwargs):
        resumed.append(kwargs)
        return ManagedCodexRecord(
            record_id="managed-resume",
            name=kwargs["name"],
            cwd=str(kwargs["cwd"]),
            prompt=kwargs["prompt"],
            command=("codex", "resume", kwargs["session_id"]),
            pid=12345,
            started_at="2026-06-05T15:30:00+00:00",
            log_path=str(codex_home / "supervisor" / "logs" / "managed-resume.log"),
            status="resumed",
            backend="codex_exec_resume",
            resume_session_id=kwargs["session_id"],
        )

    monkeypatch.setattr(
        "isotope.capabilities.supervisor.resume_managed_codex",
        fake_resume_managed_codex,
        raising=False,
    )

    result = CapabilityRunner().run_capability(
        "supervisor.codex_operation",
        inputs={
            "operation": "adopt_resume_by_description",
            "state_root": str(codex_home),
            "description": "继续 ai4s 复赛科研探索那个多 agent 会话",
        },
    )

    operation_result = result["operation_result"]
    assert operation_result["status"] == "resumed"
    assert operation_result["adopted"]["record_id"] == adopted.record_id
    assert resumed[0]["name"] == "ai4s-research"


def test_codex_operation_manifest_exposes_description_resume_operation():
    capability = CapabilityRunner().describe_capability("supervisor.codex_operation")
    properties = capability["input_contract"]["properties"]

    assert "adopt_resume_by_description" in properties["operation"]["enum"]
    assert properties["description"]["type"] == "string"
    assert "Natural-language" in properties["description"]["description"]
    assert properties["prompt"]["type"] == "string"
