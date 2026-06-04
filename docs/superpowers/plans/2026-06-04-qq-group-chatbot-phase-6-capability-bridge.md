# QQ Group Chatbot Phase 6 Capability Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let social agents call Isotope capabilities while returning useful result reports and concrete failure reports to the group decision loop.

**Architecture:** Reuse `SocialActionCandidate(kind="call_capability")` as the social intent and `CapabilityRunner.plan_capability_run/run_capability` as the execution boundary. The bridge checks role permissions and approval requirements before calling the runner, then normalizes success, blocked, approval, and failure outcomes into `SocialInformationReport`.

**Tech Stack:** Python 3.13, pytest, dataclasses.

---

## Reuse Audit

- Reuse `CharacterCard.tools.allowed_capabilities` as the role-level allowed capability list.
- Reuse `SocialActionCandidate.capability_id` and `metadata` as the request source.
- Reuse existing `CapabilityRunner` methods instead of wrapping catalog metadata manually.
- Do not execute real network/tool actions in unit tests; use a fake runner with the same method names.
- Do not hide missing or failed access behind a vague fallback; reports must name the capability and reason.

## File Structure

- Create `src/isotope/features/social/information_report.py`: normalized report shape.
- Create `src/isotope/features/social/capability_bridge.py`: permission, approval, plan, run, and failure handling.
- Modify `src/isotope/features/social/__init__.py`: export Phase 6 names.
- Create `tests/unit/features/social/test_social_capability_bridge.py`: permitted, forbidden, failed, and approval tests.

## Task 1: Capability Bridge

**Files:**
- Create: `src/isotope/features/social/information_report.py`
- Create: `src/isotope/features/social/capability_bridge.py`
- Modify: `src/isotope/features/social/__init__.py`
- Test: `tests/unit/features/social/test_social_capability_bridge.py`

- [ ] **Step 1: Write failing tests**

Create tests proving:

- a permitted capability returns a completed report with useful content;
- a capability absent from the role card allowed list returns a blocked report;
- a runner failure names the capability and concrete error;
- a capability requiring operator approval returns an approval report until approval is provided.

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_capability_bridge.py -q
```

Expected: FAIL because `SocialCapabilityBridge` and `SocialInformationReport` do not exist.

- [ ] **Step 3: Implement information report and bridge**

Create `SocialInformationReport` with:

- `status`: `completed`, `blocked`, `failed`, `missing_inputs`, `requires_operator_approval`
- `capability_id`
- `target`
- `reason`
- `content`
- `raw_result`

Create `SocialCapabilityBridge` with:

- `run(candidate, character_card, group_id, inputs={}, operator_approved=False)`
- role allowed-list check before runner calls;
- approval-required check before runner calls;
- launch plan check using `plan_capability_run`;
- execution using `run_capability`;
- concrete exception capture including capability id and error text.

- [ ] **Step 4: Run bridge tests**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_capability_bridge.py -q
```

Expected: PASS.

## Task 2: Regression And Product Acceptance

- [ ] **Step 1: Run full social regression**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social -q
```

Expected: all social tests pass.

- [ ] **Step 2: Run shared supervisor regression**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py tests/integration/supervisor/test_supervisor_desktop_chat.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run diff hygiene**

```bash
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 4: Product checklist**

Confirm from tests and code:

- tool use can provide content the social loop can answer with;
- forbidden access names the exact capability and role policy reason;
- runner failures name the exact capability and error text;
- approval-required actions are surfaced instead of silently ignored.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-06-04-qq-group-chatbot-phase-6-capability-bridge.md src/isotope/features/social tests/unit/features/social/test_social_capability_bridge.py
git commit -m "feat(social): add capability bridge"
```
