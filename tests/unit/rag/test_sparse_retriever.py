from __future__ import annotations

from isotope.rag import RetrievalDocument, SparseRetriever


def test_sparse_retriever_uses_existing_bm25_ranking():
    documents = [
        RetrievalDocument(
            document_id="project_1",
            title="portfolio demo",
            summary="general workspace",
        ),
        RetrievalDocument(
            document_id="task_1",
            title="interview story",
            summary="portfolio hiring practice",
        ),
        RetrievalDocument(
            document_id="file_1",
            title="meal plan",
            summary="weekly groceries",
        ),
    ]

    result = SparseRetriever().search(
        query="portfolio interview", documents=documents, limit=2
    )

    assert result.status == "ok"
    assert [hit.document.document_id for hit in result.hits] == [
        "task_1",
        "project_1",
    ]
    assert result.hits[0].score > result.hits[1].score > 0
