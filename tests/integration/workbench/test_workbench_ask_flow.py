from __future__ import annotations

import json
from typing import Any

import pytest

from isotope.features.ask.flow import WorkbenchAskFlow
from isotope.features.files.flow import FileFlow
from isotope.features.projects.flow import ProjectFlow
from isotope.features.tasks.flow import TaskFlow
from isotope.llm.provider import LLMResponse


FORBIDDEN_KEYS = {
    "artifact_content",
    "content",
    "full_content",
    "full_text",
    "raw_artifact_content",
    "raw_content",
    "text",
}


class RecordingProvider:
    provider = "deterministic_test"
    model = "test-workbench-ask"

    def __init__(self, content: str = "先推进作品集任务。") -> None:
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
            usage={"prompt_tokens": 12, "completion_tokens": 8},
            raw={"id": "deterministic-test"},
        )


def test_workbench_ask_flow_answers_from_public_metadata_workbench_context(tmp_path):
    ProjectFlow.in_process(tmp_path).create_project(
        name="portfolio demo",
        summary="autumn recruiting workspace",
    )
    TaskFlow.in_process(tmp_path).create_task(
        goal="build portfolio story",
        first_message="PRIVATE_TASK_NOTE_SHOULD_NOT_LEAK",
    )
    FileFlow.in_process(tmp_path).create_text_file(
        name="portfolio-notes.md",
        summary="portfolio notes",
        content="PRIVATE_FILE_CONTENT_SHOULD_NOT_LEAK",
    )
    provider = RecordingProvider("建议先整理作品集故事线。")

    answer = WorkbenchAskFlow.in_process(tmp_path, provider=provider).answer(
        "portfolio 下一步做什么？",
        search_limit=3,
        max_tokens=256,
    )

    assert answer.answer == "建议先整理作品集故事线。"
    assert answer.question == "portfolio 下一步做什么？"
    assert answer.provider == "deterministic_test"
    assert answer.model == "test-workbench-ask"
    assert answer.workbench.counts == {
        "projects": 1,
        "tasks": 1,
        "files": 1,
        "search_results": 3,
    }
    payload = answer.to_dict()
    assert payload["status"] == "ok"
    assert payload["context"]["counts"] == answer.workbench.counts
    assert payload["references"] == [
        {
            "rank": 1,
            "result_type": "project",
            "result_id": payload["context"]["search_results"][0]["result_id"],
            "title": "portfolio demo",
            "summary": "autumn recruiting workspace",
        },
        {
            "rank": 2,
            "result_type": "task",
            "result_id": payload["context"]["search_results"][1]["result_id"],
            "title": "build portfolio story",
            "summary": payload["context"]["search_results"][1]["summary"],
        },
        {
            "rank": 3,
            "result_type": "file",
            "result_id": payload["context"]["search_results"][2]["result_id"],
            "title": "portfolio-notes.md",
            "summary": "portfolio notes",
        },
    ]
    _assert_public_metadata(payload)

    prompt_payload = json.loads(provider.calls[0]["messages"][1]["content"])
    assert prompt_payload["question"] == "portfolio 下一步做什么？"
    assert prompt_payload["references"][0]["title"] == "portfolio demo"
    assert prompt_payload["workbench"]["projects"][0]["summary"] == "autumn recruiting workspace"
    assert "PRIVATE_FILE_CONTENT_SHOULD_NOT_LEAK" not in provider.calls[0]["messages"][1]["content"]
    assert "PRIVATE_TASK_NOTE_SHOULD_NOT_LEAK" not in provider.calls[0]["messages"][1]["content"]
    assert provider.calls[0]["max_tokens"] == 256


def test_workbench_ask_flow_uses_refreshed_task_and_file_summaries(tmp_path):
    task = TaskFlow.in_process(tmp_path).create_task(
        goal="build portfolio story",
        first_message="PRIVATE_TASK_NOTE_SHOULD_NOT_LEAK",
    )
    FileFlow.in_process(tmp_path).create_text_file(
        name="portfolio-notes.md",
        summary="canonical file summary",
        content="PRIVATE_FILE_CONTENT_SHOULD_NOT_LEAK",
    )
    task_index_path = tmp_path / "tasks" / "index.json"
    task_index = json.loads(task_index_path.read_text(encoding="utf-8"))
    task_index["tasks"][0]["result_summary"] = "stale task index summary"
    task_index_path.write_text(json.dumps(task_index), encoding="utf-8")
    file_index_path = tmp_path / "files" / "index.json"
    file_index = json.loads(file_index_path.read_text(encoding="utf-8"))
    file_index["files"][0]["summary"] = "stale file index summary"
    file_index_path.write_text(json.dumps(file_index), encoding="utf-8")
    provider = RecordingProvider("用刷新后的摘要推进。")

    WorkbenchAskFlow.in_process(tmp_path, provider=provider).answer(
        "portfolio 下一步做什么？",
        search_limit=3,
    )

    prompt_payload = json.loads(provider.calls[0]["messages"][1]["content"])
    prompt_context = json.dumps(prompt_payload, ensure_ascii=False, sort_keys=True)
    assert "stale task index summary" not in prompt_context
    assert "stale file index summary" not in prompt_context
    assert task.result_summary in prompt_context
    assert "canonical file summary" in prompt_context
    assert "PRIVATE_FILE_CONTENT_SHOULD_NOT_LEAK" not in prompt_context
    assert "PRIVATE_TASK_NOTE_SHOULD_NOT_LEAK" not in prompt_context


def test_workbench_ask_flow_rejects_empty_question(tmp_path):
    provider = RecordingProvider()

    with pytest.raises(ValueError, match="question must not be empty"):
        WorkbenchAskFlow.in_process(tmp_path, provider=provider).answer("  ")

    assert provider.calls == []


def test_workbench_ask_flow_rejects_empty_provider_answer(tmp_path):
    provider = RecordingProvider("  ")

    with pytest.raises(ValueError, match="provider returned empty answer"):
        WorkbenchAskFlow.in_process(tmp_path, provider=provider).answer("下一步做什么？")


def _assert_public_metadata(value: Any) -> None:
    if isinstance(value, dict):
        assert FORBIDDEN_KEYS.isdisjoint(value)
        for nested in value.values():
            _assert_public_metadata(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_public_metadata(nested)
    elif isinstance(value, str):
        assert "PRIVATE_FILE_CONTENT_SHOULD_NOT_LEAK" not in value
        assert "PRIVATE_TASK_NOTE_SHOULD_NOT_LEAK" not in value
