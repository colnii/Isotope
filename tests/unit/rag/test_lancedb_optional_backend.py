from __future__ import annotations

import builtins

from isotope.rag.lancedb_store import LanceDBVectorStore


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
