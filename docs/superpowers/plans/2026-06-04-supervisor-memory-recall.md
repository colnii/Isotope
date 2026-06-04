# Supervisor Memory Recall Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make desktop/Supervisor chat able to recall existing low-sensitive memory records from the active `state_root` without requiring the model to know an internal `run_id`.

**Architecture:** Keep `memory.query` as the strict run-audited capability for agent-loop internals. Add a product-facing read-only `memory.recall` capability that reuses `isotope.memory.views.build_memory_query_payload(...)`, accepts `root/query/scope/limit` plus optional filters, and returns only summary / refs / provenance previews. Expose `memory.recall` through the capability catalog and conversation loop so the app can retrieve existing state-root memory while preserving the no-full-content boundary.

**Tech Stack:** Python 3.13, pytest, Isotope capability runner, `FileMemoryStore`, `MemoryRecord`, Supervisor conversation loop.

---

## File Structure

- Modify `src/isotope/memory/views.py`
  - Add explicit `content_policy` to `build_memory_query_payload(...)` so app-level recall has a stable public contract.
- Modify `src/isotope/capabilities/memory.py`
  - Add `MEMORY_RECALL_CAPABILITY`, validation, and `run_memory_recall(...)`.
  - Keep `memory.query` unchanged.
- Modify `src/isotope/capabilities/runner.py`
  - Import and dispatch `memory.recall`.
- Modify `src/isotope/capabilities/catalog.py`
  - Register `memory.recall` as product-candidate, deterministic, read-only, low-sensitive.
- Modify `src/isotope/features/supervisor/conversation_observations.py`
  - Let conversation observations summarize `memory.recall` results the same way as `memory.query`.
- Modify `src/isotope/llm/prompts/supervisor_conversation_loop.md`
  - Fix the misleading `run_id` wording and tell the model to prefer `memory.recall` for user-facing memory recall.
- Test `tests/unit/memory/test_memory_views.py`
  - Lock the `content_policy` contract.
- Test `tests/unit/capabilities/test_capability_runner_thin_shell.py`
  - Lock catalog, launch, and runner behavior for `memory.recall`.
- Test `tests/unit/features/supervisor/test_supervisor_conversation_loop.py`
  - Reproduce the desktop chat failure and verify `memory.recall` returns existing state-root memory without raw content.
- Optional docs update `docs/current/agent-task-queue.md` or `docs/current/supervisor-command-reference.md`
  - Add one short note distinguishing `memory.query` from `memory.recall`.

---

### Task 1: Add Failing App-Path Regression Test

**Files:**
- Modify: `tests/unit/features/supervisor/test_supervisor_conversation_loop.py`

- [ ] **Step 1: Add imports for memory fixtures**

Add these imports near the existing imports:

```python
from isotope.platform.schemas.memory import MemoryRecord
```

- [ ] **Step 2: Add a direct fixture writer helper**

Add this helper near the other test helpers. It uses the same fixture pattern already used in memory tests and does not bypass production write authorization in application code.

```python
def _write_memory_record(memory_dir, record: MemoryRecord) -> None:
    memory_dir.mkdir(parents=True, exist_ok=True)
    memory_dir.joinpath(f"{record.memory_id}.json").write_text(
        json.dumps(asdict(record), sort_keys=True),
        encoding="utf-8",
    )
```

If `asdict` is not already imported in the file, add:

```python
from dataclasses import asdict
```

- [ ] **Step 3: Write the failing desktop recall test**

Add this test after `test_conversation_loop_calls_capability_then_returns_final_answer`:

```python
def test_conversation_loop_recalls_existing_state_root_memory_without_run_id(
    tmp_path,
) -> None:
    memory_dir = tmp_path / "state" / "memory"
    _write_memory_record(
        memory_dir,
        MemoryRecord(
            memory_id="mem_desktop_recall",
            scope="run",
            content={"raw": "raw memory content must not leak"},
            summary="Desktop chat should recall this state-root memory preview.",
            source_refs=[{"ref_type": "artifact", "artifact_id": "artifact_memory"}],
            provenance={
                "run_id": "run_real_memory",
                "execution_id": "exec_real_memory",
                "action_type": "write_memory",
            },
            created_at="2026-06-04T00:00:00Z",
            supersedes=[],
            quality="verified",
        ),
    )
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "memory.recall",
                    "arguments": {
                        "query": "state-root memory preview",
                        "scope": "run",
                    },
                    "rationale": "Recall public memory preview.",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "找到了相关记忆。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path / "repo",
            user_message="查一下 state-root memory preview 的记忆",
            provider=provider,
            max_turns=3,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert events[0].payload["capacity_id"] == "memory.recall"
    assert events[0].payload["input_summary"] == {
        "query": "state-root memory preview",
        "root": str(tmp_path / "state"),
        "scope": "run",
    }
    assert events[1].payload["status"] == "ok"
    summary = events[1].payload["result_summary"]
    assert summary["agent_loop_memory_recall_status"] == "ok"
    assert summary["agent_loop_memory_recall_result_count"] == 1
    rendered_events = json.dumps([event.payload for event in events], ensure_ascii=False)
    assert "Desktop chat should recall this state-root memory preview." in rendered_events
    assert "raw memory content must not leak" not in rendered_events
```

- [ ] **Step 4: Run the failing test**

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_loop_recalls_existing_state_root_memory_without_run_id -q
```

Expected: FAIL with `ValueError: unknown capability: memory.recall` or a missing summary key.

- [ ] **Step 5: Commit the failing regression test only if using a TDD branch checkpoint**

```bash
git add tests/unit/features/supervisor/test_supervisor_conversation_loop.py
git commit -m "test(supervisor): cover state-root memory recall in chat"
```

Skip this commit if the team prefers red/green in one local commit.

---

### Task 2: Add Product-Facing Memory Recall Capability

**Files:**
- Modify: `src/isotope/memory/views.py`
- Modify: `src/isotope/capabilities/memory.py`
- Modify: `src/isotope/capabilities/runner.py`
- Modify: `src/isotope/capabilities/catalog.py`
- Test: `tests/unit/memory/test_memory_views.py`
- Test: `tests/unit/capabilities/test_capability_runner_thin_shell.py`

- [ ] **Step 1: Lock memory view content policy**

In `tests/unit/memory/test_memory_views.py`, add this assertion to `test_memory_views_build_memory_query_payload_without_content`:

```python
assert payload["content_policy"] == "memory_record_refs_expandable"
```

- [ ] **Step 2: Run the memory view test and verify it fails**

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/unit/memory/test_memory_views.py::test_memory_views_build_memory_query_payload_without_content -q
```

Expected: FAIL with `KeyError: 'content_policy'`.

- [ ] **Step 3: Add content policy to memory query payload**

In `src/isotope/memory/views.py`, update the returned dict in `build_memory_query_payload(...)`:

```python
return {
    "status": "ok",
    "content_policy": "memory_record_refs_expandable",
    "store": {
        "root": str(root_path),
        "path": str(root_path / "memory"),
        "format": "file_memory_store",
    },
    "query": clean_query,
    "scope": scope,
    "run_id": run_id,
    "session_id": session_id,
    "summary": {
        "total": len(records),
        "matched": len(matched.all_matches),
        "hidden_records": max(0, len(matched.all_matches) - len(matched.visible)),
    },
    "results": [_memory_query_result(record) for record in matched.visible],
}
```

- [ ] **Step 4: Add capability runner tests**

In `tests/unit/capabilities/test_capability_runner_thin_shell.py`, add this test after `test_memory_query_capability_runs_existing_public_metadata_query`:

```python
def test_memory_recall_capability_runs_state_root_preview_query(tmp_path):
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    _write_memory_record(
        memory_dir,
        MemoryRecord(
            memory_id="mem_recall",
            scope="run",
            content={"raw": "raw memory content must not leak"},
            summary="Capability runner can recall app-level memory previews.",
            source_refs=[{"ref_type": "artifact", "artifact_id": "artifact_memory"}],
            provenance={
                "run_id": "run_memory",
                "execution_id": "exec_memory",
                "action_type": "write_memory",
            },
            created_at="2026-06-04T00:00:00Z",
            supersedes=[],
            quality="verified",
        ),
    )

    result = _runner().run_capability(
        "memory.recall",
        inputs={
            "root": str(tmp_path),
            "query": "app-level memory previews",
            "scope": "run",
        },
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "memory.recall"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_readonly"
    recall = result["memory_recall"]
    assert recall["status"] == "ok"
    assert recall["content_policy"] == "memory_record_refs_expandable"
    assert recall["summary"]["matched"] == 1
    assert recall["results"] == [
        {
            "record_id": "mem_recall",
            "scope": "run",
            "summary": "Capability runner can recall app-level memory previews.",
            "source_refs": [{"ref_type": "artifact", "artifact_id": "artifact_memory"}],
            "provenance": {
                "run_id": "run_memory",
                "execution_id": "exec_memory",
                "action_type": "write_memory",
            },
            "quality": "verified",
        }
    ]
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)
```

Also add this small catalog assertion near the existing memory catalog assertions:

```python
def test_memory_recall_capability_is_registered_as_readonly_product_candidate():
    runner = _runner()
    assert "memory.recall" in _ids(runner.list_capabilities())
    description = runner.describe_capability("memory.recall")
    assert description["shelf"] == "product_candidate"
    assert description["network_required"] is False
    assert description["input_contract"]["required"] == ["root", "query"]
    assert description["input_contract"]["properties"]["root"]["x-system-input"] is True
```

- [ ] **Step 5: Run capability tests and verify they fail**

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/unit/capabilities/test_capability_runner_thin_shell.py::test_memory_recall_capability_is_registered_as_readonly_product_candidate tests/unit/capabilities/test_capability_runner_thin_shell.py::test_memory_recall_capability_runs_state_root_preview_query -q
```

Expected: FAIL because `memory.recall` is not registered.

- [ ] **Step 6: Implement memory.recall in capability code**

In `src/isotope/capabilities/memory.py`, add the constant:

```python
MEMORY_RECALL_CAPABILITY = "memory.recall"
```

Update `is_memory_readonly_capability(...)`:

```python
def is_memory_readonly_capability(capability_id: str) -> bool:
    return capability_id in {
        MEMORY_QUERY_CAPABILITY,
        MEMORY_RECALL_CAPABILITY,
        MEMORY_PROMOTION_PREVIEW_CAPABILITY,
    }
```

Update `validate_memory_readonly_inputs(...)`:

```python
def validate_memory_readonly_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    if capability_id == MEMORY_QUERY_CAPABILITY:
        return _validate_memory_query_inputs(
            inputs=inputs,
            missing_inputs=missing_inputs,
        )
    if capability_id == MEMORY_RECALL_CAPABILITY:
        return _validate_memory_recall_inputs(
            inputs=inputs,
            missing_inputs=missing_inputs,
        )
    if capability_id == MEMORY_PROMOTION_PREVIEW_CAPABILITY:
        return _validate_memory_promotion_preview_inputs(
            inputs=inputs,
            missing_inputs=missing_inputs,
        )
    return dict(inputs or {})
