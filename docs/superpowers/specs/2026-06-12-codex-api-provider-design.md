# Codex API Provider Design

## Summary

Add a first slice of a Codex OAuth-backed LLM provider for Isotope.
The provider should look like a normal Isotope chat provider to callers, while
delegating authentication and session execution to the local Codex runtime.

This is separate from the existing `provider = "codex"` CLI-backed path:

- `codex`: uses `codex exec --json` through `CodexCliLLMProvider`.
- `codex-api`: uses `codex app-server` JSON-RPC through a new provider.

## Goals

- Let Supervisor LLM pool entries select `provider = "codex-api"`.
- Reuse existing Isotope provider contracts: `LLMResponse`, `PoolEntry`, and
  `create_chat_provider_from_pool_entry(...)`.
- Reuse local Codex OAuth credentials without Isotope printing, storing, or
  transforming token values.
- Support `generate(messages, max_tokens=...)` for text-only chat turns.
- Keep the current CLI-backed Codex provider working unchanged.

## Non-Goals

- Do not implement `select_tool(...)` or `select_chat_turn(...)` in the first
  slice.
- Do not expose a local OpenAI-compatible HTTP server.
- Do not call undocumented Codex backend endpoints directly from Isotope.
- Do not persist or refresh OAuth tokens in Isotope.
- Do not add a required Python dependency on the beta `openai-codex` package.

## Architecture

The first implementation should use `codex app-server` as the stable local
programmatic boundary. The app-server already owns Codex authentication,
conversation execution, and token refresh. Isotope should communicate with it
over stdio JSON-RPC and project the final assistant text back into the existing
`LLMResponse` shape.

The provider surface:

```python
provider = CodexApiLLMProvider(
    executable="codex",
    codex_home=None,
    model="gpt-5-codex",
    timeout=60,
)
response = provider.generate([{"role": "user", "content": "hello"}])
```

The internal flow for one `generate()` call:

1. Validate Isotope messages with existing provider validators.
2. Start `codex app-server --stdio`.
3. Send `initialize`, then `initialized`.
4. Send `thread/start` with the configured model.
5. Send `turn/start` with the Isotope messages converted to text input.
6. Read JSON-RPC notifications until `turn/completed`.
7. Return the latest completed or delta-built agent message as `LLMResponse`.
8. Terminate the app-server process for this first slice.

Keeping one short-lived app-server process per call is intentionally simple.
Persistent app-server reuse can come later after the contract is stable.

## Provider Configuration

Pool TOML should accept:

```toml
[[agents.providers]]
provider = "codex-api"
model = "gpt-5-codex"
max_tokens = 2048
```

Optional fields:

```toml
executable = "codex"
codex_home = "/path/to/.codex"
profile = "chatgpt"
```

The pool parser should set:

- `provider = "codex-api"`
- `api_key = ""`
- `base_url = "codex://app-server"`
- `model = "codex-default"` when omitted
- `options` containing only supported Codex app-server fields

## Error Handling

- Missing `codex` executable should resolve as missing configuration, matching
  the existing CLI-backed Codex provider behavior.
- Invalid timeout, empty model strings, and invalid TOML field types should fail
  before starting the app-server.
- JSON-RPC error responses should raise `RuntimeError` with a clipped, redacted
  message.
- If no final agent message is observed before completion, raise
  `RuntimeError("codex api provider did not return an agent message")`.
- The provider must not include token values in exceptions, raw response fields,
  or test fixtures.

## File Layout

Avoid adding the new implementation to `src/isotope/llm/provider/codex.py`,
which is already near the preferred file-size limit. Add a focused module:

- `src/isotope/llm/provider/codex_api.py`: app-server provider, JSON-RPC client,
  event projection.

Existing files to touch narrowly:

- `src/isotope/llm/provider/__init__.py`: export `CodexApiLLMProvider`.
- `src/isotope/llm/provider/factory.py`: construct it from pool entries.
- `src/isotope/llm/provider/resolution.py`: support
  `ISOTOPE_LLM_PROVIDER=codex-api` for chat provider resolution. Tool-call
  resolution remains unsupported until this provider implements
  `select_tool(...)`.
- `src/isotope/llm/pool.py`: parse `provider = "codex-api"`.
- `src/isotope/features/supervisor/supervisor_llm_pool.toml.example`: document
  the new pool option.

## Testing

Use TDD with fake process runners. Tests should not start a real app-server or
read real OAuth tokens.

Required coverage:

- `CodexApiLLMProvider.generate()` sends initialize/thread/turn requests and
  returns final assistant text.
- JSON-RPC error responses become safe provider failures.
- Pool TOML accepts `provider = "codex-api"` without `api_keys`.
- Factory creates `CodexApiLLMProvider` for a `codex-api` pool entry.
- Chat env resolution supports `ISOTOPE_LLM_PROVIDER=codex-api`, while
  tool-call env resolution does not claim support in this first slice.
- Existing `codex` CLI provider tests still pass.

## Success Criteria

- Targeted LLM/Codex tests pass.
- The new provider is selectable through TOML and env resolution.
- No test or production output prints local OAuth token values.
- Existing `provider = "codex"` behavior is unchanged.
