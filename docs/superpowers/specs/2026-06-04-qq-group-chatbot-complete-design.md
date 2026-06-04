# QQ Group Chatbot Complete Design

## Goal

Build a full QQ group chatbot product on top of Isotope's agent and capacity
runtime. The bot must live in real QQ groups, understand group context, use
role-card driven personalities, decide when to speak or stay silent, use text
and stickers naturally, call Isotope capabilities when useful, remember social
state, recover from platform failures, and expose clear product-level acceptance
criteria.

This is not a minimal `@bot -> answer once` feature. The implementation may be
phased for engineering risk, but every phase must move toward the complete
product described here.

## Reference Systems

### SillyTavern

Use SillyTavern as the primary reference for character and group experience
design.

Useful practices:

- Character cards hold identity, speaking style, scenario, first messages,
  example dialogue, and extension fields.
- World Info / lorebooks inject knowledge and behavioral rules by keyword,
  regular expression, priority, depth, and insertion position.
- Personas make the human participant a first-class actor rather than treating
  the user as an anonymous prompt sender.
- Group chat supports multiple characters in one room.
- Extensions can add commands, settings, tools, and character-card fields.

Product lesson: the bot's personality must not be a hard-coded prompt. It should
be configurable through role cards, group rules, lorebooks, social memories, and
runtime state.

References:

- SillyTavern docs: <https://docs.sillytavern.app/>
- World Info / lorebook: <https://docs.sillytavern.app/usage/core-concepts/worldinfo/>
- Writing extensions: <https://docs.sillytavern.app/for-contributors/writing-extensions/>

### Hermes / OpenClaw

Use Hermes/OpenClaw as the primary reference for long-running agent operations.

Useful practices:

- Multiple message gateways such as CLI, Telegram, Discord, Slack, WhatsApp,
  Signal, and email.
- Personality configuration and imported persistent identity state.
- Memories, skills, tools, MCP servers, scheduled tasks, and sub-agents.
- Long-running operation with recovery across sessions.
- Execution backends such as local shell, Docker, SSH, and hosted sandboxes.

Product lesson: QQ is one gateway. The core bot runtime should not be tied to
QQ, NapCat, OneBot, or a single process. It should be able to run continuously,
restart cleanly, and keep its character, memory, skills, permissions, and group
state intact.

Reference:

- Hermes Agent: <https://github.com/NousResearch/hermes-agent>

### Amadeus-QQ-MCP

Use Amadeus-QQ-MCP as the closest implementation reference for the QQ adapter.

Useful practices:

- Wraps NapCatQQ / OneBot v11 behind an MCP server.
- Provides tools such as recent context, sending messages, context compression,
  and group/friend filtering.
- Keeps a per-target sliding message buffer.
- Uses WebSocket listening plus HTTP API calls.
- Includes duplicate detection, rate limiting, message splitting, and support
  for `at` and face segments.

Product lesson: the QQ adapter should be replaceable. Amadeus is a good
prototype/reference for a QQ MCP bridge, but Isotope should keep its own
platform-neutral message and action shapes.

Reference:

- Amadeus-QQ-MCP: <https://github.com/JulesLiu390/Amadeus-QQ-MCP>

### PetGPT

Use PetGPT as a reference for autonomous social behavior.

Useful practices:

- Per-target social loops for group/friend conversations.
- Fetcher, intent, reply, observer, and memory layers.
- Explicit send-message feedback: after the bot sends a message, the model sees
  what was actually sent and the recent group messages including its own output.
- Persistent group rules, global social memory, contacts, and per-session intent
  state.

Product lesson: the bot must see its own sent messages and platform feedback.
Without that, it may repeatedly call send and spam the group.

References:

- PetGPT: <https://github.com/JulesLiu390/PetGPT>
- PetGPT send-message feedback note:
  <https://github.com/JulesLiu390/PetGPT/blob/main/SEND_MESSAGE_FEEDBACK.md>

### AstrBot

Use AstrBot as a mature platform comparison, not as source code to copy.

Useful practices:

- Supports multiple platforms including QQ Official, OneBot v11, Telegram, and
  Slack.
- Has LLM providers, MCP, plugins, knowledge base, WebUI, rate-limit checks,
  whitelist checks, wake checks, content safety stages, and response decoration.
