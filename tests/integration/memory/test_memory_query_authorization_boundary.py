import pytest

import isotope.platform.state.event_store as event_store
import isotope.platform.events.events as events
import isotope.memory as memory
import isotope.platform.state.projector as projector
import isotope.runtime.in_process as server


class ExplodingMemoryStore:
    def __init__(self):
        self.calls = []

    def list_records(self, *args, **kwargs):
        self.calls.append("list_records")
        raise AssertionError("memory query must not list records before authorization")

    def load_record(self, *args, **kwargs):
        self.calls.append("load_record")
        raise AssertionError("memory query must not load records before authorization")

    def read_content(self, *args, **kwargs):
        self.calls.append("read_content")
        raise AssertionError("memory query must not read full content without expand grant")

    def controlled_expand(self, *args, **kwargs):
        self.calls.append("controlled_expand")
        raise AssertionError("memory query must not controlled-expand without expand grant")


class PreviewOnlyMemoryStore:
    def __init__(self):
        self.calls = []
        self.records = [
            memory.MemoryRecord(
                memory_id="mem_preview_001",
                scope="run",
                content={
                    "kind": "structured_note",
                    "text": "hidden full memory content must not be returned",
                },
                summary="Resume from controlled expand preview.",
                source_refs=[{"ref_type": "artifact", "artifact_id": "artifact_001"}],
                provenance={
                    "run_id": "run_001",
                    "execution_id": "exec_001",
                    "action_type": "write_memory",
                },
                created_at="2026-05-27T00:00:00Z",
                supersedes=[],
                quality="candidate",
            )
        ]

    def list_records(self, *args, **kwargs):
        self.calls.append("list_records")
        return list(self.records)

    def load_record(self, *args, **kwargs):
        self.calls.append("load_record")
        raise AssertionError("preview-only query must not load full memory records")

    def read_content(self, *args, **kwargs):
        self.calls.append("read_content")
        raise AssertionError("preview-only query must not read full memory content")

    def controlled_expand(self, *args, **kwargs):
        self.calls.append("controlled_expand")
        raise AssertionError("preview-only query must not controlled-expand full content")


def test_unavailable_memory_query_service_boundary_exists():
    assert hasattr(memory, "UnavailableMemoryQueryService")


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"grants": None, "caller_context": {"run_id": "run_001"}},
        {"grants": {"memory": {"query": True}}, "caller_context": None},
        {"grants": "not-a-dict", "caller_context": {"run_id": "run_001"}},
        {"grants": {"memory": {"query": True}}, "caller_context": "not-a-dict"},
    ],
)
def test_memory_query_requires_explicit_grants_and_caller_context(kwargs):
    service = memory.UnavailableMemoryQueryService(memory_store=ExplodingMemoryStore())

    with pytest.raises((PermissionError, ValueError), match="grants|caller_context|memory_query|not enabled|denied"):
        service.query(run_id="run_001", query="worked examples", **kwargs)


def test_memory_query_without_query_grant_does_not_read_memory_store():
    store = ExplodingMemoryStore()
    service = memory.UnavailableMemoryQueryService(memory_store=store)

    result = service.query(
        run_id="run_001",
        query="worked examples",
        grants={"memory": {"query": False}},
        caller_context={"run_id": "run_001"},
    )

    assert result == {
        "status": "denied",
        "capability": "memory_query",
        "reason_code": "missing_memory_query_grant",
        "content_policy": "no_memory_read",
        "results": [],
    }
    assert store.calls == []


def test_controlled_expand_without_expand_grant_does_not_read_full_content():
    store = ExplodingMemoryStore()
    service = memory.UnavailableMemoryQueryService(memory_store=store)

    result = service.query(
        run_id="run_001",
        query="worked examples",
        grants={"memory": {"query": True, "controlled_expand": False}},
        caller_context={"run_id": "run_001", "caller": "agent_loop", "purpose": "agent_recall"},
        controlled_expand=True,
    )

    assert result == {
        "status": "denied",
        "capability": "memory_controlled_expand",
        "reason_code": "missing_controlled_expand_grant",
        "content_policy": "no_full_content_read",
        "results": [],
    }
    assert "content" not in result
    assert "artifact_content" not in result
    assert "full_text" not in result
    assert "raw_artifact_content" not in result
    assert store.calls == []


