import pytest

from isotope import models


def _valid_memory_record_kwargs(**overrides):
    record = {
        "memory_id": "mem_001",
        "scope": "thread",
        "content": {
            "kind": "structured_note",
            "text": "Learner prefers worked examples.",
        },
        "summary": "Learner prefers worked examples.",
        "source_refs": [
            {
                "ref_type": "artifact",
                "run_id": "run_001",
                "artifact_id": "artifact_001",
            }
        ],
        "provenance": {
            "run_id": "run_001",
            "execution_id": "exec_001",
            "action_type": "write_memory",
        },
        "created_at": "2026-04-29T00:00:00Z",
        "supersedes": [],
        "quality": "candidate",
    }
    record.update(overrides)
    return record


def test_memory_record_implementation_shape_exists():
    assert hasattr(models, "MemoryRecord")


def test_valid_memory_record_requires_structured_content_and_provenance():
    record = models.MemoryRecord(**_valid_memory_record_kwargs())

    assert record.memory_id == "mem_001"
    assert record.scope == "thread"
    assert record.content == {
        "kind": "structured_note",
        "text": "Learner prefers worked examples.",
    }
    assert record.summary == "Learner prefers worked examples."
    assert record.source_refs == [
        {
            "ref_type": "artifact",
            "run_id": "run_001",
            "artifact_id": "artifact_001",
        }
    ]
    assert record.provenance == {
        "run_id": "run_001",
        "execution_id": "exec_001",
        "action_type": "write_memory",
    }
    assert record.created_at == "2026-04-29T00:00:00Z"
    assert record.supersedes == []
    assert record.quality == "candidate"


def test_memory_record_content_cannot_be_raw_string_transcript():
    with pytest.raises((TypeError, ValueError), match="content|dict|structured"):
        models.MemoryRecord(
            **_valid_memory_record_kwargs(content="raw transcript dump")
        )


@pytest.mark.parametrize("missing_field", ["run_id", "execution_id", "action_type"])
def test_memory_record_provenance_requires_execution_action_and_run(missing_field):
    provenance = dict(_valid_memory_record_kwargs()["provenance"])
    provenance.pop(missing_field)

    with pytest.raises((TypeError, ValueError), match=missing_field):
        models.MemoryRecord(**_valid_memory_record_kwargs(provenance=provenance))


def test_memory_record_source_refs_must_be_list():
    with pytest.raises((TypeError, ValueError), match="source_refs|list"):
        models.MemoryRecord(
            **_valid_memory_record_kwargs(source_refs="artifact://run_001/artifact_001")
        )


def test_memory_record_scope_is_limited_to_thread_run_or_session():
    with pytest.raises((TypeError, ValueError), match="scope|thread|run|session"):
        models.MemoryRecord(**_valid_memory_record_kwargs(scope="global"))


def test_memory_record_rejects_top_level_artifact_content():
    with pytest.raises((TypeError, ValueError), match="artifact_content|content"):
        models.MemoryRecord(
            **_valid_memory_record_kwargs(
                artifact_content="large raw artifact content should stay behind refs"
            )
        )
