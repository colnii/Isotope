from __future__ import annotations

import json

from isotope.features.supervisor.agent_group.codex_chat.api import transcript_payload
from isotope.features.supervisor.agent_group.codex_chat.contracts import (
    ConnectedCodexMember,
)
from isotope.features.supervisor.agent_group.codex_chat.runtime import (
    CodexGroupChatRuntime,
)
from isotope.features.supervisor.agent_group.runtime import AgentGroupRuntime


def test_agent_group_codex_chat_local_two_session_smoke(tmp_path):
    codex_home = tmp_path / ".codex"
    research_session = "019e9830-8a72-7ff1-8b2e-310b9d66372b"
    engineering_session = "019e9830-8a72-7ff1-8b2e-310b9d66372c"
    write_session(codex_home, research_session, "research update")
    write_session(codex_home, engineering_session, "engineering update")

    group = AgentGroupRuntime(codex_home).create_group(
        title="RNA Codex group",
        goal="Coordinate RNA research and engineering.",
        member_specs=[
            {
                "name": "coordinator",
                "role": "Coordinate.",
                "goal": "Keep lanes synced.",
            }
        ],
        initial_message="Open the group.",
    )
    group_id = group["group"]["group_id"]
    chat_runtime = CodexGroupChatRuntime(codex_home)
    chat_runtime.store.save_member(
        member(group_id, "member_research", "Research Codex", research_session)
    )
    chat_runtime.store.save_member(
        member(group_id, "member_engineering", "Engineering Codex", engineering_session)
    )

    research_page = transcript_payload(
        codex_home,
        session_id=research_session,
        offset=0,
        limit=20,
        include_raw=False,
    )
    stop = chat_runtime.terminate_member(
        group_id=group_id,
        member_id="member_research",
        reason="User pressed member Stop.",
    )

    assert research_page["events"][-1]["text"] == "research update"
    assert stop["status"] == "terminated"
    members = {
        saved.member_id: saved for saved in chat_runtime.store.list_members(group_id)
    }
    assert members["member_research"].status == "terminated"


def write_session(codex_home, session_id: str, assistant_text: str) -> None:
    path = (
        codex_home
        / "sessions"
        / "2026"
        / "06"
        / "12"
        / f"rollout-{session_id}.jsonl"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "type": "session_meta",
            "timestamp": "2026-06-12T00:00:00Z",
            "payload": {
                "id": session_id,
                "cwd": "/home/lumber/Github/AI_Camp_RNA_2026",
            },
        },
        {
            "type": "response_item",
            "timestamp": "2026-06-12T00:00:01Z",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": assistant_text,
            },
        },
    ]
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def member(
    group_id: str,
    member_id: str,
    display_name: str,
    session_id: str,
) -> ConnectedCodexMember:
    return ConnectedCodexMember(
        member_id=member_id,
        group_id=group_id,
        display_name=display_name,
        member_kind="codex_session",
        role="Coordinate lane.",
        goal="Keep the lane moving.",
        send_policy="confirm",
        status="active",
        resume_session_id=session_id,
        source_path=None,
        managed_record_id=None,
        transcript_policy={},
        created_at="2026-06-12T00:00:00Z",
        updated_at="2026-06-12T00:00:00Z",
    )
