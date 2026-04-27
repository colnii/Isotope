from isotope_kernel import memory, server


def test_memory_query_returns_not_enabled():
    result = memory.NotEnabledMemoryService().query("run_001", "anything")

    assert result == {"status": "not_enabled", "capability": "memory_query"}


def test_external_ingestion_returns_not_enabled(tmp_path):
    api = server.InProcessServer(tmp_path)

    result = api.ingest_external_input({"raw": "input"})

    assert result == {"status": "not_enabled", "capability": "external_ingestion"}


def test_checkpoint_returns_not_enabled_or_absent(tmp_path):
    api = server.InProcessServer(tmp_path)

    result = api.create_checkpoint("run_001")

    assert result == {"status": "not_enabled", "capability": "checkpoint"}


def test_sse_not_exposed_in_slice(tmp_path):
    api = server.InProcessServer(tmp_path)

    assert not hasattr(api, "stream_events")
