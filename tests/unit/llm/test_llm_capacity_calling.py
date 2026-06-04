from __future__ import annotations

import json
from typing import Any

import pytest

from isotope.llm.capacity_calling import select_capacity_call
from isotope.llm.provider import LLMResponse
from isotope.platform.errors import IsotopeError


class RecordingProvider:
    provider = "fake"
    model = "fake-capacity-caller"

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=self.content,
            finish_reason="stop",
            usage={"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
            raw={"id": "fake-response"},
        )


def _capacity(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "capacity_id": "artifact.review",
        "title": "Artifact Review",
        "description": "Review public artifact summaries.",
        "domain_tags": ["artifact", "review"],
        "input_contract": {
            "type": "object",
            "required": ["artifact_ref", "question"],
            "properties": {
                "artifact_ref": {"type": "string"},
                "question": {"type": "string"},
            },
        },
    }
    data.update(overrides)
    return data


def test_select_capacity_call_asks_llm_to_choose_capacity_and_fill_arguments():
    provider = RecordingProvider(
        json.dumps(
            {
                "capacity_id": "artifact.review",
                "arguments": {
                    "artifact_ref": "artifact://run-1/summary",
                    "question": "检查产物摘要是否可用",
                },
                "confidence": 0.82,
                "rationale": "用户在询问 artifact review。",
            }
        )
    )

    selection = select_capacity_call(
        provider,
        goal="帮我检查 artifact://run-1/summary 这个产物摘要是否可用",
        capacities=[_capacity()],
        max_tokens=192,
    )

    assert selection.kind == "capacity_call_selection"
    assert selection.status == "ready_to_call"
    assert selection.capacity_id == "artifact.review"
    assert selection.arguments == {
        "artifact_ref": "artifact://run-1/summary",
        "question": "检查产物摘要是否可用",
    }
    assert selection.missing_inputs == []
    assert selection.provider == "fake"
    assert selection.model == "fake-capacity-caller"
    assert selection.usage == {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18}
    assert selection.to_dict()["status"] == "ready_to_call"

    prompt_payload = json.loads(provider.calls[0]["messages"][1]["content"])
    assert prompt_payload["goal"] == "帮我检查 artifact://run-1/summary 这个产物摘要是否可用"
    assert prompt_payload["capacities"][0]["capacity_id"] == "artifact.review"
    assert prompt_payload["required_json_shape"] == {
        "capacity_id": "string",
        "arguments": "object",
        "confidence": "number between 0 and 1",
        "rationale": "short public string",
    }
    assert provider.calls[0]["max_tokens"] == 192


def test_select_capacity_call_can_decline_capacity_when_allowed():
    provider = RecordingProvider(
        json.dumps(
            {
                "capacity_id": None,
                "arguments": {},
                "confidence": 0.93,
                "rationale": "普通问候不需要能力调用。",
            }
        )
    )

    selection = select_capacity_call(
        provider,
        goal="你好",
        capacities=[_capacity()],
        allow_no_capacity=True,
    )

    assert selection.status == "no_capacity"
    assert selection.capacity_id == ""
    assert selection.arguments == {}
    prompt_payload = json.loads(provider.calls[0]["messages"][1]["content"])
    assert prompt_payload["required_json_shape"]["capacity_id"] == "string or null"
    assert "set capacity_id to null" in " ".join(prompt_payload["rules"])


def test_select_capacity_call_reports_missing_required_arguments_without_execution():
    provider = RecordingProvider(
        json.dumps(
            {
                "capacity_id": "artifact.review",
                "arguments": {"artifact_ref": "artifact://run-1/summary"},
                "confidence": 0.61,
                "rationale": "缺少用户想问的问题。",
            }
        )
    )

    selection = select_capacity_call(
        provider,
        goal="检查 artifact://run-1/summary",
        capacities=[_capacity()],
    )

    assert selection.status == "missing_inputs"
    assert selection.capacity_id == "artifact.review"
    assert selection.arguments == {"artifact_ref": "artifact://run-1/summary"}
    assert selection.missing_inputs == ["question"]


def test_select_capacity_call_rejects_arguments_outside_input_contract():
    provider = RecordingProvider(
        json.dumps(
            {
                "capacity_id": "artifact.review",
                "arguments": {
                    "artifact_ref": "artifact://run-1/summary",
                    "question": "检查摘要",
                    "raw_content": "PRIVATE_ARTIFACT_CONTENT_SHOULD_NOT_LEAK",
                },
                "confidence": 0.75,
                "rationale": "tries to include extra data",
            }
        )
    )

    with pytest.raises(IsotopeError) as exc_info:
        select_capacity_call(provider, goal="检查摘要", capacities=[_capacity()])

    assert exc_info.value.code == "llm_capacity_invalid_response"
    assert exc_info.value.category == "validation"
    assert "not allowed by capacity input_contract" in str(exc_info.value)


