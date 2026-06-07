# Social LLM Participation Design

## Goal

Add an opt-in QQ social runtime mode where the LLM decides whether to participate in a group message and, when it participates, generates the reply text in the same model decision path.

The current runtime uses rule-based wake gates first. Messages without a direct mention, keyword, or autonomy trigger become `silent` before the LLM is called. That is safe for startup, but it is not the desired long-running group behavior. In long-running mode, the LLM should consider the current topic, role card, recent context, memory previews, lorebook entries, and the bot personality before deciding whether to stay silent or speak.

## Non-Goals

- Do not let the LLM bypass group allowlists, pause state, dry-run mode, or send-run flags.
- Do not add a new long-running daemon in this slice.
- Do not enable real sends by default.
- Do not remove deterministic replay behavior.
- Do not add memory writes or tool calls as part of this slice.

## Approaches Considered

### A. Keep Rule-Based Participation

The current behavior remains unchanged. It is safest, but ordinary group messages never reach the LLM unless a keyword, mention, or autonomy score triggers.

### B. LLM Participation Gate, Existing Reply Provider

Add an LLM decision before reply generation. The model returns `respond` or `silent`; if `respond`, the existing reply provider generates the message. This is more modular, but it spends two model calls for a normal response and can split intent from wording.

### C. LLM Participation And Reply Candidate

Use one LLM call to return either a silent decision or a reply candidate. This is the recommended approach because it matches the desired behavior, keeps latency and token use lower, and lets the model align the decision reason with the response text.

## Selected Design

Add a new runtime option:

```json
{
  "runtime": {
    "participation_provider": "llm",
    "reply_provider": "llm"
  }
}
```

`participation_provider` defaults to `"rules"` so existing tests, replays, and beta packs keep their current conservative behavior. `"llm"` requires the shared Isotope chat provider to resolve successfully.

When `participation_provider` is `"rules"`, `SocialDecisionLoop` behaves as it does now.

When it is `"llm"`, `SocialDecisionLoop` still applies hard system gates first, then asks a new LLM participation provider for a structured decision.

## Hard System Gates

The system keeps these outside the model:

- Group allow/block policy and paused groups.
- `dry_run` versus real send behavior.
- Recent-send suppression and anti-spam cooldown.
- Duplicate event handling in the adapter/client.
- Configured target group, bot user id, access token, and WebSocket URL.
- Candidate arbitration and send execution.
- Model failure handling: timeout, provider error, invalid JSON, or empty text defaults to a silent candidate.

## LLM Decision Contract

The LLM participation provider receives:

- `persona_instructions`
- `chat_context`
- `wake_signals`
- current `dry_run` flag
- required JSON shape

It returns JSON:

```json
{
  "action": "respond",
  "reason": "short reason",
  "confidence": 0.72,
  "text": "reply text"
}
```

or:

```json
{
  "action": "silent",
  "reason": "short reason",
  "confidence": 0.65
}
```

Rules:

- `action` must be `"respond"` or `"silent"`.
- `reason` must be non-empty.
- `confidence` must be a number from 0 to 1.
- `text` is required only for `respond`.
- Invalid output becomes a silent candidate with provider error metadata.

## Runtime Flow

1. `SocialRuntime.process_next()` receives and normalizes a QQ message.
2. Group policy decides whether the runtime may process the message.
3. Recent-send suppression can still force `silent`.
4. If `participation_provider == "rules"`, existing wake logic runs.
5. If `participation_provider == "llm"`, the LLM returns `silent` or `respond`.
6. Dry-run records proposed candidates and never sends.
7. Send-run uses the existing arbiter and OneBot send path.

## Observability

Each LLM participation candidate should include metadata:

- provider
- model
- usage if available
- action
- LLM reason
- wake signals observed by the system
- parse or provider error when degraded to silent

This lets long dry-run reports distinguish "the model chose silence" from "the provider failed."

## Testing

Add unit tests for:

- default `participation_provider` keeps rule-based behavior.
- LLM participation can choose `silent` for an ordinary message.
- LLM participation can choose `respond` for an ordinary message without mention.
- dry-run records the LLM reply candidate but selects nothing for sending.
- invalid LLM output degrades to a silent candidate.
- missing provider blocks startup/config resolution when `participation_provider == "llm"`.

Add an integration-style QQ runner test with a fake LLM provider to prove config wiring.

Manual validation:

1. Run QQ LLM dry-run with `participation_provider = "llm"` and `max-events 5`.
2. Send ordinary and mentioned group messages.
3. Confirm ordinary messages may produce either LLM silence or LLM reply candidates.
4. Confirm dry-run never sends.
5. Only then run one send-enabled message in the controlled group.
