# Social LLM Participation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in QQ social runtime mode where an LLM decides whether to participate in ordinary group messages and generates the reply candidate when it chooses to respond.

**Architecture:** Keep `SocialDecisionLoop` as the central decision boundary. Add a focused participation provider module that converts one LLM JSON response into either a silent candidate or a text reply candidate, while existing runtime policy, dry-run, arbitration, and send execution remain in code.

**Tech Stack:** Python 3.13, pytest, existing `isotope.llm.provider` chat provider interface, OneBot/NapCat QQ runtime.

---

### Task 1: Participation Provider Contract

**Files:**
- Create: `src/isotope/features/social/participation_provider.py`
- Create: `tests/unit/features/social/decision/test_llm_participation_provider.py`

- [x] **Step 1: Write failing tests for provider output parsing**

Create `tests/unit/features/social/decision/test_llm_participation_provider.py` with tests for:

```python
from __future__ import annotations

from isotope.features.social.participation_provider import (
    LLMParticipationDecision,
    participation_decision_from_content,
)


def test_participation_decision_parses_respond() -> None:
    decision = participation_decision_from_content(
        '{"action":"respond","reason":"topic fit","confidence":0.73,"text":"可以，我补一句。"}'
    )

    assert decision == LLMParticipationDecision(
        action="respond",
        reason="topic fit",
        confidence=0.73,
        text="可以，我补一句。",
    )


def test_participation_decision_parses_silent() -> None:
    decision = participation_decision_from_content(
        '{"action":"silent","reason":"用户只是记录状态","confidence":0.64}'
    )

    assert decision.action == "silent"
    assert decision.reason == "用户只是记录状态"
    assert decision.confidence == 0.64
    assert decision.text is None


def test_participation_decision_rejects_respond_without_text() -> None:
    try:
        participation_decision_from_content(
            '{"action":"respond","reason":"topic fit","confidence":0.73}'
        )
    except ValueError as exc:
        assert "respond decisions require text" in str(exc)
    else:
        raise AssertionError("expected ValueError")
```

- [x] **Step 2: Run tests and verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/decision/test_llm_participation_provider.py -q
```

Expected: import failure because `participation_provider.py` does not exist.

- [x] **Step 3: Implement minimal parser and value object**

Create `src/isotope/features/social/participation_provider.py` with:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .messages import _required_string_value


@dataclass(frozen=True)
class LLMParticipationDecision:
    action: str
    reason: str
    confidence: float
    text: str | None = None

    def __post_init__(self) -> None:
        if self.action not in {"respond", "silent"}:
            raise ValueError("participation action must be respond or silent")
        _required_string_value(self.reason, "participation reason")
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
            raise ValueError("participation confidence must be between 0 and 1")
        if self.confidence < 0 or self.confidence > 1:
            raise ValueError("participation confidence must be between 0 and 1")
        if self.action == "respond":
            _required_string_value(self.text, "participation text")
        elif self.text is not None and not isinstance(self.text, str):
            raise ValueError("participation text must be a string")


def participation_decision_from_content(content: object) -> LLMParticipationDecision:
    if not isinstance(content, str) or not content.strip():
        raise ValueError("participation provider output must be a JSON object")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("participation provider output must be a JSON object") from exc
    if not isinstance(payload, dict):
        raise ValueError("participation provider output must be a JSON object")
    action = _required_string_value(payload.get("action"), "participation action")
    reason = _required_string_value(payload.get("reason"), "participation reason")
    confidence = payload.get("confidence")
    text = payload.get("text")
    if action == "respond" and (not isinstance(text, str) or not text.strip()):
        raise ValueError("respond decisions require text")
    return LLMParticipationDecision(
        action=action,
        reason=reason,
        confidence=_confidence(confidence),
        text=text.strip() if isinstance(text, str) and text.strip() else None,
    )


def _confidence(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("participation confidence must be between 0 and 1")
    parsed = float(value)
    if parsed < 0 or parsed > 1:
        raise ValueError("participation confidence must be between 0 and 1")
    return parsed
```

- [x] **Step 4: Run parser tests and commit**

Run the same pytest command. Expected: all tests pass.

Commit:

```bash
git add src/isotope/features/social/participation_provider.py tests/unit/features/social/decision/test_llm_participation_provider.py
git commit -m "feat(social): add llm participation decision parser"
```

### Task 2: LLM Participation Provider

**Files:**
- Modify: `src/isotope/features/social/participation_provider.py`
- Create: `src/isotope/llm/prompts/social_participation.md`
- Create: `src/isotope/llm/prompts/social_participation_user.md`
- Modify: `tests/unit/features/social/decision/test_llm_participation_provider.py`

- [x] **Step 1: Add failing test for provider prompt and metadata**

Append a fake chat provider test that calls `LLMSocialParticipationProvider.decide(...)` with a minimal `SocialDecisionRequest` and asserts:

```python
assert decision.action == "respond"
assert decision.text == "可以，我补一句。"
assert fake_provider.messages[0]["role"] == "system"
assert "required_json_shape" in fake_provider.messages[1]["content"]
```

