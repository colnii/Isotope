# Social QQ Personality Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make QQ runtime turns expose role-card-driven personality instructions
and inspectable group chat context, so dry-run/replay output can prove the bot is
using the configured role card and the current group message context.

**Architecture:** Reuse the existing `CharacterCard`, group override,
`SocialContextBuilder`, and QQ runtime path. Do not add another persona system.
Extend the context payload with:

- `persona_instructions`: a direct, structured summary of active role identity,
  voice, social behavior, sticker preference, tool style, memory policy, group
  ID, and whether a group override was applied.
- `chat_context`: current message, recent messages, memory previews, and
  selected lorebook entries grouped together for decision/LLM consumers.

Keep existing top-level context fields for compatibility.

---

### Task 1: Context Builder Red Test

**Files:**
- Modify: `tests/unit/features/social/test_social_context_builder.py`

- [x] **Step 1: Assert personality and chat context output**

Add assertions that a group-overridden card emits `persona_instructions` with
the active voice/social/sticker/tool/memory settings, plus `chat_context` with
the current QQ message, recent messages, memory previews, and selected lorebook
entries.

- [x] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_context_builder.py -q
```

Expected: FAIL because `persona_instructions` does not exist yet.

### Task 2: Implement Context Payload

**Files:**
- Modify: `src/isotope/features/social/context_builder.py`

- [x] **Step 1: Build persona instructions from active group card**

Use `CharacterCard.for_group(group_id)` as the source of truth. Include the
group override flag, but do not mutate the base card.

- [x] **Step 2: Group conversation context**

Add `chat_context` while preserving existing top-level `message`,
`recent_messages`, `memory_previews`, and `lorebook_entries` fields.

### Task 3: QQ Text Normalization and CLI Acceptance

**Files:**
- Modify: `tests/unit/integrations/qq/test_onebot_adapter.py`
- Modify: `src/isotope/integrations/qq/onebot_adapter.py`
- Modify: `tests/unit/features/social/test_social_runner.py`

- [x] **Step 1: Add adapter red test**

Assert that `SocialMessage.text` is the readable text segment content, not the
raw CQ string.

- [x] **Step 2: Fix adapter source**

Make `OneBotAdapter` join text segments for `SocialMessage.text`, falling back
to `raw_message` only when there is no text segment.

- [x] **Step 3: Assert QQ CLI dry-run output**

Check that `qq dry-run` returns `persona_instructions` and `chat_context` in the
turn context.

### Task 4: Verification

- [x] **Step 1: Final verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_context_builder.py tests/unit/integrations/qq/test_onebot_adapter.py tests/unit/features/social/test_social_runner.py tests/unit/features/social tests/integration/social/test_qq_runtime_wiring.py tests/integration/social/test_social_fake_platform_flow.py tests/unit/integrations/qq/test_onebot_ws_client.py tests/integration/qq/test_fake_onebot_flow.py tests/unit/docs/test_qq_group_chatbot_docs.py -q
git diff --check
```

Expected: tests pass and whitespace check has no output.

### Acceptance Standard

- Dry-run/replay/runtime JSON exposes the active role-card personality settings
  in `turn.context.persona_instructions`.
- Dry-run/replay/runtime JSON exposes current group message context in
  `turn.context.chat_context`.
- QQ `SocialMessage.text` is readable message text, while mentions remain in
  `mentions` and `parts`.
- Existing context keys and QQ CLI behavior remain compatible.
