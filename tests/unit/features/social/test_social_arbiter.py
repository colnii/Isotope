from __future__ import annotations

from isotope.features.social import (
    SocialActionCandidate,
    SocialArbiter,
    SocialMessagePart,
    SocialReplyAction,
    SocialTarget,
)


def _reply_action(action_id: str) -> SocialReplyAction:
    return SocialReplyAction(
        action_id=action_id,
        target=SocialTarget(platform="qq", chat_type="group", group_id="12345"),
        parts=(SocialMessagePart(kind="text", text="我来答"),),
    )


def test_arbiter_allows_only_one_send_candidate_per_turn() -> None:
    result = SocialArbiter().choose(
        (
            SocialActionCandidate(
                candidate_id="agent_a_send",
                agent_id="agent_a",
                kind="respond",
                reason="mentioned",
                confidence=0.6,
                reply_action=_reply_action("reply_a"),
            ),
            SocialActionCandidate(
                candidate_id="agent_b_send",
                agent_id="agent_b",
                kind="respond",
                reason="keyword",
                confidence=0.9,
                reply_action=_reply_action("reply_b"),
            ),
        )
    )

    assert [item.candidate_id for item in result.selected] == ["agent_b_send"]
    assert result.rejected == {
        "agent_a_send": "duplicate_send:agent_b_send already selected"
    }


def test_arbiter_rejects_state_lock_conflicts() -> None:
    result = SocialArbiter().choose(
        (
            SocialActionCandidate(
                candidate_id="memory_a",
                agent_id="agent_a",
                kind="write_memory",
                reason="remember preference",
                confidence=0.8,
                state_locks=("memory:user:10001",),
            ),
            SocialActionCandidate(
                candidate_id="memory_b",
                agent_id="agent_b",
                kind="request_operator_review",
                reason="review same preference",
                confidence=0.7,
                state_locks=("memory:user:10001",),
            ),
        )
    )

    assert [item.candidate_id for item in result.selected] == ["memory_a"]
    assert result.rejected == {
        "memory_b": "state_lock_conflict:memory:user:10001 owned by memory_a"
    }


def test_arbiter_selects_non_conflicting_non_send_candidates_together() -> None:
    result = SocialArbiter().choose(
        (
            SocialActionCandidate(
                candidate_id="note",
                agent_id="agent_a",
                kind="internal_note",
                reason="track context",
                confidence=0.4,
            ),
            SocialActionCandidate(
                candidate_id="tool",
                agent_id="agent_b",
                kind="call_capability",
                reason="needs repo search",
                confidence=0.9,
                capability_id="code.search",
                state_locks=("capability:code.search",),
            ),
        )
    )

    assert [item.candidate_id for item in result.selected] == ["tool", "note"]
    assert result.rejected == {}
