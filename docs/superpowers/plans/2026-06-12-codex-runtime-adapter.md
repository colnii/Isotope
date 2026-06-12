# Codex Runtime Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared Codex runtime projection layer that turns `codex exec --json` output into low-sensitive Isotope runtime summaries and artifacts.

**Architecture:** Add a focused `isotope.integrations.codex.runtime` package for event projection, summary aggregation, and summary artifact payload shaping. Keep `CodexCliBackend` as the executor and `CodexTaskAdapter` as the artifact boundary; the new runtime layer only interprets stdout/stderr.

**Tech Stack:** Python 3.13, dataclasses, stdlib `json`, pytest, existing Codex task adapter contracts.

---

### Task 1: Runtime Projection API

**Files:**
- Create: `src/isotope/integrations/codex/runtime/__init__.py`
- Create: `src/isotope/integrations/codex/runtime/events.py`
- Create: `src/isotope/integrations/codex/runtime/projection.py`
- Create: `src/isotope/integrations/codex/runtime/summary.py`
- Create: `src/isotope/integrations/codex/runtime/artifacts.py`
- Test: `tests/unit/integrations/codex/runtime/test_projection.py`

- [ ] **Step 1: Write failing projection tests**

Create `tests/unit/integrations/codex/runtime/test_projection.py` with tests for:

```python
from __future__ import annotations

import json

from isotope.integrations.codex.runtime import (
    codex_runtime_summary_artifact_payload,
    project_codex_jsonl_stdout,
)


def _line(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def test_projection_normalizes_messages_tools_reasoning_and_errors() -> None:
    stdout = "\n".join(
        [
            _line({"type": "session.created", "message": "started"}),
            _line(
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"text": "请检查仓库"}],
                    },
                }
            ),
            _line(
                {
                    "type": "response_item",
                    "payload": {
                        "type": "reasoning",
                        "summary": [{"text": "需要查看状态"}],
                    },
                }
            ),
            _line(
                {
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "name": "exec_command",
                        "arguments": {"cmd": "git status", "api_key": "secret"},
                    },
                }
            ),
            _line(
                {
                    "type": "response_item",
                    "payload": {
                        "type": "function_call_output",
                        "output": "## main...origin/main\n",
                    },
                }
            ),
            _line(
                {
                    "type": "event_msg",
                    "payload": {"type": "error", "message": "command failed"},
                }
            ),
            _line(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "最终答复"},
                }
            ),
        ]
    )

    projection = project_codex_jsonl_stdout(
        stdout=stdout,
        stderr="diagnostic stderr",
        status="completed",
        reason_code="codex_cli_completed",
    )

    events = [event.to_dict() for event in projection.events]
    assert [event["kind"] for event in events] == [
        "status",
        "message",
        "reasoning",
        "tool_call",
        "tool_output",
        "error",
        "message",
    ]
    assert events[1]["role"] == "user"
    assert events[1]["text"] == "请检查仓库"
    assert events[3]["title"] == "exec_command"
    assert "secret" not in events[3]["text"]
    assert "[redacted]" in events[3]["text"]
    assert projection.summary.last_agent_message == "最终答复"
    assert projection.summary.error_messages == ["command failed"]
    assert projection.summary.event_counts["tool_call"] == 1
    assert projection.summary.stderr_preview == "diagnostic stderr"


def test_projection_counts_malformed_lines_without_raising() -> None:
    projection = project_codex_jsonl_stdout(
        stdout='{"type":"event_msg","payload":{"type":"status","message":"ok"}}\nnot json\n',
        stderr="",
        status="completed",
        reason_code="codex_cli_completed",
    )

    assert projection.summary.malformed_event_count == 1
    assert [event.kind for event in projection.events] == ["status"]


def test_summary_artifact_payload_is_low_sensitive() -> None:
    projection = project_codex_jsonl_stdout(
        stdout=_line(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": "完成",
                },
            }
        ),
        stderr="stderr raw text",
        status="completed",
        reason_code="codex_cli_completed",
    )

    payload = codex_runtime_summary_artifact_payload(projection)

    assert payload["kind"] == "codex_runtime_summary"
    assert payload["summary"]["last_agent_message"] == "完成"
    assert "stdout" not in json.dumps(payload, ensure_ascii=False)
    assert "stderr raw text" in json.dumps(payload, ensure_ascii=False)
```

- [ ] **Step 2: Run projection tests and verify RED**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/integrations/codex/runtime/test_projection.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'isotope.integrations.codex.runtime'`.

- [ ] **Step 3: Implement runtime dataclasses and projection**

Implement:

- `CodexRuntimeEvent` and `CodexRuntimeSummary` as dataclasses with `to_dict()`.
- `CodexRuntimeProjection` as a dataclass with `to_dict()`.
- `project_codex_jsonl_stdout(...)` to parse response item events, `item.completed`
  agent messages, event messages, malformed lines, and bounded stderr previews.
- Redaction for sensitive keys such as `api_key`, `secret`, `token`, and raw
  prompt/stdout/stderr fields.
- `codex_runtime_summary_artifact_payload(...)` to return a low-sensitive dict.

- [ ] **Step 4: Run projection tests and verify GREEN**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/integrations/codex/runtime/test_projection.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit runtime projection API**

```bash
git add src/isotope/integrations/codex/runtime tests/unit/integrations/codex/runtime/test_projection.py
git commit -m "feat(codex): add runtime projection"
```

### Task 2: Backend Integration

**Files:**
- Modify: `src/isotope/integrations/codex/cli.py`
- Test: `tests/integration/codex/test_codex_cli_backend.py`

- [ ] **Step 1: Write failing backend tests**

Update `test_codex_cli_backend_invokes_codex_exec_with_stdin_and_isotope_limits`
to use a realistic assistant JSONL event and assert:

```python
assert result.summary.startswith('{"kind": "codex_runtime_summary"')
assert "Codex answer" in result.summary
assert len(result.output_artifacts) == 2
assert result.output_artifacts[1].artifact_type == "codex_task_summary"
summary_artifact = json.loads(result.output_artifacts[1].content)
assert summary_artifact["summary"]["last_agent_message"] == "Codex answer"
assert "Inspect the repo" not in result.output_artifacts[1].content
```

Add a new test:

```python
def test_codex_cli_backend_omits_summary_artifact_when_policy_excludes_summary(tmp_path):
    runner = RecordingProcessRunner(
        StubCompletedProcess(
            stdout=json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "Codex answer"},
                }
            )
            + "\n"
        )
    )
    backend = codex_cli.CodexCliBackend(
        codex_cli.CodexCliBackendConfig(
            executable="/opt/codex/bin/codex",
            workspace_root=str(tmp_path),
        ),
        process_runner=runner,
    )
    request = _request(tmp_path)
    request.artifact_policy["capture"] = ["transcript"]

    result = backend.run(request)

    assert [artifact.artifact_type for artifact in result.output_artifacts] == [
        "codex_task_transcript"
    ]
    assert "Codex answer" in result.summary