@pytest.mark.parametrize("budget", [0, -1, "1", True, None])
@pytest.mark.parametrize(
    "service_factory",
    [
        memory.UnavailableMemoryQueryService,
        memory.LocalMemoryQueryService,
    ],
)
def test_controlled_expand_rejects_invalid_budget_without_store_read(service_factory, budget):
    store = ExplodingMemoryStore()
    service = service_factory(memory_store=store)

    result = service.query(
        run_id="run_001",
        query="worked examples",
        grants={
            "memory": {
                "query": True,
                "controlled_expand": True,
                "expand_budget": budget,
            }
        },
        caller_context={
            "run_id": "run_001",
            "caller": "agent_loop",
            "purpose": "agent_recall",
        },
        controlled_expand=True,
    )

    assert result == {
        "status": "denied",
        "capability": "memory_controlled_expand",
        "reason_code": "invalid_controlled_expand_budget",
        "content_policy": "no_full_content_read",
        "results": [],
    }
    assert store.calls == []


def test_memory_query_default_shape_excludes_full_content():
    service = memory.UnavailableMemoryQueryService(memory_store=ExplodingMemoryStore())

    result = service.query(
        run_id="run_001",
        query="worked examples",
        grants={"memory": {"query": True}},
        caller_context={"run_id": "run_001", "caller": "agent_loop", "purpose": "agent_recall"},
    )

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "memory_query_unavailable"
    assert result["content_policy"] == "summary_refs_provenance_only"
    assert "content" not in result
    assert "artifact_content" not in result
    assert "full_text" not in result
    assert "raw_artifact_content" not in result
    for item in result.get("results", []):
        assert "content" not in item
        assert "artifact_content" not in item
        assert "full_text" not in item
        assert "raw_artifact_content" not in item


def test_unavailable_memory_query_with_valid_controlled_expand_returns_queued_metadata():
    store = ExplodingMemoryStore()
    service = memory.UnavailableMemoryQueryService(memory_store=store)

    result = service.query(
        run_id="run_001",
        query="worked examples",
        grants={
            "memory": {
                "query": True,
                "controlled_expand": True,
                "expand_budget": 2,
            }
        },
        caller_context={
            "run_id": "run_001",
            "caller": "agent_loop",
            "purpose": "agent_recall",
        },
        controlled_expand=True,
    )

    assert result == {
        "status": "unavailable",
        "capability": "memory_query",
        "reason_code": "memory_query_unavailable",
        "content_policy": "summary_refs_provenance_only",
        "controlled_expand": {
            "status": "queued",
            "budget": 2,
            "content_policy": "summary_refs_provenance_only",
        },
        "results": [],
    }
    assert store.calls == []


def test_valid_controlled_expand_grant_materializes_record_content_with_budget():
    store = PreviewOnlyMemoryStore()
    service = memory.LocalMemoryQueryService(memory_store=store)

    result = service.query(
        run_id="run_001",
        query="controlled expand preview",
        grants={
            "memory": {
                "query": True,
                "controlled_expand": True,
                "expand_budget": 100,
            }
        },
        caller_context={
            "run_id": "run_001",
            "caller": "agent_loop",
            "purpose": "agent_recall",
        },
        controlled_expand=True,
    )

    assert result["status"] == "ok"
    assert result["content_policy"] == "summary_refs_provenance_only"
    assert result["controlled_expand"]["status"] == "materialized"
    assert result["controlled_expand"]["budget"] == 100
    assert result["controlled_expand"]["used"] > 0
    assert result["controlled_expand"]["content_policy"] == (
        "controlled_expand_memory_record_content_only"
    )
    assert result["controlled_expand"]["materialized_results"] == [
        {
            "record_id": "mem_preview_001",
            "scope": "run",
            "encoding": "json",
            "materialized_text": (
                '{"kind": "structured_note", '
                '"text": "hidden full memory content must not be returned"}'
            ),
            "used": result["controlled_expand"]["used"],
            "truncated": False,
            "source_refs": [{"ref_type": "artifact", "artifact_id": "artifact_001"}],
            "provenance": {
                "run_id": "run_001",
                "execution_id": "exec_001",
                "action_type": "write_memory",
            },
        }
    ]
    assert result["results"] == [
        {
            "record_id": "mem_preview_001",
            "scope": "run",
            "summary": "Resume from controlled expand preview.",
            "source_refs": [{"ref_type": "artifact", "artifact_id": "artifact_001"}],
            "provenance": {
                "run_id": "run_001",
                "execution_id": "exec_001",
                "action_type": "write_memory",
            },
            "quality": "candidate",
        }
    ]
    assert store.calls == ["list_records"]