- [x] **Step 2: Run test and verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/decision/test_llm_participation_provider.py -q
```

Expected: import failure for `LLMSocialParticipationProvider`.

- [x] **Step 3: Implement provider**

Add `LLMSocialParticipationProvider` to `participation_provider.py`. It should:

- validate `chat_provider.generate`
- render `social_participation` and `social_participation_user` prompts
- pass `wake_signals`, `persona_instructions`, `chat_context`, `dry_run`, and the required JSON shape
- return `LLMParticipationDecision` with metadata from the LLM response

Prompt files should mirror the existing `social_reply` prompt style and require JSON only.

- [x] **Step 4: Run provider tests and commit**

Run the provider test file. Expected: all tests pass.

Commit:

```bash
git add src/isotope/features/social/participation_provider.py src/isotope/llm/prompts/social_participation.md src/isotope/llm/prompts/social_participation_user.md tests/unit/features/social/decision/test_llm_participation_provider.py
git commit -m "feat(social): add llm participation provider"
```

### Task 3: Decision Loop Wiring

**Files:**
- Modify: `src/isotope/features/social/loop.py`
- Create: `tests/unit/features/social/decision/test_social_decision_llm_participation.py`

- [x] **Step 1: Write failing decision-loop tests**

Create tests proving:

- default `SocialDecisionLoop()` still returns `silent/no_wake_reason` for an ordinary message.
- `SocialDecisionLoop(participation_provider=fake_provider)` can respond to an ordinary message without mention or keyword.
- dry-run records the LLM reply candidate and selects nothing.
- invalid provider output degrades to a silent candidate with provider error metadata.

- [x] **Step 2: Run decision tests and verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/decision/test_social_decision_llm_participation.py -q
```

Expected: constructor does not accept `participation_provider`.

- [x] **Step 3: Implement loop support**

Modify `SocialDecisionLoop` to accept `participation_provider: SocialParticipationProvider | None = None`.

Flow:

- recent-send suppression still returns forced silent.
- if `participation_provider is None`, keep existing `_wake_reasons` flow.
- if provider exists, compute wake signals and call provider.
- `silent` provider decision becomes a `silent` candidate.
- `respond` provider decision becomes `reply_text` candidate using provider text.
- dry-run keeps proposed candidates and selects nothing for send candidates.
- provider exceptions degrade to silent with metadata containing `provider_error`.

- [x] **Step 4: Run decision tests and commit**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/decision/test_social_decision_llm_participation.py tests/unit/features/social/test_social_decision_loop.py -q
```

Expected: all tests pass.

Commit:

```bash
git add src/isotope/features/social/loop.py tests/unit/features/social/decision/test_social_decision_llm_participation.py
git commit -m "feat(social): let llm decide participation"
```

### Task 4: QQ Runtime Config Wiring

**Files:**
- Modify: `src/isotope/features/social/qq_runtime_commands.py`
- Create: `tests/unit/features/social/decision/test_social_qq_llm_participation_config.py`

- [ ] **Step 1: Write failing config wiring tests**

Create tests proving:

- `runtime.participation_provider` defaults to rules and does not require LLM config.
- `runtime.participation_provider = "llm"` injects an LLM participation provider.
- missing LLM provider raises `ValueError("LLM participation provider is not configured: ...")`.
- invalid value raises `ValueError("runtime.participation_provider must be rules or llm")`.

- [ ] **Step 2: Run tests and verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/decision/test_social_qq_llm_participation_config.py -q
```

Expected: config value is ignored.

- [ ] **Step 3: Implement config wiring**

Modify `decision_loop_from_config`:

- read `runtime.participation_provider`, default `"rules"`
- validate it is `"rules"` or `"llm"`
- if `"llm"`, resolve chat provider and pass `LLMSocialParticipationProvider(chat_provider=resolution.provider)`
- keep existing `runtime.reply_provider` validation for rule-based reply generation

- [ ] **Step 4: Run config tests and commit**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/decision/test_social_qq_llm_participation_config.py tests/unit/features/social/decision/test_social_decision_llm_participation.py -q
```

Expected: all tests pass.

Commit:

```bash
git add src/isotope/features/social/qq_runtime_commands.py tests/unit/features/social/decision/test_social_qq_llm_participation_config.py
git commit -m "feat(social): wire qq llm participation config"
```

### Task 5: Docs And Verification

**Files:**
- Modify: `docs/current/qq-group-chatbot.md`
- Modify: `docs/current/qq-group-chatbot-operations.md`
- Test: relevant social tests

- [ ] **Step 1: Document opt-in mode**

Add a short section showing:

```json
{
  "runtime": {
    "participation_provider": "llm",
    "reply_provider": "llm"
  }
}
```

Explain that ordinary messages may be answered or ignored by the LLM, while dry-run and send-run boundaries remain system controlled.

- [ ] **Step 2: Run focused tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/decision tests/unit/features/social/test_social_decision_loop.py tests/unit/features/social/test_social_reply_provider.py tests/unit/features/social/test_social_runner_structure.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Run QQ live dry-run smoke manually**

Use the existing local NapCat config with a temporary JSON config that sets both providers to `llm`, but do not pass `--send`.

Expected: a normal group message can produce either an LLM `silent` or an LLM `reply_text` candidate, and `send_feedback` remains empty.

- [ ] **Step 4: Commit docs**

Commit:

```bash
git add docs/current/qq-group-chatbot.md docs/current/qq-group-chatbot-operations.md
git commit -m "docs(social): describe llm participation mode"
```

- [ ] **Step 5: Final branch verification**

Run:

```bash
git diff --check
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/decision tests/unit/features/social/test_social_decision_loop.py tests/unit/features/social/test_social_reply_provider.py tests/integration/social/test_qq_runtime_wiring.py -q
```

Expected: diff check passes and all selected tests pass.
