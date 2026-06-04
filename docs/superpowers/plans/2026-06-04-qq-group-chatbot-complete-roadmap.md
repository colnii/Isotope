# QQ Group Chatbot Complete Implementation Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to
> create a phase-specific implementation plan before coding each phase. For
> implementation execution, use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`)
> syntax for tracking.

**Goal:** Implement the complete QQ group chatbot described in
`docs/superpowers/specs/2026-06-04-qq-group-chatbot-complete-design.md`.

**Architecture:** Build a platform-neutral social agent core first, then attach
QQ through replaceable adapters. Role cards, group lorebooks, sticker behavior,
social decision loops, capability calls, and operations controls are separate
subsystems with explicit module agreements.

**Tech Stack:** Python 3.13, pytest, Isotope capability runner, Isotope memory
store, optional NapCat/OneBot, optional Amadeus-style MCP, optional NoneBot.

---

## Planning Rule

This roadmap is the master path. It is not a substitute for phase-level
implementation plans.

Before coding a phase, write a dedicated plan under
`docs/superpowers/plans/YYYY-MM-DD-qq-group-chatbot-phase-N-<name>.md` with:

- exact files to create or modify;
- test-first steps;
- expected failing and passing commands;
- commit points;
- product review checklist for that phase.

No phase is complete until both mechanical tests and product-level acceptance
pass.

## Phase 0: Repair Shared Conversation Baseline

**Why:** The QQ bot will reuse Isotope's conversation/capability runtime. Known
desktop conversation tests were failing after provider and routing changes, so
the shared base must be repaired before QQ code depends on it.

**Files likely involved:**

- `src/isotope/features/supervisor/conversation_loop.py`
- `src/isotope/features/supervisor/desktop_chat.py`
- `src/isotope/features/supervisor/web/_impl.py`
- `tests/unit/features/supervisor/test_supervisor_conversation_loop.py`
- `tests/integration/supervisor/test_supervisor_desktop_chat.py`

**Mechanical acceptance:**

- [ ] Run:
  `.venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py tests/integration/supervisor/test_supervisor_desktop_chat.py -q`
- [ ] Expected: all selected tests pass.
- [ ] Run: `git diff --check`
- [ ] Expected: no whitespace errors.

**Product acceptance:**

- [ ] A model-selected capacity call receives the inputs required by the chosen
  capability, not a fake or empty provider path.
- [ ] Legacy desktop capacity-provider behavior either works or is explicitly
  removed with tests and docs updated. It must not silently skip configured
  providers.
- [ ] Capability failures report what failed and why in useful language.

## Phase 1: Platform-Neutral Social Message Model

**Goal:** Create message and reply objects that can represent real QQ group
messages without importing a QQ SDK into the agent core.

**Files to create:**

- `src/isotope/features/social/__init__.py`
- `src/isotope/features/social/messages.py`
- `src/isotope/features/social/replies.py`
- `src/isotope/features/social/send_feedback.py`
- `tests/unit/features/social/test_social_messages.py`
- `tests/unit/features/social/test_social_replies.py`

**Required behavior:**

- incoming messages support text, mention, reply, QQ face, image, sticker, file,
  voice, video, link, and raw fallback parts;
- outgoing reply actions support text, mention, reply, QQ face, sticker, image,
  file, and voice parts;
- send feedback records actual chunks, sent message ids, rendered preview, recent
  messages after send, and platform error when present;
- message objects validate required platform, chat, sender, timestamp, and parts
  fields.

**Mechanical acceptance:**

- [ ] Unit tests prove a message with empty text but a sticker part is valid.
- [ ] Unit tests prove a text-only message still stores a `parts` list.
- [ ] Unit tests prove malformed sender, empty message id, and unknown part kind
  fail with clear errors.
- [ ] Run:
  `.venv/bin/python -m pytest tests/unit/features/social/test_social_messages.py tests/unit/features/social/test_social_replies.py -q`
- [ ] Expected: all selected tests pass.

**Product acceptance:**

- [ ] The model can tell the difference between "no content" and "sticker-only
  content".
- [ ] The message shape leaves room for future Telegram/WeChat support without
  changing the core.

## Phase 2: Character Card Plus

**Goal:** Load role-card driven personalities inspired by tavern character
cards, extended for QQ behavior, stickers, tools, and group overrides.

**Files to create:**

- `src/isotope/features/social/character_card.py`
- `src/isotope/features/social/character_loader.py`
- `tests/unit/features/social/test_character_card.py`
- `tests/fixtures/social/character_cards/*.yaml`

**Required behavior:**

- role cards include identity, voice, social behavior, sticker preferences,
  tools, memory policy, and group overrides;
- fields are versioned with `schema_version`;
- invalid cards fail with field-specific errors;
- group overrides merge over base cards without mutating the base card.

**Mechanical acceptance:**

- [ ] Tests load a valid fixture card and assert all major sections are present.
- [ ] Tests reject cards without identity name, invalid sticker frequency, and
  unknown schema version.
- [ ] Tests prove a group override changes talkativeness and sticker policy for
  one group only.
- [ ] Run:
  `.venv/bin/python -m pytest tests/unit/features/social/test_character_card.py -q`
- [ ] Expected: all tests pass.

**Product acceptance:**

- [ ] Changing a card changes behavior inputs without code edits.
- [ ] A reviewer can read the card and understand how the role should speak and
  use stickers.

## Phase 3: Group Lorebook And Social Memory Inputs

**Goal:** Add group-specific rules, recurring context, relationships, and memory
entries that can be injected by triggers and inspected by operators.

**Files to create:**

- `src/isotope/features/social/lorebook.py`
- `src/isotope/features/social/context_builder.py`
- `tests/unit/features/social/test_lorebook.py`
- `tests/unit/features/social/test_social_context_builder.py`
- `tests/fixtures/social/lorebooks/*.yaml`

**Required behavior:**

- lorebook entries support keywords, regex, users, message part kinds, priority,
  insertion position, and expiration;
- context builder combines role card, group override, triggered lorebook entries,
  recent messages, and memory previews;
- injected entries include inspectable reasons.

**Mechanical acceptance:**

- [ ] Tests prove keyword, regex, user, and sticker-kind triggers work.
- [ ] Tests prove high-priority group rules override generic personality hints.
- [ ] Tests prove expired entries are skipped.
- [ ] Run:
  `.venv/bin/python -m pytest tests/unit/features/social/test_lorebook.py tests/unit/features/social/test_social_context_builder.py -q`
- [ ] Expected: all selected tests pass.

**Product acceptance:**

- [ ] Operators can answer "why did this rule enter the context?"
- [ ] A group can have its own norms without duplicating a whole character card.

## Phase 4: Sticker And Media System

**Goal:** Make stickers, QQ faces, and image memes first-class parts of
understanding and replying.

**Files to create:**

- `src/isotope/features/social/stickers.py`
- `src/isotope/features/social/media_refs.py`
- `tests/unit/features/social/test_stickers.py`
- `tests/fixtures/social/stickers/*.yaml`

**Required behavior:**

- sticker library entries include media ref, pack id, tags, text meaning, allowed
  groups, blocked groups, and source;
- role cards can prefer or avoid sticker tags;
- reply planner can select sticker-only, text-plus-sticker, or no-sticker output;
- group rules can forbid image/sticker sends.

**Mechanical acceptance:**

- [ ] Tests select a sticker from emotion and scene tags.
- [ ] Tests reject a sticker blocked in the target group.
- [ ] Tests prove role-card preferences affect sticker selection.
- [ ] Tests prove sticker-only replies are valid when allowed.
- [ ] Run:
  `.venv/bin/python -m pytest tests/unit/features/social/test_stickers.py -q`
- [ ] Expected: all tests pass.

**Product acceptance:**

- [ ] Sticker choice feels tied to the role, not random.
- [ ] Sticker spam is prevented by policy and send feedback.

## Phase 5: Social Decision Loop

**Goal:** Decide whether to speak, stay silent, use a sticker, call a capability,
or update memory based on group context and character state.

**Files to create or modify:**

- `src/isotope/features/social/decision.py`
- `src/isotope/features/social/candidates.py`
- `src/isotope/features/social/arbiter.py`
- `src/isotope/features/social/loop.py`
- `tests/unit/features/social/test_social_decision_loop.py`
- `tests/unit/features/social/test_social_arbiter.py`

**Required behavior:**

- candidate actions include silent, internal note, respond, interrupt, call
  capability, write memory, and request operator review;
- multiple agents can propose actions;
- arbiter prevents duplicate sends and state-lock conflicts;
- dry-run mode returns proposed actions without sending;
- send feedback is fed into the next decision.

**Mechanical acceptance:**

- [ ] Tests prove mention wake, keyword wake, autonomous wake, and no-wake cases.
- [ ] Tests prove two agents do not both send in one turn.
- [ ] Tests prove self-send feedback prevents immediate repeated sends.
- [ ] Run:
  `.venv/bin/python -m pytest tests/unit/features/social/test_social_decision_loop.py tests/unit/features/social/test_social_arbiter.py -q`
- [ ] Expected: all selected tests pass.

**Product acceptance:**

- [ ] The bot can explain why it spoke or stayed silent.
- [ ] The bot does not feel like a stateless assistant endpoint.

## Phase 6: Capability Bridge

**Goal:** Let social agents use Isotope capabilities while reporting useful
results and honest access failures.

**Files to create or modify:**

- `src/isotope/features/social/capability_bridge.py`
- `src/isotope/features/social/information_report.py`
- `tests/unit/features/social/test_social_capability_bridge.py`
- relevant existing capability tests as needed

**Required behavior:**

- group/role configuration controls allowed capabilities;
- capability call results include enough content for the agent to answer;
- blocked, missing, or failed access reports the target and reason;
- risky actions require explicit operator approval rather than silent omission.

**Mechanical acceptance:**

- [ ] Tests prove a permitted capability returns a useful result to the social
  loop.
- [ ] Tests prove a forbidden capability produces an operator-readable blocked
  report.
- [ ] Tests prove failed web/content access states which target failed.
- [ ] Run:
  `.venv/bin/python -m pytest tests/unit/features/social/test_social_capability_bridge.py -q`
- [ ] Expected: all tests pass.

**Product acceptance:**

- [ ] Tool use gives the group a better answer than guessing.
- [ ] If information is missing, the bot says what is missing in concrete terms.

## Phase 7: Fake Platform Adapter And Integration Harness

**Goal:** Test the complete social core without QQ.

**Files to create:**

- `src/isotope/features/social/fake_platform.py`
- `tests/integration/social/test_social_fake_platform_flow.py`

**Required behavior:**

- fake adapter emits incoming messages;
- fake adapter records outgoing actions and returns send feedback;
- complete loop can run with role card, lorebook, sticker library, and fake
  capability bridge.

**Mechanical acceptance:**

- [ ] Integration test processes a multi-part group message and sends a
  role-consistent reply.
- [ ] Integration test sends a sticker reply when role and group allow it.
- [ ] Integration test runs in dry-run mode and sends nothing.
- [ ] Run:
  `.venv/bin/python -m pytest tests/integration/social/test_social_fake_platform_flow.py -q`
- [ ] Expected: all tests pass.

**Product acceptance:**

- [ ] A reviewer can read the integration scenario and recognize the intended
  QQ group behavior.

## Phase 8: QQ Adapter

**Goal:** Attach the platform-neutral core to a real QQ stack.

**Files to create:**

- `src/isotope/integrations/qq/__init__.py`
- `src/isotope/integrations/qq/onebot_client.py`
- `src/isotope/integrations/qq/onebot_adapter.py`
- `src/isotope/integrations/qq/amadeus_mcp_adapter.py` if MCP is selected
- `tests/unit/integrations/qq/test_onebot_adapter.py`
- `tests/integration/qq/test_fake_onebot_flow.py`

**Required behavior:**

- ingest group/private events;
- normalize OneBot/NapCat segments into standard social messages;
- send text, mention, reply, QQ face, image sticker, and mixed messages;
- handle history backfill, reconnect state, duplicate events, and platform
  errors.

**Mechanical acceptance:**

- [ ] Unit tests map OneBot text, at, face, image, reply, and file segments.
- [ ] Integration test uses fake OneBot HTTP/WebSocket fixtures.
- [ ] Optional real smoke is documented and disabled by default unless env vars
  are set.
- [ ] Run:
  `.venv/bin/python -m pytest tests/unit/integrations/qq/test_onebot_adapter.py tests/integration/qq/test_fake_onebot_flow.py -q`
- [ ] Expected: all selected tests pass.

**Product acceptance:**

- [ ] QQ platform failure stays in the adapter and does not corrupt social core
  state.
- [ ] Real QQ smoke, when enabled, can send and receive a sticker-capable reply
  in a controlled test group.

## Phase 9: Operations And Operator Controls

**Goal:** Make the bot operable in real groups.

**Files to create or modify:**

- `src/isotope/features/social/config.py`
- `src/isotope/features/social/operations.py`
- `src/isotope/features/social/audit_log.py`
- CLI or desktop entry points chosen by the phase-specific plan
- `tests/unit/features/social/test_social_operations.py`

**Required behavior:**

- group whitelist/blacklist;
- user roles and operator permissions;
- pause/resume per group;
- dry-run review;
- decision log, send log, capability log, and health checks;
- role/lorebook/sticker inspection.

**Mechanical acceptance:**

- [ ] Tests pause one group without pausing another.
- [ ] Tests inspect current role card and group lorebook.
- [ ] Tests show decision and send logs for a completed turn.
- [ ] Run:
  `.venv/bin/python -m pytest tests/unit/features/social/test_social_operations.py -q`
- [ ] Expected: all tests pass.

**Product acceptance:**

- [ ] An operator can debug why the bot spoke, did not speak, or failed to send.
- [ ] Operations controls are understandable without reading source code.

## Phase 10: Real Group Beta Hardening

**Goal:** Validate the product in a controlled real QQ group.

**Files to create or modify:**

- `docs/current/qq-group-chatbot.md`
- `docs/current/qq-group-chatbot-operations.md`
- smoke scripts or commands selected by the phase-specific plan
- regression tests from observed failures

**Required behavior:**

- real-group setup guide;
- role-card tuning workflow;
- sticker pack setup guide;
- observed failure log;
- regression suite for real failures;
- multi-day run checklist.

**Mechanical acceptance:**

- [ ] Docs include exact setup, config, run, pause, inspect, and shutdown steps.
- [ ] Real smoke commands are documented and guarded by env vars.
- [ ] Regression tests exist for every real failure fixed during beta.

**Product acceptance:**

- [ ] The bot can run multiple days in a controlled group without duplicate
  replies, lost state, or uninspectable failures.
- [ ] The configured role stays recognizable.
- [ ] Group members can understand and control when the bot participates.