def test_valid_controlled_expand_grant_truncates_to_budget():
    store = PreviewOnlyMemoryStore()
    service = memory.LocalMemoryQueryService(memory_store=store)

    result = service.query(
        run_id="run_001",
        query="controlled expand preview",
        grants={
            "memory": {
                "query": True,
                "controlled_expand": True,
                "expand_budget": 2,
            }
        },
        caller_context={
            "run_id": "run_001",
            "caller": "agent_loop",
            "purpose": "agent_recall",
        },
        controlled_expand=True,
    )

    controlled_expand = result["controlled_expand"]
    assert controlled_expand["status"] == "materialized"
    assert controlled_expand["budget"] == 2
    assert controlled_expand["used"] == 2
    assert controlled_expand["materialized_results"][0]["truncated"] is True
    assert controlled_expand["materialized_results"][0]["encoding"] == "json_prefix"
    assert controlled_expand["materialized_results"][0]["materialized_text"] == '{"kind":'
    assert store.calls == ["list_records"]


def test_local_memory_query_denials_use_same_reason_contract():
    store = ExplodingMemoryStore()
    service = memory.LocalMemoryQueryService(memory_store=store)

    missing_query_grant = service.query(
        run_id="run_001",
        query="worked examples",
        grants={"memory": {"query": False}},
        caller_context={"run_id": "run_001"},
    )
    missing_expand_grant = service.query(
        run_id="run_001",
        query="worked examples",
        grants={"memory": {"query": True, "controlled_expand": False}},
        caller_context={"run_id": "run_001", "caller": "agent_loop", "purpose": "agent_recall"},
        controlled_expand=True,
    )

    assert missing_query_grant == {
        "status": "denied",
        "capability": "memory_query",
        "reason_code": "missing_memory_query_grant",
        "content_policy": "no_memory_read",
        "results": [],
    }
    assert missing_expand_grant == {
        "status": "denied",
        "capability": "memory_controlled_expand",
        "reason_code": "missing_controlled_expand_grant",
        "content_policy": "no_full_content_read",
        "results": [],
    }
    assert store.calls == []


@pytest.mark.parametrize(
    ("caller_context", "reason_code"),
    [
        ({"run_id": "run_other"}, "caller_context_run_mismatch"),
        ({}, "caller_context_run_mismatch"),
    ],
)
@pytest.mark.parametrize(
    "service_factory",
    [
        memory.UnavailableMemoryQueryService,
        memory.LocalMemoryQueryService,
    ],
)
def test_memory_query_rejects_caller_context_run_mismatch_without_store_read(
    service_factory,
    caller_context,
    reason_code,
):
    store = ExplodingMemoryStore()
    service = service_factory(memory_store=store)

    result = service.query(
        run_id="run_allowed",
        query="worked examples",
        grants={"memory": {"query": True}},
        caller_context=caller_context,
    )

    assert result == {
        "status": "denied",
        "capability": "memory_query",
        "reason_code": reason_code,
        "content_policy": "no_memory_read",
        "results": [],
    }
    assert store.calls == []


@pytest.mark.parametrize(
    "caller_context",
    [
        {"run_id": "run_allowed"},
        {"run_id": "run_allowed", "caller": "", "purpose": "agent_recall"},
        {"run_id": "run_allowed", "caller": "agent_loop", "purpose": ""},
        {"run_id": "run_allowed", "caller": "agent_loop", "purpose": 123},
    ],
)
@pytest.mark.parametrize(
    "service_factory",
    [
        memory.UnavailableMemoryQueryService,
        memory.LocalMemoryQueryService,
    ],
)
def test_memory_query_rejects_missing_caller_audit_context_without_store_read(
    service_factory,
    caller_context,
):
    store = ExplodingMemoryStore()
    service = service_factory(memory_store=store)

    result = service.query(
        run_id="run_allowed",
        query="worked examples",
        grants={"memory": {"query": True}},
        caller_context=caller_context,
    )

    assert result == {
        "status": "denied",
        "capability": "memory_query",
        "reason_code": "invalid_caller_context",
        "content_policy": "no_memory_read",
        "results": [],
    }
    assert store.calls == []


def test_projector_rebuild_still_does_not_read_memory_query_or_store(tmp_path):
    class ExplodingMemoryQueryService:
        def query(self, *args, **kwargs):
            raise AssertionError("projector must not query memory")

    store = event_store.FileEventStore(tmp_path)
    store.append(
        events.CanonicalEvent(
            event_id="evt_001",
            run_id="run_001",
            event_type="run.created",
            payload={"run_id": "run_001"},
            created_at="2026-04-29T00:00:00Z",
        )
    )
    memory_query = ExplodingMemoryQueryService()
    memory_store = ExplodingMemoryStore()

    state = projector.RunProjector().rebuild("run_001", store)

    assert memory_query is not None
    assert memory_store is not None
    assert state.run_id == "run_001"
    assert state.status == "running"
    assert memory_store.calls == []


def test_server_memory_query_public_api_remains_absent_until_boundary_is_enabled(tmp_path):
    api = server.InProcessServer(tmp_path)

    assert not hasattr(api, "query_memory")
