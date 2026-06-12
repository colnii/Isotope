from __future__ import annotations

import json
from pathlib import Path

from isotope.features.supervisor.agent_group.workspace import api
from isotope.features.supervisor.agent_group.workspace import dispatcher
from isotope.features.supervisor.agent_group.workspace.store import AgentWorkspaceStore
from isotope.features.supervisor.registry.records import ManagedCodexRecord


def test_relayed_member_reply_is_not_relayed_back_to_source(tmp_path, monkeypatch):
    codex_home = tmp_path / ".codex"
    workspace_root = tmp_path / "AI_Camp_RNA_2026"
    workspace_root.mkdir()
    research_path = tmp_path / "research.jsonl"
    training_path = tmp_path / "training.jsonl"
    write_jsonl(
        research_path,
        [
            {"type": "session_meta", "payload": {"id": "session_research"}},
            _message_row("user", "请和训练侧完成三次握手。", index=1),
            _message_row("assistant", "科研侧 SYN：我已准备好同步 schema 判断。", index=2),
        ],
    )
    write_jsonl(
        training_path,
        [
            {"type": "session_meta", "payload": {"id": "session_training"}},
            _message_row("user", "等待群聊转发。", index=1),
        ],
    )
    store = AgentWorkspaceStore(codex_home)
    workspace = store.ensure_default_workspace(root_path=workspace_root)
    channel = store.list_channels(workspace.workspace_id)[0]
    research_member = store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="rna探索",
        role="科研探索",
        goal="提出科研判断。",
        send_policy="auto",
        resume_session_id="session_research",
        source_path=str(research_path),
        managed_record_id=None,
    )
    training_member = store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="RNA训练",
        role="工程推进",
        goal="验证训练链路。",
        send_policy="auto",
        resume_session_id="session_training",
        source_path=str(training_path),
        managed_record_id=None,
    )
    store.update_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        member_id=research_member.member_id,
        transcript_policy={
            **research_member.transcript_policy,
            "last_imported_event_index": 1,
        },
    )
    store.update_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        member_id=training_member.member_id,
        transcript_policy={
            **training_member.transcript_policy,
            "last_imported_event_index": 1,
        },
    )
    resumed_calls: list[dict[str, object]] = []

    def fake_resume_managed_codex(**kwargs):
        resumed_calls.append(kwargs)
        return ManagedCodexRecord(
            record_id=f"managed-{len(resumed_calls)}",
            name=str(kwargs["name"]),
            cwd=str(kwargs["cwd"]),
            prompt=str(kwargs["prompt"]),
            command=("codex", "resume", str(kwargs["session_id"])),
            pid=1234 + len(resumed_calls),
            started_at="2026-06-12T00:00:00Z",
            log_path=str(
                codex_home
                / "supervisor"
                / "logs"
                / f"managed-{len(resumed_calls)}.log"
            ),
            status="resumed",
            backend="codex_exec_resume",
            resume_session_id=str(kwargs["session_id"]),
        )

    monkeypatch.setattr(dispatcher, "resume_managed_codex", fake_resume_managed_codex)

    first_payload = api.workspace_payload(codex_home, workspace.workspace_id)

    assert first_payload["imports"][0]["member_id"] == research_member.member_id
    assert [call["session_id"] for call in resumed_calls] == ["session_training"]
    store = AgentWorkspaceStore(codex_home)
    messages = store.list_messages(workspace.workspace_id, "channel", channel.channel_id)
    research_observation = next(
        message
        for message in messages
        if message.message_type == "member_observation"
        and message.from_actor == research_member.member_id
    )
    sent_to_training = next(
        message
        for message in messages
        if message.message_type == "sent_to_member"
        and message.to_actor == training_member.member_id
    )
    assert (
        sent_to_training.payload["relay_source_message_id"]
        == research_observation.message_id
    )
    assert sent_to_training.payload["relay_depth"] == 1
    assert sent_to_training.payload["trigger_kind"] == "member_observation_relay"

    write_jsonl(
        training_path,
        [
            {"type": "session_meta", "payload": {"id": "session_training"}},
            _message_row("user", "等待群聊转发。", index=1),
            _message_row("assistant", "训练侧 ACK：已收到科研侧 schema 判断。", index=2),
        ],
    )

    second_payload = api.workspace_payload(codex_home, workspace.workspace_id)

    assert second_payload["imports"][0]["member_id"] == training_member.member_id
    assert second_payload["relays"] == []
    assert [call["session_id"] for call in resumed_calls] == ["session_training"]
    store = AgentWorkspaceStore(codex_home)
    messages = store.list_messages(workspace.workspace_id, "channel", channel.channel_id)
    training_observation = next(
        message
        for message in messages
        if message.message_type == "member_observation"
        and message.from_actor == training_member.member_id
    )
    assert training_observation.payload["relay_depth"] == 1
    assert (
        training_observation.payload["reply_to_relay_source_message_id"]
        == research_observation.message_id
    )
    assert not [
        message
        for message in messages
        if message.message_type == "sent_to_member"
        and message.to_actor == research_member.member_id
        and message.payload.get("relay_source_message_id")
        == training_observation.message_id
    ]


def _message_row(role: str, content: str, *, index: int) -> dict[str, object]:
    return {
        "type": "response_item",
        "timestamp": f"2026-06-12T00:00:0{index}Z",
        "payload": {
            "type": "message",
            "role": role,
            "content": content,
        },
    }


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
