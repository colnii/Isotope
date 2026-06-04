from __future__ import annotations

import builtins

from isotope.rag.lancedb_store import LanceDBVectorStore
from isotope.rag.vector_store import VectorSearchHit


def test_lancedb_store_reports_unavailable_when_dependency_is_missing(
    monkeypatch, tmp_path
):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "lancedb":
            raise ModuleNotFoundError("No module named 'lancedb'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    store = LanceDBVectorStore(path=tmp_path / "vectors.lance", table_name="memory")
    result = store.search(query_vector=[1.0, 0.0, 0.0], limit=3)

    assert result.status == "dense_unavailable"
    assert result.reason_code == "lancedb_not_installed"
    assert result.hits == []


class _FakeLanceTable:
    def search(self, query_vector):
        self.query_vector = query_vector
        return self

    def limit(self, limit):
        self.query_limit = limit
        return self

    def to_list(self):
        return [
            {"document_id": "doc_1", "_distance": 0.1, "kind": "memory"},
            {"document_id": "doc_2", "_distance": 0.4, "kind": "memory"},
        ]


class _FakeLanceConnection:
    def open_table(self, table_name):
        assert table_name == "memory"
        return _FakeLanceTable()


class _FakeLanceModule:
    @staticmethod
    def connect(path):
        return _FakeLanceConnection()


def test_lancedb_store_maps_rows_to_vector_hits(monkeypatch, tmp_path):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "lancedb":
            return _FakeLanceModule
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    result = LanceDBVectorStore(
        path=tmp_path / "vectors.lance", table_name="memory"
    ).search(
        query_vector=[1.0, 0.0],
        limit=2,
    )

    assert result.status == "ok"
    assert result.hits == [
        VectorSearchHit(document_id="doc_1", score=0.9, metadata={"kind": "memory"}),
        VectorSearchHit(document_id="doc_2", score=0.6, metadata={"kind": "memory"}),
    ]