```

- [ ] **Step 2: Run backend tests and verify RED**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/integration/codex/test_codex_cli_backend.py::test_codex_cli_backend_invokes_codex_exec_with_stdin_and_isotope_limits \
  tests/integration/codex/test_codex_cli_backend.py::test_codex_cli_backend_omits_summary_artifact_when_policy_excludes_summary \
  -q
```

Expected: fail because summary artifacts are not emitted yet.

- [ ] **Step 3: Integrate runtime projection in `CodexCliBackend._result`**

Modify `_result(...)` so it:

- calls `project_codex_jsonl_stdout(...)`;
- uses `json.dumps(codex_runtime_summary_artifact_payload(projection), ensure_ascii=False, sort_keys=True)` as `CodexTaskResult.summary`;
- always keeps `codex_task_transcript`;
- appends `codex_task_summary` only when `"summary"` is in `request.artifact_policy["capture"]`;
- keeps process status, reason code, retryable flag, and resource usage unchanged.

- [ ] **Step 4: Run backend tests and verify GREEN**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/integration/codex/test_codex_cli_backend.py -q
```

Expected: all backend tests pass.

- [ ] **Step 5: Commit backend integration**

```bash
git add src/isotope/integrations/codex/cli.py tests/integration/codex/test_codex_cli_backend.py
git commit -m "feat(codex): summarize runtime output"
```

### Task 3: LLM Provider Reuse And Regression

**Files:**
- Modify: `src/isotope/llm/provider/codex.py`
- Test: `tests/unit/llm/test_llm_provider.py`

- [ ] **Step 1: Write failing provider regression**

Add a test near `test_codex_cli_provider_generates_from_agent_message`:

```python
def test_codex_cli_provider_uses_latest_runtime_agent_message(tmp_path):
    stdout = "\n".join(
        [
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "First"},
                }
            ),
            json.dumps(
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": "Second",
                    },
                }
            ),
        ]
    )

    class Runner:
        def __init__(self) -> None:
            self.calls = []

        def __call__(self, argv, **kwargs):
            self.calls.append({"argv": list(argv), "kwargs": dict(kwargs)})
            return _StubCompletedProcess(stdout=stdout + "\n")

    provider = CodexCliLLMProvider(
        workspace_root=str(tmp_path),
        executable="codex",
        process_runner=Runner(),
        executable_resolver=_resolve_codex_executable,
    )

    response = provider.generate([{"role": "user", "content": "hello"}])

    assert response.content == "Second"
```

- [ ] **Step 2: Run provider test and verify RED**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/llm/test_llm_provider.py::test_codex_cli_provider_uses_latest_runtime_agent_message -q
```

Expected: fail because the old helper reads only `item.completed` agent messages.

- [ ] **Step 3: Reuse runtime projection in `CodexCliLLMProvider`**

Modify `_extract_output_text(...)` to parse transcript stdout through
`project_codex_jsonl_stdout(...)` first and return `projection.summary.last_agent_message`
when present. Keep `_plain_text_or_none(...)` fallback for non-JSONL output.

- [ ] **Step 4: Run provider tests and verify GREEN**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/llm/test_llm_provider.py -q
```

Expected: all provider tests pass.

- [ ] **Step 5: Commit provider reuse**

```bash
git add src/isotope/llm/provider/codex.py tests/unit/llm/test_llm_provider.py
git commit -m "refactor(codex): reuse runtime message projection"
```

### Task 4: Final Verification

**Files:**
- Existing tests and changed-surface gate.

- [ ] **Step 1: Run targeted suite**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/integrations/codex/runtime \
  tests/unit/integrations/codex/test_codex_task_adapter_contract.py \
  tests/integration/codex/test_codex_cli_backend.py \
  tests/unit/llm/test_llm_provider.py \
  tests/unit/integrations/codex/test_codex_transcript.py \
  -q
```

Expected: all tests pass.

- [ ] **Step 2: Run changed-surface gate**

Run:

```bash
scripts/dev-eval changed_surface --base origin/main --json
```

Expected: either `eval_required=false`, or it returns a smoke command to run. If
it recommends a smoke command, run that command and inspect any generated
reviewer prompts before final reporting.

- [ ] **Step 3: Inspect git state**

Run:

```bash
git status --short --branch
git log --oneline --decorate -5
```

Expected: branch contains only the planned commits and no uncommitted changes.
