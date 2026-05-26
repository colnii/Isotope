from __future__ import annotations

import json

import pytest

from isotope.memory.promotion import build_memory_promotion_proposal


ARTIFACT_REF = {
    "ref_type": "artifact",
    "scope": "run",
    "run_id": "run_memory",
    "artifact_id": "artifact_research_summary",
}


def test_memory_promotion_builds_write_memory_proposal_from_artifact_metadata():
    proposal = build_memory_promotion_proposal(
        run_id="run_memory",
        agent_id="agent_memo",
        thread_id="thread_memory",
        candidate={
            "source_type": "artifact",
            "artifact_ref": ARTIFACT_REF,
            "artifact_type": "research.report",
            "summary": "User prefers provenance-backed memory promotion.",
            "provenance": {"execution_id": "exec_research"},
        },
    )

    assert proposal.action_type == "write_memory"
    assert proposal.requested_capabilities == {"tools": ["write_memory"]}
    assert proposal.payload["scope"] == "run"
    assert proposal.payload["summary"] == (
        "User prefers provenance-backed memory promotion."
    )
    assert proposal.payload["source_refs"] == [ARTIFACT_REF]
    assert proposal.payload["quality"] == "candidate"
    assert proposal.payload["content"] == {
        "kind": "memory_promotion_candidate",
        "source_type": "artifact",
        "artifact_type": "research.report",
        "source_summary": "User prefers provenance-backed memory promotion.",
    }
    assert proposal.payload["provenance"] == {
        "promotion_source": "artifact",
        "source_execution_id": "exec_research",
    }


def test_memory_promotion_builds_write_memory_proposal_from_imported_observation():
    proposal = build_memory_promotion_proposal(
        run_id="run_memory",
        agent_id="agent_memo",
        thread_id="thread_memory",
        candidate={
            "source_type": "external_observation",
            "snapshot_id": "snapshot_research",
            "source_ref": ARTIFACT_REF,
            "summary": "Imported observation says the source is verified.",
            "observation": {"claim": "source verified", "subject": "memory"},
            "quality": {
                "confidence": 0.91,
                "coverage": "summary",
                "freshness": "fresh",
            },
            "provenance": {"raw_artifact_ref": ARTIFACT_REF},
            "basis_refs": [ARTIFACT_REF],
        },
        scope="session",
        quality="verified",
    )

    assert proposal.action_type == "write_memory"
    assert proposal.payload["scope"] == "session"
    assert proposal.payload["source_refs"] == [ARTIFACT_REF]
    assert proposal.payload["quality"] == "verified"
    assert proposal.payload["content"] == {
        "kind": "memory_promotion_candidate",
        "source_type": "external_observation",
        "snapshot_id": "snapshot_research",
        "source_summary": "Imported observation says the source is verified.",
        "observation": {"claim": "source verified", "subject": "memory"},
        "quality": {
            "confidence": 0.91,
            "coverage": "summary",
            "freshness": "fresh",
        },
    }
    assert proposal.payload["provenance"] == {
        "promotion_source": "external_observation",
        "snapshot_id": "snapshot_research",
        "raw_artifact_ref": ARTIFACT_REF,
        "basis_refs": [ARTIFACT_REF],
    }


def test_memory_promotion_rejects_raw_text_without_structured_source():
    with pytest.raises(
        ValueError,
        match="raw memory promotion requires structured source",
    ):
        build_memory_promotion_proposal(
            run_id="run_memory",
            agent_id="agent_memo",
            thread_id="thread_memory",
            candidate={
                "source_type": "raw_text",
                "summary": "raw note",
                "raw_text": "raw memory content must not be promoted directly",
            },
        )


def test_memory_promotion_rejects_raw_content_in_structured_candidate():
    with pytest.raises(
        ValueError,
        match="raw memory promotion cannot include raw_content",
    ):
        build_memory_promotion_proposal(
            run_id="run_memory",
            agent_id="agent_memo",
            thread_id="thread_memory",
            candidate={
                "source_type": "artifact",
                "artifact_ref": ARTIFACT_REF,
                "artifact_type": "research.report",
                "summary": "summary",
                "raw_content": "raw artifact content must not leak",
                "provenance": {"execution_id": "exec_research"},
            },
        )


def test_memory_promotion_rejects_raw_content_nested_in_observation():
    with pytest.raises(
        ValueError,
        match="raw memory promotion cannot include raw_content",
    ):
        build_memory_promotion_proposal(
            run_id="run_memory",
            agent_id="agent_memo",
            thread_id="thread_memory",
            candidate={
                "source_type": "external_observation",
                "snapshot_id": "snapshot_research",
                "source_ref": ARTIFACT_REF,
                "summary": "summary",
                "observation": {
                    "claim": "source verified",
                    "raw_content": "raw observation payload must not leak",
                },
                "quality": {
                    "confidence": 0.91,
                    "coverage": "summary",
                    "freshness": "fresh",
                },
                "provenance": {"raw_artifact_ref": ARTIFACT_REF},
                "basis_refs": [ARTIFACT_REF],
            },
        )


def test_memory_promotion_payload_does_not_expose_raw_source_text():
    proposal = build_memory_promotion_proposal(
        run_id="run_memory",
        agent_id="agent_memo",
        thread_id="thread_memory",
        candidate={
            "source_type": "artifact",
            "artifact_ref": ARTIFACT_REF,
            "artifact_type": "research.report",
            "summary": "Safe summary only.",
            "provenance": {"execution_id": "exec_research"},
        },
    )

    assert "raw artifact content" not in json.dumps(proposal.payload)
