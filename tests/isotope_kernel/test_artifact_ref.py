import pytest

from isotope_kernel import (
    action_compiler,
    artifact_store,
    event_store,
    executor,
    policy,
    refs,
    retrieval,
    workspace,
)


def _write_artifact(tmp_path, text="hello"):
    artifacts = artifact_store.ArtifactStore(tmp_path)
    proposal = action_compiler.ActionCompiler().compile(
        {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": text,
            "requested_tools": ["write_artifact_tool"],
        },
        {
            "run_id": "run_001",
            "agent_id": "agent_supervisor",
            "thread_id": "thread_main",
        },
    )
    decision = policy.PolicyEngine().decide(proposal)
    result = executor.Executor(
        event_store=event_store.FileEventStore(tmp_path),
        artifact_store=artifacts,
        workspace_manager=workspace.WorkspaceManager(),
    ).execute(decision, proposal)
    return artifacts, result


def test_write_artifact_tool_creates_artifact_with_execution_provenance(tmp_path):
    artifacts, result = _write_artifact(tmp_path)

    created = artifacts.list_artifacts("run_001")

    assert len(created) == 1
    assert created[0].summary == "hello artifact"
    assert created[0].provenance["execution_id"] == result.execution_id


def test_artifact_has_structured_resource_ref(tmp_path):
    artifacts = artifact_store.ArtifactStore(tmp_path)

    artifact = artifacts.create_artifact(
        run_id="run_001",
        execution_id="exec_001",
        artifact_type="text",
        summary="hello artifact",
        content="hello",
    )

    assert not isinstance(artifact.ref, str)
    assert artifact.ref == refs.make_artifact_ref(
        run_id="run_001",
        artifact_id=artifact.artifact_id,
    )
    assert artifact.ref.to_dict() == {
        "ref_type": "artifact",
        "scope": "run",
        "run_id": "run_001",
        "artifact_id": artifact.artifact_id,
    }


def test_retrieval_summary_uses_resource_ref_not_uri_string(tmp_path):
    artifacts = artifact_store.ArtifactStore(tmp_path)
    artifact = artifacts.create_artifact(
        run_id="run_001",
        execution_id="exec_001",
        artifact_type="text",
        summary="hello artifact",
        content="hello hidden content",
    )
    service = retrieval.RetrievalService(artifacts)
    grants = {"artifact": {"read": "summary"}}

    summary = service.get_artifact_summary(artifact.ref, grants=grants)

    assert summary == {
        "ref": artifact.ref.to_dict(),
        "artifact_type": "text",
        "summary": "hello artifact",
        "provenance": {"execution_id": "exec_001"},
    }
    with pytest.raises(TypeError):
        service.get_artifact_summary(
            f"artifact://run_001/{artifact.artifact_id}",
            grants=grants,
        )
