from __future__ import annotations

import pytest

from isotope.features.supervisor.agent_group.workspace.coordination.candidates import (
    CodexGroupCandidate,
    candidate_to_agent_message,
    parse_codex_group_candidate,
)


def test_parse_codex_group_candidate_respond_marker() -> None:
    candidate = parse_codex_group_candidate(
        text=(
            "工程验证完成。\n\n"
            "GROUP_CHAT_INTENT: respond\n"
            "GROUP_CHAT_SUMMARY: 工程侧已经完成镜像 smoke，建议科研侧确认 schema。\n"
            "GROUP_CHAT_PRIORITY: 70\n"
            "GROUP_CHAT_STATE_LOCK: rna:submission\n"
        ),
        workspace_id="workspace_1",
        channel_id="channel_1",
        member_id="member_training",
        display_name="RNA训练",
        resume_session_id="session_training",
        event_index=42,
        transcript_ref={"session_id": "session_training", "event_index": 42},
    )

    assert candidate == CodexGroupCandidate(
        candidate_id="candidate_member_training_session_training_42_respond",
        workspace_id="workspace_1",
        channel_id="channel_1",
        member_id="member_training",
        display_name="RNA训练",
        resume_session_id="session_training",
        event_index=42,
        intent="respond",
        summary="工程侧已经完成镜像 smoke，建议科研侧确认 schema。",
        priority=70,
        state_lock="rna:submission",
        transcript_ref={"session_id": "session_training", "event_index": 42},
    )


def test_parse_codex_group_candidate_silent_marker() -> None:
    candidate = parse_codex_group_candidate(
        text=(
            "已读。\n\n"
            "GROUP_CHAT_INTENT: silent\n"
            "GROUP_CHAT_SUMMARY: 当前只是状态同步，我继续原工作。\n"
            "GROUP_CHAT_PRIORITY: 0\n"
        ),
        workspace_id="workspace_1",
        channel_id="channel_1",
        member_id="member_research",
        display_name="rna探索",
        resume_session_id="session_research",
        event_index=9,
        transcript_ref={"session_id": "session_research", "event_index": 9},
    )

    assert candidate.intent == "silent"
    assert candidate.summary == "当前只是状态同步，我继续原工作。"
    assert candidate.priority == 0
    assert candidate.state_lock is None


def test_parse_codex_group_candidate_absent_marker_returns_none() -> None:
    assert (
        parse_codex_group_candidate(
            text="普通 Codex 工作输出，不应进入群聊。",
            workspace_id="workspace_1",
            channel_id="channel_1",
            member_id="member_training",
            display_name="RNA训练",
            resume_session_id="session_training",
            event_index=3,
            transcript_ref={"session_id": "session_training", "event_index": 3},
        )
        is None
    )


def test_parse_codex_group_candidate_rejects_bad_intent() -> None:
    with pytest.raises(ValueError, match="GROUP_CHAT_INTENT"):
        parse_codex_group_candidate(
            text=(
                "GROUP_CHAT_INTENT: maybe\n"
                "GROUP_CHAT_SUMMARY: bad\n"
                "GROUP_CHAT_PRIORITY: 1\n"
            ),
            workspace_id="workspace_1",
            channel_id="channel_1",
            member_id="member_training",
            display_name="RNA训练",
            resume_session_id="session_training",
            event_index=3,
            transcript_ref={"session_id": "session_training", "event_index": 3},
        )


def test_candidate_to_agent_message_preserves_visibility_metadata() -> None:
    candidate = CodexGroupCandidate(
        candidate_id="candidate_member_training_session_training_42_respond",
        workspace_id="workspace_1",
        channel_id="channel_1",
        member_id="member_training",
        display_name="RNA训练",
        resume_session_id="session_training",
        event_index=42,
        intent="respond",
        summary="工程侧 ready。",
        priority=50,
        state_lock="rna:submission",
        transcript_ref={"session_id": "session_training", "event_index": 42},
    )

    message = candidate_to_agent_message(candidate)

    assert message.message_id == candidate.candidate_id
    assert message.agent_id == "member_training"
    assert message.intent == "respond"
    assert message.summary == "工程侧 ready。"
    assert message.priority == 50
    assert message.state_lock == "rna:submission"
    assert message.metadata == {
        "source": "codex_group_candidate",
        "workspace_id": "workspace_1",
        "channel_id": "channel_1",
        "display_name": "RNA训练",
        "resume_session_id": "session_training",
        "event_index": 42,
        "transcript_ref": {"session_id": "session_training", "event_index": 42},
    }