- Shows that a complete chatbot product needs platform management and operations,
  not only prompts.

Constraint: AstrBot is AGPL-3.0-or-later. Do not copy implementation code into
Isotope without an explicit license decision.

Reference:

- AstrBot: <https://github.com/AstrBotDevs/AstrBot>

### QQ Platform Stack

Preferred first QQ stack:

- NapCatQQ or another OneBot v11 provider for personal QQ group access.
- An Amadeus-style MCP bridge or a thin Isotope adapter for event ingestion and
  sending.
- NoneBot adapters remain useful references or alternatives:
  - OneBot adapter: <https://github.com/nonebot/adapter-onebot>
  - QQ official adapter: <https://github.com/nonebot/adapter-qq>

The core design must not require one specific QQ stack. QQ Official, OneBot,
NapCat, Amadeus-style MCP, and future platforms should all map into the same
Isotope message format.

## Vocabulary In Plain Language

### Module Agreement

When this document says a module agreement, it means:

- what fields one module sends to another;
- what fields are required;
- what values are allowed;
- what the receiver promises to do;
- what errors look like.

Example: the QQ adapter must not send only `{text: "hello"}` to the agent core,
because QQ messages can contain mentions, replies, images, stickers, files,
voice, and raw platform segments. The adapter must send a structured message
that leaves room for those parts from day one.

### Information Handling Rule

Do not use vague safety language to justify missing functionality.

Whenever information is hidden, trimmed, summarized, or blocked, the design and
implementation must state:

- the original information category;
- exactly what was kept;
- exactly what was removed;
- why it was removed;
- whether the removal affects bot judgment;
- how an authorized path can inspect or recover the missing information.

Bad design:

```text
Return a restricted summary.
```

Acceptable design:

```text
The agent receives the command, exit code, working directory, and full stdout up
to 12000 characters. If output is longer, the stored artifact keeps the full
output and the agent receives an artifact reference plus the first and last 3000
characters. Strings matching configured secret patterns are replaced with
`[redacted: secret-pattern:<name>]`; the run log records which pattern matched.
```

For web search, the bot must not claim it read a page unless it actually fetched
page content or a declared provider excerpt. Search result titles alone are not
enough.

## Product Philosophy

The QQ bot should feel like a capable group member with configurable identity,
not a stateless Q&A endpoint.

It should:

- understand when the group wants it to answer and when silence is better;
- remember group rules, recurring jokes, relationships, and prior decisions;
- speak in a stable character voice controlled by role cards;
- use stickers and emoji like part of its personality, not random decoration;
- know what tools it can use and explain when tool access is missing;
- avoid spamming by seeing its own sent messages and respecting group cadence;
- recover from disconnects and continue with the same state;
- provide operator controls for configuration, pause, dry-run, logs, and
  inspection.

Product failure examples:

- It only replies when mentioned and never behaves autonomously.
- It sends generic assistant prose regardless of character card.
- It cannot understand or send stickers.
- It forgets group rules after restart.
- It claims a tool result without actually reading the source data.
- It hides useful information behind vague safety wording.
- It spams because it cannot see its own sent messages.
- It cannot explain why it spoke or why it stayed silent.

## Architecture

```text
QQ Platform
  -> Platform Adapter
  -> Standard Group Message
  -> Group Context Engine
  -> Character Card + Group Lorebook + Social Memory
  -> Social Decision Loop
  -> Agent Group Chat Core
  -> Capability Bridge
  -> Reply Planner
  -> Platform Send Action
  -> Send Feedback + Memory Update
```

### Platform Adapter

Responsibilities:

- receive QQ group/private events from NapCat/OneBot, QQ Official, or an MCP
  bridge;
- normalize incoming platform events into Isotope's standard message shape;
- send text, mentions, replies, QQ faces, image stickers, files, and future
  message parts back to the platform;
- handle login state, reconnect, duplicate events, send failures, and platform
  rate limits;
- store enough platform identifiers to quote, reply, fetch history, and audit
  what was sent.

The adapter may use Amadeus-style MCP, NoneBot, or direct OneBot clients. The
agent core must not depend on any of those directly.

### Standard Group Message

The standard message shape must support at least:

```yaml
message_id: platform message id
platform: qq
adapter: napcat_onebot | qq_official | amadeus_mcp | nonebot | other
chat_type: group | private
group_id: group id when chat_type is group
sender:
  user_id:
  display_name:
  roles:
  is_bot:
timestamp:
text:
mentions:
  - user_id:
    display_name:
reply_to:
  message_id:
  sender_id:
  text_preview:
parts:
  - kind: text | mention | qq_face | image | sticker | file | voice | video | link | raw
    text:
    media_ref:
    platform_data:
raw_event_ref:
```

The `parts` list is required even when the message is plain text. That prevents
future image/sticker/file support from being bolted on as an afterthought.

### Reply Action

The standard outgoing action must support:

```yaml
action_id:
target:
  platform:
  chat_type:
  group_id:
  user_id:
reply_to_message_id:
parts:
  - kind: text | mention | qq_face | sticker | image | file | voice
    text:
    media_ref:
    platform_data:
send_policy:
  urgency: normal | interrupt | delayed
  allow_split:
  max_chunks:
  min_delay_ms:
  reason:
```

The platform adapter must return send feedback:

```yaml
status: sent | partial | failed
sent_message_ids:
chunks:
  - message_id:
    parts:
    rendered_preview:
platform_error:
recent_messages_after_send:
```

The agent uses this feedback to avoid repeated sends and to understand how its
message appeared in the group.

## Character Card Plus

The bot uses role cards similar to tavern character cards, extended for QQ group
behavior and tools.

```yaml
schema_version: isotope.character_card_plus.v1
identity:
  name:
  aliases:
  avatar_ref:
  description:
  creator_notes:
voice:
  speaking_style:
  tone:
  vocabulary:
  example_messages:
  forbidden_style:
social_behavior:
  talkativeness:
  interruption_style:
  mention_policy:
  lurk_policy:
  disagreement_style:
  relationship_policy:
stickers:
  enabled:
  favorite_packs:
  style_tags:
  emotion_map:
  use_frequency:
  allow_sticker_only_reply:
  avoid_tags:
tools:
  allowed_capabilities:
  tool_use_style:
  after_tool_result_behavior:
memory:
  remember:
  do_not_remember:
  review_policy:
groups:
  overrides:
```

Acceptance criteria:

- Changing the card changes behavior without code edits.
- A role can be exported, versioned, reviewed, and loaded again after restart.
- The card can control sticker style and frequency.
- Group-specific overrides can change behavior without duplicating the whole
  card.

## Group Lorebook

Group lorebooks hold group-specific social knowledge:

- group rules;
- allowed topics and forbidden topics;
- recurring jokes and shared references;
- user nicknames and relationships;
- formal/informal tone expectations;
- sticker norms;
- escalation rules;
- tools allowed in this group.

Entries need trigger rules:

```yaml
entry_id:
title:
content:
triggers:
  keywords:
  regex:
  users:
  message_part_kinds:
priority:
position: before_character | after_recent_context | before_reply
expires_at:
```

Acceptance criteria:

- A group rule triggered by a keyword appears in the agent context for that turn.
- A higher-priority rule wins over a generic character habit.
- Operators can inspect why a lorebook entry was injected.
- The bot can run with no lorebook and still behave from its base card.

## Stickers And Emoji

Stickers are a first-class feature.

Inbound support:

- QQ face segments;
- image stickers;
- images used as memes;
- sticker-only messages;
- text plus sticker messages;
- reply-to-sticker context.

Outbound support:

- text only;
- QQ face only;
- image sticker only;
- text plus sticker;
- mention plus text plus sticker;
- delayed sticker reaction after a message.

Sticker library:

```yaml
sticker_id:
pack_id:
media_ref:
tags:
  emotion:
  scene:
  character_style:
  intensity:
text_meaning:
safe_groups:
blocked_groups:
source:
```

Acceptance criteria:

- The bot can identify that a message contains a sticker even if text is empty.
- A role card can prefer or avoid sticker categories.
- The reply planner can choose not to use a sticker when the group rules forbid
  image replies.
- Send feedback records exactly which sticker was sent.
- Sticker use is tested for anti-spam behavior.

## Social Decision Loop

Each group has an independent social loop:

1. Fetch new events.
2. Update group context.
3. Detect whether the bot should wake.
4. Build decision context from role card, group lorebook, recent messages,
   social memory, platform state, and available capabilities.
