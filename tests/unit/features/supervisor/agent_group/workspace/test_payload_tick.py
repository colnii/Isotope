from __future__ import annotations

import json
from pathlib import Path

from isotope.features.supervisor.agent_group.store import AgentGroupStore
from isotope.features.supervisor.agent_group.workspace import api
from isotope.features.supervisor.agent_group.workspace import dispatcher
from isotope.features.supervisor.agent_group.workspace.store import AgentWorkspaceStore
from isotope.features.supervisor.registry.records import ManagedCodexRecord


def test_workspace_payload_is_read_only_and_does_not_import_codex_member_replies(tmp_path):
    codex_home, workspace, channel, member = _workspace_with_training_candidate(tmp_path)
    store = AgentWorkspaceStore(codex_home)

    payload = api.workspace_payload(codex_home, workspace.workspace_id)

    assert payload["imports"] == []
    assert payload["inbox_drains"] == []
    assert payload["messages"] == []
    loaded = store.list_channel_members(workspace.workspace_id, channel.channel_id)[0]
    assert loaded.member_id == member.member_id
    assert loaded.transcript_policy["last_imported_event_index"] == 1


def test_workspace_tick_imports_codex_member_replies_explicitly(tmp_path):
    codex_home, workspace, channel, member = _workspace_with_training_candidate(tmp_path)

    payload = api.workspace_tick_payload(codex_home, workspace.workspace_id)

    assert payload["imports"] == [
        {
            "member_id": member.member_id,
            "display_name": "RNA训练",
            "status": "candidate_imported",
            "imported_count": 1,
            "candidate_count": 1,
            "published_count": 1,
            "last_imported_event_index": 2,
        }
    ]
    assert [
        (message["from_actor"], message["message_type"], message["summary"])
        for message in payload["messages"]
    ] == [
        (
            member.member_id,
            "member_observation",
            "工程侧已经开始验证训练链路。",
        )
    ]


def test_workspace_payload_does_not_relay_or_resume_codex_members(
    tmp_path,
    monkeypatch,
):
    codex_home, workspace, channel, research_member, training_member = (
        _workspace_with_research_candidate_and_training_member(tmp_path)
    )
    store = AgentWorkspaceStore(codex_home)
    resumed_calls: list[dict[str, object]] = []

    def fake_resume_managed_codex(**kwargs):
        resumed_calls.append(kwargs)
        return _managed_record(codex_home, kwargs, index=len(resumed_calls))

    monkeypatch.setattr(dispatcher, "resume_managed_codex", fake_resume_managed_codex)

    payload = api.workspace_payload(codex_home, workspace.workspace_id)

    assert payload["imports"] == []
    assert payload["inbox_drains"] == []
    assert AgentGroupStore(codex_home).list_groups() == []
    assert resumed_calls == []
    assert payload["inbox"]["pending_counts"].get(training_member.member_id, 0) == 0
    loaded = store.list_channel_members(workspace.workspace_id, channel.channel_id)
    by_id = {member.member_id: member for member in loaded}
    assert by_id[research_member.member_id].transcript_policy["last_imported_event_index"] == 1


def test_workspace_tick_relays_imported_member_reply_to_other_codex_members(
    tmp_path,
    monkeypatch,
):
    codex_home, workspace, _, research_member, training_member = (
        _workspace_with_research_candidate_and_training_member(tmp_path)
    )
    resumed_calls: list[dict[str, object]] = []

    def fake_resume_managed_codex(**kwargs):
        resumed_calls.append(kwargs)
        return _managed_record(codex_home, kwargs, index=len(resumed_calls))

    monkeypatch.setattr(dispatcher, "resume_managed_codex", fake_resume_managed_codex)

    payload = api.workspace_tick_payload(codex_home, workspace.workspace_id)

    assert payload["imports"][0]["member_id"] == research_member.member_id
    assert payload["imports"][0]["status"] == "candidate_imported"
    group = AgentGroupStore(codex_home).list_groups()[0]
    runtime_messages = AgentGroupStore(codex_home).list_group_messages(group.group_id)
    assert [(message.from_member, message.message_type, message.summary) for message in runtime_messages[-1:]] == [
        (research_member.member_id, "reply", "科研侧建议先做 schema readiness 审计。")
    ]
    assert [call["session_id"] for call in resumed_calls] == [training_member.resume_session_id]
    assert "待处理群聊消息" in str(resumed_calls[0]["prompt"])
    assert "科研侧建议先做 schema readiness 审计。" in str(resumed_calls[0]["prompt"])
    assert payload["inbox"]["pending_counts"].get(training_member.member_id, 0) == 0
    assert "session_research" not in [call["session_id"] for call in resumed_calls]


