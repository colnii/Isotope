from __future__ import annotations

import json
from pathlib import Path

from isotope.features.supervisor.agent_group.workspace import api
from isotope.features.supervisor.agent_group.workspace import dispatcher
from isotope.features.supervisor.agent_group.workspace.coordination.inbox import (
    MemberInboxStore,
)
from isotope.features.supervisor.agent_group.workspace.store import AgentWorkspaceStore


def test_selected_member_reply_queues_for_running_peer_without_recursive_resume(
    tmp_path,
    monkeypatch,
):
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
            _message_row(
                "assistant",
                (
                    "科研侧建议先做 schema readiness 审计。\n\n"
                    "GROUP_CHAT_INTENT: respond\n"
                    "GROUP_CHAT_SUMMARY: 科研侧建议先做 schema readiness 审计。\n"
                    "GROUP_CHAT_PRIORITY: 80\n"
                ),
                index=2,
            ),
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
        managed_record_id="managed-training",
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
        status="running",
        transcript_policy={
            **training_member.transcript_policy,
            "last_imported_event_index": 1,
        },
    )
    resumed_calls: list[dict[str, object]] = []

    def fake_resume_managed_codex(**kwargs):
        resumed_calls.append(kwargs)
        raise AssertionError("running peer must receive inbox queue, not resume")

    monkeypatch.setattr(dispatcher, "resume_managed_codex", fake_resume_managed_codex)

    payload = api.workspace_payload(codex_home, workspace.workspace_id)

    assert payload["imports"][0]["member_id"] == research_member.member_id
    assert payload["imports"][0]["status"] == "candidate_imported"
    assert [call["session_id"] for call in resumed_calls] == []
    pending = MemberInboxStore(codex_home).list_pending(
        workspace.workspace_id,
        channel.channel_id,
        training_member.member_id,
    )
    assert len(pending) == 1
    assert pending[0].summary == "科研侧建议先做 schema readiness 审计。"
    assert payload["inbox"]["pending_counts"] == {training_member.member_id: 1}


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
