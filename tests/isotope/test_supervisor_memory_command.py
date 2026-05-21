from __future__ import annotations

import json
from dataclasses import asdict

from isotope.features.supervisor import runner
from isotope.platform.schemas.memory import MemoryRecord


def test_supervisor_memory_command_reports_store_summary_without_content(tmp_path, capsys):
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    _write_memory_record(
        memory_dir,
        MemoryRecord(
            memory_id="mem_run",
            scope="run",
            content={"secret": "raw memory content must not leak"},
            summary="Run memory summary.",
            source_refs=[{"ref_type": "artifact", "artifact_id": "artifact_001"}],
            provenance={
                "run_id": "run_001",
                "execution_id": "exec_001",
                "action_type": "write_memory",
            },
            created_at="2026-05-21T00:00:00Z",
            supersedes=[],
            quality="candidate",
        ),
    )
    _write_memory_record(
        memory_dir,
        MemoryRecord(
            memory_id="mem_session",
            scope="session",
            content={"note": "another raw memory payload"},
            summary="Session memory summary.",
            source_refs=[],
            provenance={
                "run_id": "run_002",
                "execution_id": "exec_002",
                "action_type": "write_memory",
            },
            created_at="2026-05-22T00:00:00Z",
            supersedes=["mem_old"],
            quality="verified",
        ),
    )

    assert runner.main(["memory", "--root", str(tmp_path), "--json"]) == 0

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["status"] == "ok"
    assert payload["summary"] == {
        "total": 2,
        "by_scope": {"run": 1, "session": 1, "thread": 0},
        "by_quality": {"candidate": 1, "verified": 1},
        "hidden_records": 0,
    }
    assert payload["records"][0]["record_id"] == "mem_session"
    assert payload["records"][0]["summary"] == "Session memory summary."
    assert payload["records"][0]["scope"] == "session"
    assert "content" not in payload["records"][0]
    assert "raw memory" not in output


def test_supervisor_memory_command_plain_output_is_human_readable(tmp_path, capsys):
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    _write_memory_record(
        memory_dir,
        MemoryRecord(
            memory_id="mem_thread",
            scope="thread",
            content={"raw": "hidden"},
            summary="Thread summary.",
            source_refs=[],
            provenance={
                "run_id": "run_003",
                "execution_id": "exec_003",
                "action_type": "write_memory",
            },
            created_at="2026-05-22T01:00:00Z",
            supersedes=[],
            quality="candidate",
        ),
    )

    assert runner.main(["memory", "--root", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "Memory store" in output
    assert "total: 1" in output
    assert "mem_thread / thread / candidate / Thread summary." in output
    assert "hidden" not in output


def _write_memory_record(memory_dir, record: MemoryRecord) -> None:
    (memory_dir / f"{record.memory_id}.json").write_text(
        json.dumps(asdict(record), sort_keys=True),
        encoding="utf-8",
    )
