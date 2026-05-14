from isotope import projector, server


def test_happy_path_produce_hello_artifact(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="produce a hello artifact")

    result = api.submit_input(run["run_id"], "hello")

    assert result["status"] == "completed"
    assert result["run_state"].status == "completed"
    assert result["run_state"].artifacts == [
        {
            "ref": result["artifact_ref"].to_dict(),
            "artifact_type": "text",
            "summary": "hello artifact",
            "provenance": {
                "execution_id": result["execution_id"],
                "proposal_id": result["proposal_id"],
                "decision_id": result["decision_id"],
            },
        }
    ]


def test_server_run_state_comes_from_projector(tmp_path, monkeypatch):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="produce a hello artifact")
    api.submit_input(run["run_id"], "hello")

    calls = []
    original_rebuild = projector.RunProjector.rebuild

    def spy_rebuild(self, run_id, event_store):
        calls.append(run_id)
        return original_rebuild(self, run_id, event_store)

    monkeypatch.setattr(projector.RunProjector, "rebuild", spy_rebuild)

    state = api.get_run_state(run["run_id"])

    assert calls == [run["run_id"]]
    assert state.status == "completed"
    assert state.artifacts[0]["summary"] == "hello artifact"


def test_server_events_come_from_event_store(tmp_path, monkeypatch):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="produce a hello artifact")
    api.submit_input(run["run_id"], "hello")

    calls = []
    original_list_events = api.event_store.list_events

    def spy_list_events(run_id):
        calls.append(run_id)
        return original_list_events(run_id)

    monkeypatch.setattr(api.event_store, "list_events", spy_list_events)

    events = api.get_events(run["run_id"])

    assert calls == [run["run_id"]]
    assert [event.event_type for event in events] == [
        "run.created",
        "agent.created",
        "thread.created",
        "action.proposed",
        "action.decided",
        "action.started",
        "artifact.created",
        "action.completed",
        "run.completed",
    ]
