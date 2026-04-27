import pytest

from isotope_kernel import action_compiler, artifact_store, event_store, executor, policy, workspace


def _proposal():
    compiler = action_compiler.ActionCompiler()
    return compiler.compile(
        {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": "hello",
            "requested_tools": ["write_artifact_tool", "extra_tool"],
            "workspace_mode": "isolated_rw",
            "budget": {"seconds": 999},
        },
        {
            "run_id": "run_001",
            "agent_id": "agent_supervisor",
            "thread_id": "thread_main",
        },
    )


def test_modified_policy_removes_ungranted_tool_and_workspace():
    assert hasattr(policy, "PolicyEngine")

    decision = policy.PolicyEngine().decide(_proposal())

    assert decision.outcome == "modified"
    assert decision.grants["tools"] == ["write_artifact_tool"]
    assert decision.grants["workspace"]["mode"] == "shared_ro"
    assert decision.grants["budget"]["seconds"] < 999


def test_executor_uses_grants_not_requested_capabilities(tmp_path):
    assert hasattr(executor, "Executor")
    proposal = _proposal()
    decision = policy.PolicyEngine().decide(proposal)

    runner = executor.Executor(
        event_store=event_store.FileEventStore(tmp_path),
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        workspace_manager=workspace.WorkspaceManager(),
    )
    result = runner.execute(decision, proposal)

    assert result.effective_grants_snapshot["tools"] == ["write_artifact_tool"]
    assert result.effective_grants_snapshot["workspace"]["mode"] == "shared_ro"
    assert "extra_tool" not in result.effective_grants_snapshot["tools"]


def test_isotope_kernel_does_not_import_x_agent():
    import pathlib

    root = pathlib.Path("src/isotope_kernel")
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "import x_agent" in text or "from x_agent" in text:
            offenders.append(str(path))

    assert offenders == []
