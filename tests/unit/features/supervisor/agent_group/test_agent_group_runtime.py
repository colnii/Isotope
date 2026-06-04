from __future__ import annotations

from isotope.agents.loop.conversation import AgentConversationMessage
from isotope.features.supervisor.agent_group.runtime import (
    AgentGroupRuntime,
    StaticAgentGroupProvider,
    SummaryAgentGroupProvider,
)


def test_runtime_tick_selects_visible_messages_and_records_turn(tmp_path):
    provider = StaticAgentGroupProvider(
        {
            "planner": AgentConversationMessage(
                message_id="candidate_planner",
                agent_id="planner",
                intent="respond",
                summary="Start with a narrow contract.",
                priority=50,
            ),
            "reviewer": AgentConversationMessage(
                message_id="candidate_reviewer",
                agent_id="reviewer",
                intent="respond",
                summary="Add failing tests first.",
                priority=40,
            ),
        }
    )
    runtime = AgentGroupRuntime(tmp_path, provider=provider)
    created = runtime.create_group(
        title="Feature group",
        goal="Discuss group chat.",
        member_specs=[
            {"name": "planner", "role": "Plan work.", "goal": "Find steps."},
            {"name": "reviewer", "role": "Review work.", "goal": "Find risks."},
        ],
        initial_message="Start.",
    )

    tick = runtime.tick_group(created["group"]["group_id"], max_visible_messages=1)

    assert tick["status"] == "ok"
    assert tick["turn"]["status"] == "selected"
    assert tick["turn"]["selected_message_ids"]
    assert tick["turn"]["queued_messages"][0]["reason"] == "visible_limit"
    messages = runtime.list_group(created["group"]["group_id"])["messages"]
    assert messages[-1]["summary"] == "Start with a narrow contract."


def test_runtime_tick_allows_silent_members(tmp_path):
    provider = StaticAgentGroupProvider(
        {
            "planner": AgentConversationMessage(
                message_id="candidate_planner",
                agent_id="planner",
                intent="silent",
                summary="No update.",
                priority=0,
            )
        }
    )
    runtime = AgentGroupRuntime(tmp_path, provider=provider)
    created = runtime.create_group(
        title="Feature group",
        goal="Discuss group chat.",
        member_specs=[{"name": "planner", "role": "Plan work.", "goal": "Find steps."}],
        initial_message="Start.",
    )

    tick = runtime.tick_group(created["group"]["group_id"])

    assert tick["turn"]["status"] == "silent"
    assert tick["turn"]["selected_message_ids"] == []
    assert len(runtime.list_group(created["group"]["group_id"])["messages"]) == 1


class FakeSummaryProvider:
    def summarize(self, messages: list[dict[str, str]]) -> str:
        return "Use a narrow first slice."


def test_summary_agent_group_provider_builds_member_reply(tmp_path):
    provider = SummaryAgentGroupProvider(FakeSummaryProvider())
    runtime = AgentGroupRuntime(tmp_path, provider=StaticAgentGroupProvider({}))
    created = runtime.create_group(
        title="Feature group",
        goal="Discuss group chat.",
        member_specs=[{"name": "planner", "role": "Plan work.", "goal": "Find steps."}],
        initial_message="Start.",
    )
    member = runtime.store.list_members(created["group"]["group_id"])[0]

    candidate = provider.candidate_for_member(
        member=member,
        group=created["group"],
        messages=created["messages"],
    )

    assert candidate.agent_id == member.member_id
    assert candidate.intent == "respond"
    assert candidate.summary == "Use a narrow first slice."
