from __future__ import annotations

import json

from isotope.features.research.recall import build_research_recall_payload
from isotope.rag import RetrievalDocument
from isotope.rag.index import build_rag_index
from isotope.workspace.artifacts import ArtifactStore


def test_lancedb_rag_index_round_trips_with_installed_package(tmp_path):
    import lancedb  # noqa: F401

    index = build_rag_index(
        [
            RetrievalDocument(
                document_id="doc_semantic",
                title="semantic vector search",
                summary="LanceDB real package round trip.",
            )
        ],
        {
            "backend": "lancedb",
            "path": str(tmp_path / "vectors"),
            "table_name": "rag",
            "dimensions": 8,
        },
    )

    assert index is not None
    components = index.components()
    result = components.vector_store.search(
        query_vector=components.embedding_provider.embed("semantic vector search"),
        limit=5,
    )

    assert result.status == "ok"
    assert result.reason_code is None
    assert [hit.document_id for hit in result.hits] == ["doc_semantic"]
    assert (tmp_path / "vectors").exists()


def test_research_recall_uses_real_lancedb_backend(tmp_path):
    import lancedb  # noqa: F401

    store = ArtifactStore(tmp_path)
    report = store.create_artifact(
        "run_real_lancedb",
        execution_id="exec_real_lancedb",
        artifact_type="research.report",
        summary="REAL_LANCEDB_SMOKE semantic vector recall preview.",
        content=json.dumps({"body": "hidden report body"}),
    )

    payload = build_research_recall_payload(
        root=tmp_path,
        query="semantic vector recall",
        dense_retrieval={
            "backend": "lancedb",
            "path": str(tmp_path / "vectors"),
            "table_name": "research_recall_smoke",
            "dimensions": 8,
        },
    )

    assert payload["retrieval"] == {"backend": "hybrid", "dense_status": "ok"}
    assert [item["artifact_id"] for item in payload["results"]] == [
        report.artifact_id
    ]