def _workspace_with_training_candidate(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace_root = tmp_path / "AI_Camp_RNA_2026"
    workspace_root.mkdir()
    session_path = tmp_path / "session.jsonl"
    write_jsonl(
        session_path,
        [
            {"type": "session_meta", "payload": {"id": "session_training"}},
            _message_row("user", "收到群聊消息。", timestamp="2026-06-12T00:00:00Z"),
            _candidate_row(
                summary="工程侧已经开始验证训练链路。",
                timestamp="2026-06-12T00:00:01Z",
            ),
        ],
    )
    store = AgentWorkspaceStore(codex_home)
    workspace = store.ensure_default_workspace(root_path=workspace_root)
    channel = store.list_channels(workspace.workspace_id)[0]
    member = store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="RNA训练",
        role="工程推进",
        goal="继续训练。",
        send_policy="auto",
        resume_session_id="session_training",
        source_path=str(session_path),
        managed_record_id=None,
    )
    store.update_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        member_id=member.member_id,
        transcript_policy={
            **member.transcript_policy,
            "last_imported_event_index": 1,
        },
    )
    return codex_home, workspace, channel, member


def _workspace_with_research_candidate_and_training_member(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace_root = tmp_path / "AI_Camp_RNA_2026"
    workspace_root.mkdir()
    session_path = tmp_path / "research.jsonl"
    write_jsonl(
        session_path,
        [
            {"type": "session_meta", "payload": {"id": "session_research"}},
            _message_row("user", "请同步当前进展。", timestamp="2026-06-12T00:00:00Z"),
            _candidate_row(
                summary="科研侧建议先做 schema readiness 审计。",
                timestamp="2026-06-12T00:00:01Z",
            ),
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
        goal="寻找全局优化点。",
        send_policy="auto",
        resume_session_id="session_research",
        source_path=str(session_path),
        managed_record_id=None,
    )
    training_member = store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="RNA训练",
        role="工程推进",
        goal="继续训练和提交链路。",
        send_policy="auto",
        resume_session_id="session_training",
        source_path=None,
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
    return codex_home, workspace, channel, research_member, training_member


def _message_row(role: str, content: str, *, timestamp: str) -> dict[str, object]:
    return {
        "type": "response_item",
        "timestamp": timestamp,
        "payload": {
            "type": "message",
            "role": role,
            "content": content,
        },
    }


def _candidate_row(*, summary: str, timestamp: str) -> dict[str, object]:
    return _message_row(
        "assistant",
        (
            f"{summary}\n\n"
            "GROUP_CHAT_INTENT: respond\n"
            f"GROUP_CHAT_SUMMARY: {summary}\n"
            "GROUP_CHAT_PRIORITY: 80\n"
        ),
        timestamp=timestamp,
    )


def _managed_record(
    codex_home: Path,
    kwargs: dict[str, object],
    *,
    index: int,
) -> ManagedCodexRecord:
    return ManagedCodexRecord(
        record_id=f"managed-{index}",
        name=str(kwargs["name"]),
        cwd=str(kwargs["cwd"]),
        prompt=str(kwargs["prompt"]),
        command=("codex", "resume", str(kwargs["session_id"])),
        pid=1234 + index,
        started_at="2026-06-12T00:00:00Z",
        log_path=str(codex_home / "supervisor" / "logs" / f"managed-{index}.log"),
        status="resumed",
        backend="codex_exec_resume",
        resume_session_id=str(kwargs["session_id"]),
    )


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