```

Add the runner:

```python
def run_memory_recall(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    required_inputs = ["root", "query"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = _validate_memory_recall_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    payload = build_memory_query_payload(
        root=input_mapping["root"],
        query=input_mapping["query"],
        scope=input_mapping.get("scope"),
        run_id=input_mapping.get("run_id"),
        session_id=input_mapping.get("session_id"),
        limit=input_mapping["limit"],
    )
    return {
        "kind": "capability_run_result",
        "capability_id": MEMORY_RECALL_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_readonly",
        "memory_recall": payload,
    }
```

Add validation:

```python
def _validate_memory_recall_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    input_mapping = inputs or {}
    for name in ("root", "query"):
        if name in missing_inputs:
            continue
        value = input_mapping.get(name)
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        if not value.strip():
            raise ValueError(f"{name} must be a non-empty string")

    scope = input_mapping.get("scope")
    if scope is not None and scope not in VALID_MEMORY_QUERY_SCOPES:
        raise ValueError("scope must be thread, run, or session")

    for name in ("run_id", "session_id"):
        value = input_mapping.get(name)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"{name} must be a non-empty string")

    limit = input_mapping.get("limit", 20)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive integer")

    normalized = dict(input_mapping)
    normalized["limit"] = limit
    return normalized
```

Add the import near the top:

```python
from ..memory.views import build_memory_query_payload
```

- [ ] **Step 7: Dispatch memory.recall in CapabilityRunner**

In `src/isotope/capabilities/runner.py`, extend the memory import:

```python
from .memory import (
    MEMORY_PROMOTION_PREVIEW_CAPABILITY,
    MEMORY_QUERY_CAPABILITY,
    MEMORY_RECALL_CAPABILITY,
    is_memory_readonly_capability,
    run_memory_promotion_preview,
    run_memory_query,
    run_memory_recall,
    validate_memory_readonly_inputs,
)
```

Add dispatch after `memory.query`:

```python
if capability_id == MEMORY_QUERY_CAPABILITY:
    return run_memory_query(inputs=input_mapping)
if capability_id == MEMORY_RECALL_CAPABILITY:
    return run_memory_recall(inputs=input_mapping)
if capability_id == MEMORY_PROMOTION_PREVIEW_CAPABILITY:
    return run_memory_promotion_preview(inputs=input_mapping)
```

- [ ] **Step 8: Register memory.recall in the catalog**

In `src/isotope/capabilities/catalog.py`, add this `Capability(...)` after `memory.query`:

```python
Capability(
    capability_id="memory.recall",
    title="Memory Recall",
    description=(
        "Search local state-root memory previews without requiring the model "
        "to know an internal agent-loop run id."
    ),
    maturity="v0.2",
    shelf="product_candidate",
    domain_tags=("memory", "recall", "query", "preview", "provenance"),
    input_contract={
        "type": "object",
        "required": ["root", "query"],
        "properties": {
            "root": {
                "type": "string",
                "x-system-input": True,
                "description": "Runtime root containing memory/*.json.",
            },
            "query": {
                "type": "string",
                "description": "Public memory search query.",
            },
            "scope": {
                "type": "string",
                "enum": ["thread", "run", "session"],
                "description": "Optional memory scope filter.",
            },
            "run_id": {
                "type": "string",
                "description": "Optional provenance run id filter when the user names a run.",
            },
            "session_id": {
                "type": "string",
                "description": "Optional provenance session id filter when the user names a session.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum records to preview.",
                "default": 20,
            },
        },
    },
    output_contract={
        "type": "object",
        "fields": [
            "status",
            "content_policy",
            "summary",
            "results",
        ],
    },
    safety_boundaries=(
        "memory_preview_only",
        "summary_refs_provenance_only",
        "no_memory_record_content",
        "no_source_artifact_full_content_read",
    ),
    default_enabled=True,
    network_required=False,
)
```

- [ ] **Step 9: Run memory/capability tests**

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/unit/memory/test_memory_views.py::test_memory_views_build_memory_query_payload_without_content tests/unit/capabilities/test_capability_runner_thin_shell.py::test_memory_recall_capability_is_registered_as_readonly_product_candidate tests/unit/capabilities/test_capability_runner_thin_shell.py::test_memory_recall_capability_runs_state_root_preview_query -q
```

Expected: PASS.

- [ ] **Step 10: Commit capability slice**

```bash
git add src/isotope/memory/views.py src/isotope/capabilities/memory.py src/isotope/capabilities/runner.py src/isotope/capabilities/catalog.py tests/unit/memory/test_memory_views.py tests/unit/capabilities/test_capability_runner_thin_shell.py
git commit -m "feat(memory): add app-level recall capability"
```

---

### Task 3: Wire Memory Recall Into Supervisor Chat Observations

**Files:**
- Modify: `src/isotope/features/supervisor/conversation_observations.py`
- Modify: `src/isotope/features/supervisor/commands/capacity_summary.py`
- Modify: `src/isotope/llm/prompts/supervisor_conversation_loop.md`
- Test: `tests/unit/features/supervisor/test_supervisor_conversation_loop.py`

- [ ] **Step 1: Add memory.recall observation support**

In `src/isotope/features/supervisor/conversation_observations.py`, update `_capability_result_observation(...)`:

```python
if capacity_id in {"memory.query", "memory.recall"}:
    return _memory_query_observation(capability_run)
```

Then update `_memory_query_observation(...)` so it accepts either payload key:

```python
def _memory_query_observation(capability_run: dict[str, Any]) -> dict[str, Any] | None:
    memory_query = capability_run.get("memory_query")
    kind = "memory_query"
    if not isinstance(memory_query, dict):
        memory_query = capability_run.get("memory_recall")
        kind = "memory_recall"
    if not isinstance(memory_query, dict):
        return None
    results = memory_query.get("results")
    safe_results: list[dict[str, Any]] = []
    if isinstance(results, list):
        for result in results:
            if not isinstance(result, dict):
                continue
            safe_result = _safe_memory_query_result(result)
            if safe_result is not None:
                safe_results.append(safe_result)
    return {
        "kind": kind,
        "status": (
            memory_query.get("status")
            if isinstance(memory_query.get("status"), str)
            else ""
        ),
        "content_policy": (
            memory_query.get("content_policy")
            if isinstance(memory_query.get("content_policy"), str)
            else ""
        ),
        "result_count": len(results) if isinstance(results, list) else 0,
        "results": safe_results,
    }
```

- [ ] **Step 2: Add summary support for memory.recall**

In `src/isotope/features/supervisor/commands/capacity_summary.py`, update the summary helper so it can summarize `memory_recall` separately. Add this near the existing memory query summary logic:

```python
def _agent_loop_memory_recall_summary(
    capability_run: Mapping[str, Any],
) -> dict[str, Any]:
    if capability_run.get("capability_id") != "memory.recall":
        return {}
    memory_recall = capability_run.get("memory_recall")
    if not isinstance(memory_recall, Mapping):
        return {}
    results = memory_recall.get("results")
    summary = {
        "agent_loop_memory_recall_status": memory_recall.get("status"),
        "agent_loop_memory_recall_result_count": (
            len(results) if isinstance(results, list) else 0
        ),
    }
    content_policy = memory_recall.get("content_policy")
    if isinstance(content_policy, str):
        summary["agent_loop_memory_recall_content_policy"] = content_policy
    return summary
```

Then add this update where `agent_loop_json_summary(...)` combines capability summaries:

```python
summary.update(_agent_loop_memory_recall_summary(capability_run))
```

- [ ] **Step 3: Update the Supervisor conversation prompt**

In `src/isotope/llm/prompts/supervisor_conversation_loop.md`, replace this line:

```markdown
- call_capability.arguments 只填 capability input_contract 允许的字段；系统会补 state_root/root/cwd/run_id 等已知上下文。
```

with:

```markdown
- call_capability.arguments 只填 capability input_contract 允许的字段；系统会补带 x-system-input 的 state_root/root/cwd 等上下文。用户想查已有记忆时优先用 memory.recall；只有明确要查某个 agent-loop run 的内部记忆时才用 memory.query 并提供 run_id。
```

- [ ] **Step 4: Run the desktop recall regression test**

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_loop_recalls_existing_state_root_memory_without_run_id -q
```

Expected: PASS.

- [ ] **Step 5: Run nearby Supervisor conversation tests**

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_manifest_hides_system_routing_inputs tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_loop_filters_model_supplied_inputs_to_capability_contract tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_loop_calls_capability_then_returns_final_answer -q
```

Expected: PASS.

- [ ] **Step 6: Commit Supervisor chat wiring**

```bash
git add src/isotope/features/supervisor/conversation_observations.py src/isotope/features/supervisor/commands/capacity_summary.py src/isotope/llm/prompts/supervisor_conversation_loop.md tests/unit/features/supervisor/test_supervisor_conversation_loop.py
git commit -m "fix(supervisor): recall memory previews in chat"
```

---

### Task 4: Document the Contract Boundary and Run Final Verification

**Files:**
- Modify: `docs/current/agent-task-queue.md`
- Optional Modify: `docs/current/supervisor-command-reference.md`

- [ ] **Step 1: Add a short contract note**

In `docs/current/agent-task-queue.md`, add this bullet near the existing memory query bullets:

```markdown
- `memory.recall` 是面向 Supervisor / desktop chat 的应用层记忆召回能力：
  它从当前 `state_root` 的 `memory/*.json` 搜索 summary / refs / provenance preview，
  不要求模型知道内部 agent-loop `run_id`，也不返回 raw memory content。
  `memory.query` 保留为需要显式 `run_id` 的 agent-loop 内部精确查询能力。
```

- [ ] **Step 2: Run targeted verification**

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/unit/memory/test_memory_views.py tests/unit/capabilities/test_capability_runner_thin_shell.py tests/unit/features/supervisor/test_supervisor_conversation_loop.py -q
```

Expected: PASS.

- [ ] **Step 3: Inspect public manifest manually**

Run:

```bash
PYTHONPATH=src python3 - <<'PY'
from isotope.capabilities.runner import CapabilityRunner
cap = CapabilityRunner().describe_capability("memory.recall")
print(cap["capability_id"])
print(cap["input_contract"]["required"])
print(cap["safety_boundaries"])
PY
```

Expected output includes:

```text
memory.recall
['root', 'query']
```

and safety boundaries include `no_memory_record_content`.

- [ ] **Step 4: Check diff scope**

Run:

```bash
git status --short
git diff --stat
```

Expected: only memory capability, Supervisor conversation, prompt, docs, and test files changed.

- [ ] **Step 5: Commit docs and final verification evidence**

```bash
git add docs/current/agent-task-queue.md
git commit -m "docs(supervisor): clarify memory recall boundary"
```

- [ ] **Step 6: Push the branch**

```bash
git push -u origin HEAD
```

Expected: branch pushes successfully.

---

## Reuse Audit

- Reuse `FileMemoryStore` for local state-root records.
- Reuse `isotope.memory.views.build_memory_query_payload(...)` because it already searches memory summaries / refs / provenance without returning `content`.
- Reuse `CapabilityRunner` deterministic read-only dispatch patterns from `memory.query`.
- Reuse `conversation_observations._memory_query_observation(...)` shape to avoid adding a second observation format.
- Do not change `LocalMemoryQueryService.query(...)` semantics; its run/session audit boundary is correct for agent-loop internals.
- Do not add vector search, embeddings, automatic promotion, or full-content expansion in this slice.

## Success Criteria

- Desktop/Supervisor chat can call `memory.recall` with only `query` and system-provided `root`.
- Existing state-root run-scope memory records can be found even when their `provenance.run_id` is not the temporary conversation-loop run id.
- Raw `MemoryRecord.content` never appears in capability output, event payloads, observations, or tests.
- `memory.query` continues to require `run_id` and remains available for precise agent-loop recall.
- Prompt no longer claims that the system supplements `run_id` for all capabilities.
