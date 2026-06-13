from __future__ import annotations

from isotope.rag import RetrievalDocument
from isotope.rag.index import build_rag_index, parse_rag_index_config


def test_build_rag_index_returns_none_without_dense_config():
    assert build_rag_index([], None) is None


def test_local_rag_index_builds_dense_components_for_documents():
    documents = [
        RetrievalDocument(document_id="doc_1", title="semantic vector search"),
    ]

    index = build_rag_index(
        documents,
        {"backend": "local", "dimensions": 8},
    )

    assert index is not None
    components = index.components()
    result = components.vector_store.search(
        query_vector=components.embedding_provider.embed("semantic vector search"),
        limit=5,
    )
    assert result.status == "ok"
    assert [hit.document_id for hit in result.hits] == ["doc_1"]


def test_rag_index_config_rejects_unknown_backend():
    try:
        parse_rag_index_config({"backend": "unknown"})
    except ValueError as exc:
        assert "dense_retrieval.backend" in str(exc)
    else:
        raise AssertionError("unknown backend should fail")


def test_rag_index_config_rejects_invalid_dimensions():
    try:
        parse_rag_index_config({"backend": "local", "dimensions": 0})
    except ValueError as exc:
        assert "dense_retrieval.dimensions" in str(exc)
    else:
        raise AssertionError("invalid dimensions should fail")
