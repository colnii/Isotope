from pathlib import Path

from isotope.features.supervisor import native_coding_run


class _FakeProvider:
    provider = "fake"
    model = "fake"


class _FakeServer:
    captured_contexts = []

    def __init__(self, root):
        self.root = Path(root)

    def create_session(self):
        return {"session_id": "session_native_coding"}

    def create_run(self, session_id, goal):
        return {"run_id": "run_native_coding"}

    def run_agent_loop_provider_planner_tick(self, run_id, **kwargs):
        self.captured_contexts.append(kwargs["default_context_extra"])
        return {
            "after_policy": {"should_continue": False},
            "planner_contract_result": None,
        }


def test_native_coding_agent_loop_exposes_ast_edit_capability(monkeypatch, tmp_path):
    _FakeServer.captured_contexts = []
    monkeypatch.setattr(native_coding_run, "InProcessServer", _FakeServer)

    native_coding_run.run_native_coding_agent_loop(
        state_root=tmp_path / "state",
        cwd=tmp_path / "repo",
        goal="Edit a function by AST node.",
        inputs={},
        provider=_FakeProvider(),
        max_steps=1,
    )

    coding_context = _FakeServer.captured_contexts[0]["coding_task"]
    assert "code.ast_edit" in coding_context["allowed_capabilities"]
