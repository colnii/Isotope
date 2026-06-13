# Supervisor Prompt Contract Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up the Supervisor desktop-chat decision prompt so it behaves like a stable contract instead of a pile of route-specific prompt patches.

**Architecture:** Keep `conversation_loop.py` as the runtime executor and keep hard checks in runtime guards. Reshape `supervisor/conversation_loop.prompt.md` into concise role, context-boundary, action, and JSON-output sections. Use prompt-manifest tests to lock that route-specific hints leave the system prompt and that capability metadata/observations stay separated.

**Tech Stack:** Python 3.13, pytest, Isotope prompt registry, Supervisor conversation loop.

---

## File Structure

- Modify `src/isotope/llm/prompts/supervisor/conversation_loop.prompt.md`
  - Replace route-specific and patch-like rule prose with a smaller contract.
  - Keep true protocol terms: `capacity_manifest`, `capacity_observation`, `answer_basis`, legal action kinds, low-sensitive result boundary.
- Modify `tests/unit/features/supervisor/conversation/test_prompt_manifest.py`
  - Add prompt-shape regression tests before editing the prompt.
  - Update existing prompt assertions from route-specific wording to contract wording.
- Check `src/isotope/features/supervisor/conversation_loop.py`
  - Do not edit unless tests reveal runtime message construction is mixing context types.

---

### Task 1: Add Failing Prompt Contract Tests

**Files:**
- Modify: `tests/unit/features/supervisor/conversation/test_prompt_manifest.py`

- [ ] **Step 1: Add a route-specific-hints regression test**

Add this test after `test_conversation_loop_prompt_separates_manifest_from_observation`:

```python
def test_conversation_loop_prompt_avoids_route_specific_capacity_hints(
    tmp_path,
) -> None:
    provider = RecordingConversationProvider(
        [no_capability_direct_answer("这条测试只检查 prompt。")]
    )

    list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path / "repo",
            user_message="帮我规划、读文件、查记忆",
            provider=provider,
        )
    )

    system_prompt = provider.calls[0]["messages"][0]["content"]
    prompt_prose = system_prompt.split("capacity_manifest:", 1)[0]
    assert "用户想查已有记忆时优先用 memory.recall" not in prompt_prose
    assert "只有明确要查某个 agent-loop run" not in prompt_prose
    assert "读取文件时优先使用 `file.read`" not in prompt_prose
    assert "当用户要求目标规划" not in prompt_prose
    assert "supervisor.goal_plan" not in prompt_prose
    assert "research_context" not in prompt_prose
```

- [ ] **Step 2: Add a clean contract structure test**

Add this test after the route-specific-hints test:

```python
def test_conversation_loop_prompt_is_a_compact_decision_contract(
    tmp_path,
) -> None:
    provider = RecordingConversationProvider(
        [no_capability_direct_answer("这条测试只检查 prompt。")]
    )

    list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path / "repo",
            user_message="总结当前上下文",
            provider=provider,
        )
    )

    system_prompt = provider.calls[0]["messages"][0]["content"]
    assert "## Role" in system_prompt
    assert "## Context Boundaries" in system_prompt
    assert "## Decision Rules" in system_prompt
    assert "## Output Contract" in system_prompt
    assert len(system_prompt.splitlines()) < 80
```

- [ ] **Step 3: Run the new tests and verify RED**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/supervisor/conversation/test_prompt_manifest.py::test_conversation_loop_prompt_avoids_route_specific_capacity_hints \
  tests/unit/features/supervisor/conversation/test_prompt_manifest.py::test_conversation_loop_prompt_is_a_compact_decision_contract \
  -q
```

Expected: FAIL because the current prompt still contains route-specific capacity hints and does not use the compact contract headings.

---

### Task 2: Rewrite the Prompt as a Clean Contract

**Files:**
- Modify: `src/isotope/llm/prompts/supervisor/conversation_loop.prompt.md`
- Modify: `tests/unit/features/supervisor/conversation/test_prompt_manifest.py`

- [ ] **Step 1: Replace the prompt body**

Rewrite only the `supervisor_conversation_loop` prompt section. Preserve the markdown section markers and `capacity_manifest: {{ capacity_manifest }}` variable.

Use this section shape:

```markdown
## Role
You are the Isotope Supervisor desktop-chat decision layer.

## Context Boundaries
- `capacity_manifest` is discovery metadata.
- `capacity_observation` is runtime evidence.
- History and user messages are conversation context.

## Decision Rules
- Choose from `direct_answer`, `call_capability`, `call_capabilities`, or `report_capability_gap`.
- Let the user's goal and available capability metadata drive the choice.
- Use capabilities when the answer needs current project state, files, memory, screen state, network/MCP data, or execution results.
- Answer directly only when no capability is needed, or when existing observations are enough.
- Report a capability gap only when Isotope lacks the capability or execution boundary needed to continue.

## Output Contract
Keep the existing JSON keys for `kind`, `answer`, `answer_basis`, `capacity_id`,
`arguments`, `calls`, `gap`, and `rationale`.
```

- [ ] **Step 2: Update route-specific old assertions**

Replace assertions in `test_conversation_loop_prompt_routes_goal_planning_to_capacity` so it checks generic capability-selection contract, not `supervisor.goal_plan` route prose:

```python
assert "Let the user's goal and available capability metadata drive the choice." in system_prompt
assert "Use capabilities when the answer needs current project state" in system_prompt
assert "Report a capability gap only when Isotope lacks the capability" in system_prompt
```

- [ ] **Step 3: Run prompt tests and verify GREEN**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/supervisor/conversation/test_prompt_manifest.py \
  -q
```

Expected: PASS.

---

### Task 3: Verify Supervisor Conversation Surface

**Files:**
- No additional source files expected.

- [ ] **Step 1: Run direct-answer guard tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/supervisor/test_conversation_loop_direct_answer_guard.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run changed-surface dev-eval gate**

Run:

```bash
PYTHONPATH=src scripts/dev-eval changed_surface --base origin/main --json
```

Expected: command completes. If `eval_required=true`, run the recommended smoke command from `full_command` or the reported command field and read any reviewer prompt files it creates.

- [ ] **Step 3: Inspect diff**

Run:

```bash
git diff -- src/isotope/llm/prompts/supervisor/conversation_loop.prompt.md tests/unit/features/supervisor/conversation/test_prompt_manifest.py docs/superpowers/plans/2026-06-14-supervisor-prompt-contract-cleanup.md
git diff --check
```

Expected: only prompt/test/plan changes and no whitespace errors.