5. Let agents propose candidate actions:
   - stay silent;
   - internal note;
   - respond;
   - interrupt;
   - call capability;
   - update memory;
   - request operator review.
6. Arbitrate candidates.
7. Plan the outgoing message parts.
8. Send.
9. Feed send result and recent messages back into context.
10. Persist memory or diagnostics.

The current Isotope `AgentConversationMessage` and
`arbitrate_agent_conversation_turn(...)` are a useful starting point, but the
complete feature needs richer candidate actions and platform send feedback.

Acceptance criteria:

- The bot can explain why it spoke, why it stayed silent, or why it delayed.
- The bot sees its own sent messages before deciding whether to send again.
- Multiple agents can compete without double-sending.
- A state lock prevents two agents from editing the same group memory at once.
- The loop survives restart without losing group identity and persistent memory.

## Agent Group Chat Core

The core is platform-independent. It knows about standard messages and reply
actions, not QQ-specific API calls.

Core responsibilities:

- manage candidate agent messages;
- arbitrate who speaks;
- track internal notes and deferred candidates;
- apply group policy and role-card constraints;
- pass capability requests to the capability bridge;
- produce reply actions with reasons and send policies.

Acceptance criteria:

- Unit tests can run the core with no QQ process.
- The same core can be fed synthetic QQ, Telegram, or test messages.
- No platform-specific SDK object crosses into the core.
- The core can run in dry-run mode and produce proposed actions without sending.

## Capability Bridge

Capabilities are Isotope actions the social agents can call. Examples:

- web research;
- repository status;
- issue or task lookup;
- memory read/write;
- artifact inspection;
- scheduled reminders;
- controlled coding or command execution when explicitly allowed.

Capability calls must be useful, not decorative. If a capability needs page
content, terminal output, or file content, the bridge must provide the needed
content or clearly report that it could not access it and why.

Information handling must use the rule in this document: say exactly what is
kept, removed, blocked, or recoverable.

Acceptance criteria:

- A capability result includes enough information for the agent to answer the
  group question.
- If access fails, the bot reports the failing capability, target, and reason.
- Operators can configure which capabilities are available per group and role.
- Dangerous actions require explicit operator approval rather than being silently
  omitted.

## Operations And Safety

This section is about real product controls, not using safety wording to hide
missing features.

Required controls:

- group whitelist and blacklist;
- user roles and operator permissions;
- bot pause/resume per group;
- dry-run mode;
- rate limits per group and per sender;
- duplicate send detection;
- message chunking with delay;
- reconnect and backfill after disconnect;
- audit log of received events, decisions, sends, failures, and operator actions;
- configuration validation;
- health check for QQ adapter, agent loop, memory store, and capability bridge.

Acceptance criteria:

- The bot can be paused in one group without stopping another group.
- Reconnect backfills enough history to avoid replying to stale context.
- If sending fails, the failure is visible in logs and state, not swallowed.
- Operator commands can inspect current role card, group rules, recent decisions,
  and pending failures.

## Product-Level Acceptance

Mechanical acceptance is necessary but not sufficient. Each completed slice must
pass both engineering checks and product judgment.

### Engineering Checks

- Unit tests for message normalization, role-card loading, lorebook triggers,
  sticker selection, decision loop, arbitration, send planning, and capability
  bridge.
- Integration tests with a fake QQ adapter.
- Optional smoke tests with NapCat/OneBot in a real or local controlled group.
- Restart tests proving persistent state is reloaded.
- Failure tests for duplicate messages, send failure, disconnected adapter,
  malformed platform events, and capability failures.

### Product Judgment

A feature is not accepted if it only proves a function exists. It must behave
like a usable group bot.

Product review questions:

- Does the bot feel like the configured role card?
- Does it know when not to speak?
- Does it avoid spam after sending one message?
- Does it use stickers in-character and at the right frequency?
- Does it remember group-specific rules after restart?
- Does it give useful answers when using tools?
- Can an operator understand why it acted?
- Can the same agent core work without QQ-specific code?
- Are missing permissions and unavailable data reported honestly?

## Development Path

The full feature should be delivered as complete subsystem slices. Each slice
must have tests, docs, and product review criteria. A slice may be implemented
before later slices, but it must not pretend the whole product is finished.