def test_select_capacity_call_rejects_arguments_with_wrong_contract_type():
    provider = RecordingProvider(
        json.dumps(
            {
                "capacity_id": "artifact.review",
                "arguments": {
                    "artifact_ref": "artifact://run-1/summary",
                    "question": "检查摘要",
                    "max_results": "5",
                },
                "confidence": 0.75,
                "rationale": "fills max_results with a string",
            }
        )
    )
    capacity = _capacity(
        input_contract={
            "type": "object",
            "required": ["artifact_ref", "question"],
            "properties": {
                "artifact_ref": {"type": "string"},
                "question": {"type": "string"},
                "max_results": {"type": "integer"},
            },
        }
    )

    with pytest.raises(IsotopeError) as exc_info:
        select_capacity_call(provider, goal="检查摘要", capacities=[capacity])

    assert exc_info.value.code == "llm_capacity_invalid_response"
    assert exc_info.value.category == "validation"
    assert "does not match input_contract type" in str(exc_info.value)


def test_select_capacity_call_rejects_arguments_outside_contract_enum():
    provider = RecordingProvider(
        json.dumps(
            {
                "capacity_id": "artifact.review",
                "arguments": {
                    "artifact_ref": "artifact://run-1/summary",
                    "question": "检查摘要",
                    "mode": "raw",
                },
                "confidence": 0.75,
                "rationale": "fills an enum argument outside the contract",
            }
        )
    )
    capacity = _capacity(
        input_contract={
            "type": "object",
            "required": ["artifact_ref", "question"],
            "properties": {
                "artifact_ref": {"type": "string"},
                "question": {"type": "string"},
                "mode": {"type": "string", "enum": ["summary", "detail"]},
            },
        }
    )

    with pytest.raises(IsotopeError) as exc_info:
        select_capacity_call(provider, goal="检查摘要", capacities=[capacity])

    assert exc_info.value.code == "llm_capacity_invalid_response"
    assert exc_info.value.category == "validation"
    assert "not allowed by input_contract enum" in str(exc_info.value)


def test_select_capacity_call_rejects_required_inputs_not_declared_in_properties():
    provider = RecordingProvider(
        json.dumps(
            {
                "capacity_id": "artifact.review",
                "arguments": {},
                "confidence": 0.75,
                "rationale": "should not be called",
            }
        )
    )
    capacity = _capacity(
        input_contract={
            "type": "object",
            "required": ["artifact_ref", "question", "raw_content"],
            "properties": {
                "artifact_ref": {"type": "string"},
                "question": {"type": "string"},
            },
        }
    )

    with pytest.raises(ValueError, match="required inputs must be declared"):
        select_capacity_call(provider, goal="检查摘要", capacities=[capacity])

    assert provider.calls == []


def test_select_capacity_call_rejects_duplicate_required_inputs_before_provider_call():
    provider = RecordingProvider(
        json.dumps(
            {
                "capacity_id": "artifact.review",
                "arguments": {},
                "confidence": 0.75,
                "rationale": "should not be called",
            }
        )
    )
    capacity = _capacity(
        input_contract={
            "type": "object",
            "required": ["artifact_ref", "question", "question"],
            "properties": {
                "artifact_ref": {"type": "string"},
                "question": {"type": "string"},
            },
        }
    )

    with pytest.raises(ValueError, match="duplicate required input"):
        select_capacity_call(provider, goal="检查摘要", capacities=[capacity])

    assert provider.calls == []


def test_select_capacity_call_rejects_duplicate_capacity_ids_before_provider_call():
    provider = RecordingProvider(
        json.dumps(
            {
                "capacity_id": "artifact.review",
                "arguments": {},
                "confidence": 0.75,
                "rationale": "should not be called",
            }
        )
    )

    with pytest.raises(ValueError, match="duplicate capacity_id"):
        select_capacity_call(
            provider,
            goal="检查摘要",
            capacities=[
                _capacity(title="Artifact Review A"),
                _capacity(title="Artifact Review B"),
            ],
        )

    assert provider.calls == []


def test_select_capacity_call_rejects_unoffered_capacity():
    provider = RecordingProvider(
        json.dumps(
            {
                "capacity_id": "terminal.exec",
                "arguments": {},
                "confidence": 0.9,
                "rationale": "tries to escape the offered set",
            }
        )
    )

    with pytest.raises(IsotopeError) as exc_info:
        select_capacity_call(provider, goal="run a command", capacities=[_capacity()])

    assert exc_info.value.code == "llm_capacity_unoffered"
    assert exc_info.value.category == "unavailable"
    assert exc_info.value.details == {"capacity_id": "terminal.exec"}


def test_select_capacity_call_rejects_malformed_provider_json():
    provider = RecordingProvider("I would use artifact.review")

    with pytest.raises(IsotopeError) as exc_info:
        select_capacity_call(provider, goal="review artifact", capacities=[_capacity()])

    assert exc_info.value.code == "llm_capacity_invalid_response"
    assert exc_info.value.category == "validation"


def test_capacity_prompt_excludes_raw_content_like_fields():
    provider = RecordingProvider(
        json.dumps(
            {
                "capacity_id": "artifact.review",
                "arguments": {
                    "artifact_ref": "artifact://run-1/summary",
                    "question": "检查摘要",
                },
                "confidence": 0.8,
                "rationale": "safe",
            }
        )
    )
    capacity = _capacity(raw_content="PRIVATE_ARTIFACT_CONTENT_SHOULD_NOT_LEAK")

    select_capacity_call(provider, goal="检查摘要", capacities=[capacity])

    serialized_messages = json.dumps(provider.calls[0]["messages"], ensure_ascii=False)
    assert "PRIVATE_ARTIFACT_CONTENT_SHOULD_NOT_LEAK" not in serialized_messages
