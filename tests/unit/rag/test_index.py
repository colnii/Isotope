from __future__ import annotations

import builtins

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


def test_rag_index_config_accepts_lancedb_backend():
    config = parse_rag_index_config(
        {
            "backend": "lancedb",
            "path": "/tmp/isotope-vectors",
            "table_name": "research",
            "dimensions": 8,
        }
    )

    assert config.backend == "lancedb"
    assert config.path == "/tmp/isotope-vectors"
    assert config.table_name == "research"
    assert config.dimensions == 8


class _FakeWritableLanceTable:
    def __init__(self):
        self.rows = []

    def add(self, rows, mode=None):
        self.rows = list(rows)
        self.add_mode = mode
        return self

    def search(self, query_vector):
        self.query_vector = query_vector
        return self

    def limit(self, limit):
        self.query_limit = limit
        return self

    def to_list(self):
        return [
            {**row, "_distance": 0.1}
            for row in self.rows[: self.query_limit]
        ]


class _FakeWritableLanceConnection:
    def __init__(self):
        self.tables = {}

    def open_table(self, table_name):
        if table_name not in self.tables:
            raise FileNotFoundError(table_name)
        return self.tables[table_name]

    def create_table(self, table_name, data, mode=None):
        table = _FakeWritableLanceTable()
        table.rows = list(data)
        table.create_mode = mode
        self.tables[table_name] = table
        return table


class _FakeWritableLanceModule:
    connections = []
    connections_by_path = {}

    @classmethod
    def connect(cls, path):
        if path not in cls.connections_by_path:
            connection = _FakeWritableLanceConnection()
            cls.connections_by_path[path] = connection
            cls.connections.append(connection)
        return cls.connections_by_path[path]


def test_lancedb_rag_index_builds_dense_components_for_documents(monkeypatch, tmp_path):
    _FakeWritableLanceModule.connections = []
    _FakeWritableLanceModule.connections_by_path = {}
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "lancedb":
            return _FakeWritableLanceModule
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    index = build_rag_index(
        [RetrievalDocument(document_id="doc_1", title="semantic vector search")],
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