### Phase 1: Platform-Neutral Social Model

Deliver:

- standard incoming group/private message objects;
- standard outgoing reply actions;
- message parts for text, mention, reply, QQ face, sticker, image, file, voice,
  video, link, and raw fallback;
- fake platform adapter for tests;
- send feedback object.

Acceptance:

- Complex synthetic QQ messages normalize without dropping stickers or images.
- The agent core can consume normalized messages without QQ SDK imports.
- Send feedback includes actual rendered chunks and recent messages after send.

### Phase 2: Character Card Plus And Group Lorebook

Deliver:

- role-card loader and validator;
- group override rules;
- group lorebook triggers;
- sticker preference fields;
- operator inspection command or CLI/API.

Acceptance:

- Changing a role card changes style and sticker behavior.
- Group-specific rules override base personality.
- Lorebook injection is inspectable.

### Phase 3: Social Decision Loop

Deliver:

- per-group loop state;
- wake rules for mention, keyword, active conversation, and autonomous mode;
- candidate actions;
- arbitration;
- dry-run mode;
- self-send feedback loop.

Acceptance:

- The bot can autonomously speak or stay silent based on group context.
- Multiple agents do not double-send.
- After sending, the next decision sees the sent message.

### Phase 4: Sticker And Media System

Deliver:

- sticker library;
- inbound sticker/media classification;
- outbound sticker/media reply planning;
- group and role restrictions;
- anti-spam checks for sticker-only and multi-part replies.

Acceptance:

- Sticker-only inbound messages affect decisions.
- Role cards control sticker style.
- Send feedback records exact sticker IDs/media refs.

### Phase 5: Capability Bridge

Deliver:

- capability availability per group/role;
- tool decision and result loop;
- explicit information handling reports;
- operator approval for dangerous actions;
- useful failure reporting.

Acceptance:

- A group question can trigger a capability and get a useful answer.
- Missing access is reported with target and reason.
- Content needed to answer is actually read or clearly unavailable.

### Phase 6: QQ Adapter

Deliver:

- NapCat/OneBot or Amadeus-style MCP adapter;
- login/reconnect state;
- group/private event ingestion;
- history backfill;
- message send for text, mention, reply, QQ face, and image sticker;
- platform error mapping.

Acceptance:

- Controlled QQ group smoke can receive a mention, process context, and send a
  role-consistent response.
- Adapter reconnects and backfills after a restart.
- Adapter failure does not crash the agent core.

### Phase 7: Operations Console And Observability

Deliver:

- group configuration management;
- pause/resume;
- dry-run review;
- decision log;
- send log;
- capability log;
- health checks;
- role/lorebook/sticker inspection.

Acceptance:

- An operator can debug why the bot spoke or did not speak.
- An operator can pause one group and keep another running.
- Logs show received event, selected context, candidate actions, final action,
  send feedback, and any failures.

### Phase 8: Real Group Beta Hardening

Deliver:

- real-group usage checklist;
- spam and cadence tuning;
- memory review tools;
- role-card tuning workflow;
- adapter fallback plan;
- regression suite from observed real failures.

Acceptance:

- The bot can run for multiple days in a controlled group without duplicate
  replies, lost state, or uninspectable failures.
- Product review confirms it feels in-character, helpful, and socially aware.

## Initial File Direction

Likely new packages:

- `src/isotope/features/social/` for platform-neutral social messages, role
  cards, lorebooks, stickers, decision loop, and reply planning.
- `src/isotope/integrations/qq/` for QQ adapter implementations.
- `tests/unit/features/social/` for core unit tests.
- `tests/integration/qq/` for fake adapter and optional real adapter smoke.
- `docs/current/qq-group-chatbot.md` for user-facing operation docs after the
  first implementation slice exists.

The exact implementation plan for each phase must be written before coding that
phase. Plans should use test-first steps and frequent commits.

## Open Product Choices

These need explicit decisions before implementation:

- Which QQ stack is first: NapCat/OneBot direct, Amadeus-style MCP, or NoneBot.
- Where role cards and group lorebooks are stored.
- Whether role-card editing starts as files, CLI, or desktop UI.
- Whether initial real-group testing uses a private test group.
- Which capabilities are allowed in group chat on day one.
- What sticker storage format and media path policy to use.
