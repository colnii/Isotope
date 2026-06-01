# AI Chat Capacity Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the desktop monitoring UI with an AI chat surface that can show inline Supervisor capacity calls with collapsed, expanded, and fullscreen detail views.

**Architecture:** Keep `/desktop/chat` as the single chat stream and add low-sensitive capacity events to that SSE stream. The frontend parses those events into `DesktopChatMessage.capacityCalls` and renders them inside the assistant message. Main, mini, and orb surfaces stop showing Codex monitoring data on the user path.

**Tech Stack:** Python 3.13, pytest, Svelte 5, TypeScript, Vitest, SvelteKit, Tailwind CSS.

---

### Task 1: Backend Capacity SSE Events

**Files:**
- Modify: `src/isotope/features/supervisor/desktop_chat.py`
- Modify: `src/isotope/features/supervisor/web.py`
- Test: `tests/integration/supervisor/test_supervisor_desktop_chat.py`

- [ ] **Step 1: Write the failing backend stream test**

Add a test that injects a fake capacity-calling provider and expects `/desktop/chat`
to emit `capacity_start` and `capacity_result` before the final `done`.

```python
def test_desktop_chat_endpoint_streams_capacity_events_before_answer(tmp_path) -> None:
    provider = RecordingDesktopChatProvider(content="我查到了上下文。")
    capacity_provider = RecordingCapacityProvider(
        '{"capacity_id":"memory.query","arguments":{"query":"capacity arguments","max_results":2},'
        '"confidence":0.9,"rationale":"需要查 memory"}'
    )
    server = create_dashboard_server(
        codex_home=tmp_path,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
        desktop_chat_provider=provider,
        desktop_chat_capacity_provider=capacity_provider,
    )
    body = _post_desktop_chat(server, {"question": "查一下 capacity arguments"})
    events = _parse_sse(body)
    names = [event["event"] for event in events]
    assert "capacity_start" in names
    assert "capacity_result" in names
    result = next(event["data"] for event in events if event["event"] == "capacity_result")
    assert result["capacity_id"] == "memory.query"
    assert result["status"] in {"ok", "blocked"}
    assert "details" in result
    assert "raw" not in body
    assert "messages" not in body
```

- [ ] **Step 2: Run the backend test to verify RED**

Run:

```bash
/home/lumber/Github/isotope/.venv/bin/python -m pytest tests/integration/supervisor/test_supervisor_desktop_chat.py::test_desktop_chat_endpoint_streams_capacity_events_before_answer -q
```

Expected: FAIL because `desktop_chat_capacity_provider` and capacity SSE events do not exist yet.

- [ ] **Step 3: Implement minimal backend event model**

Add a `DesktopChatStreamEvent` dataclass and a `stream_desktop_chat_events(...)`
function. Keep the existing `stream_desktop_chat(...)` text-only helper as a compatibility wrapper.

```python
@dataclass(frozen=True)
class DesktopChatStreamEvent:
    event: str
    payload: dict[str, Any]
    provider: str = "unknown"
    model: str = "unknown"
```

`stream_desktop_chat_events(...)` should require a valid question, build
supervisor chat context, optionally plan and execute one capacity call when a
capacity provider is available, yield `capacity_start` and `capacity_result`
projection events, then stream normal `delta` events from the desktop chat provider.

- [ ] **Step 4: Wire web.py to write new SSE events**

Add `desktop_chat_capacity_provider` to the dashboard server constructor. In
`_send_desktop_chat`, iterate `stream_desktop_chat_events(...)` and call
`_write_sse(event.event, event.payload)`.

- [ ] **Step 5: Run backend test to verify GREEN**

Run:

```bash
/home/lumber/Github/isotope/.venv/bin/python -m pytest tests/integration/supervisor/test_supervisor_desktop_chat.py -q
```

Expected: all desktop chat tests pass.

### Task 2: Frontend Stream Parsing And Chat State

**Files:**
- Modify: `apps/desktop/src/lib/client/agentClient.ts`
- Modify: `apps/desktop/src/lib/client/agentClient.test.ts`
- Modify: `apps/desktop/src/lib/stores/appState.ts`
- Modify: `apps/desktop/src/lib/stores/appState.test.ts`

- [ ] **Step 1: Write failing agentClient test**

Extend the stream fixture with capacity events and expect handlers plus final answer capacity calls.

```ts
const capacityEvents: string[] = [];
const answer = await createAgentClient('http://127.0.0.1:8765').askDesktopQuestion('capacity?', {
  onCapacityStart: (call) => capacityEvents.push(`start:${call.capacityId}`),
  onCapacityResult: (call) => capacityEvents.push(`result:${call.status}`)
});
expect(capacityEvents).toEqual(['start:memory.query', 'result:ok']);
expect(answer.capacityCalls?.[0].capacityId).toBe('memory.query');
```

- [ ] **Step 2: Run agentClient test to verify RED**

Run:

```bash
npm --prefix apps/desktop run test -- src/lib/client/agentClient.test.ts
```

Expected: FAIL because capacity handlers and types do not exist.

- [ ] **Step 3: Implement TypeScript capacity types and parser**

Add `DesktopCapacityCall`, `DesktopCapacityDetailSection`, and handler callbacks.
Parse `capacity_start`, `capacity_update`, and `capacity_result`, normalizing
snake_case payload fields to camelCase.

- [ ] **Step 4: Write failing appState test**

Update the store test so a streamed capacity call lands on `chat_assistant_1.capacityCalls`.

```ts
expect(get(state.chatMessages)[1].capacityCalls?.[0]).toMatchObject({
  capacityId: 'memory.query',
  status: 'ok'
});
```

- [ ] **Step 5: Implement appState capacity merge**

When `onCapacityStart`, `onCapacityUpdate`, or `onCapacityResult` fires, update
the active assistant message. Merge by capacity call id so later events replace
earlier partial data.

- [ ] **Step 6: Run frontend state tests to verify GREEN**

Run:

```bash
npm --prefix apps/desktop run test -- src/lib/client/agentClient.test.ts src/lib/stores/appState.test.ts
```

Expected: both test files pass.

### Task 3: Capacity Detail UI Components

**Files:**
- Create: `apps/desktop/src/lib/view/capacityCallView.ts`
- Create: `apps/desktop/src/lib/view/capacityCallView.test.ts`
- Create: `apps/desktop/src/lib/components/main/CapacityCallCard.svelte`
- Modify: `apps/desktop/src/lib/components/main/ConversationWorkspace.svelte`

- [ ] **Step 1: Write failing view tests**

Test that status labels, summary text, and detail formatting are stable.

```ts
expect(capacityCallStatusLabel({ ...call, status: 'running' })).toBe('Running');
expect(capacityCallSummary(call)).toContain('memory.query');
expect(formatCapacityDetailContent({ label: 'Inputs', kind: 'json', content: { query: 'x' } })).toContain('"query"');
```

- [ ] **Step 2: Run view tests to verify RED**

Run:

```bash
npm --prefix apps/desktop run test -- src/lib/view/capacityCallView.test.ts
```

Expected: FAIL because the view helper file does not exist.

- [ ] **Step 3: Implement view helpers**

Create helpers for status labels, one-line summaries, and safe formatting of
JSON/text detail sections.

- [ ] **Step 4: Implement CapacityCallCard**

Render collapsed card by default, an expand/collapse button, a scrollable detail
body with `max-h-*` and `overflow-auto`, a fullscreen button, and a fullscreen
overlay with visible close button and Escape close.

- [ ] **Step 5: Render cards inside assistant messages**

In `ConversationWorkspace.svelte`, after assistant text, render:

```svelte
{#if message.role === 'assistant' && message.capacityCalls?.length}
  <div class="mt-3 space-y-2">
    {#each message.capacityCalls as call (call.id)}
      <CapacityCallCard {call} />
    {/each}
  </div>
{/if}
```

- [ ] **Step 6: Run frontend tests**

Run:

```bash
npm --prefix apps/desktop run test -- src/lib/view/capacityCallView.test.ts
```

Expected: PASS.

### Task 4: Remove Monitor UI From Main And Mini User Surfaces

**Files:**
- Modify: `apps/desktop/src/lib/components/main/MainWindowShell.svelte`
- Modify: `apps/desktop/src/lib/components/mini/MiniWindow.svelte`
- Modify: `apps/desktop/src/lib/components/orb/FloatingOrb.svelte`
- Modify: `apps/desktop/src/routes/+page.svelte`
- Modify: `apps/desktop/src/lib/view/mainWindowProductView.ts`
- Modify: `apps/desktop/src/lib/view/mainWindowProductView.test.ts`
- Modify: `apps/desktop/src/lib/view/miniWindowView.ts`
- Modify: `apps/desktop/src/lib/view/miniWindowView.test.ts`

- [ ] **Step 1: Write failing tests for main and mini product text**

Assert the main and mini view helpers no longer expose monitor labels such as
`Activities`, `Inspector`, `Running`, `Approvals`, or replay event copy on the
default chat path.

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
npm --prefix apps/desktop run test -- src/lib/view/mainWindowProductView.test.ts src/lib/view/miniWindowView.test.ts
```

Expected: FAIL because current views still describe monitoring UI.

- [ ] **Step 3: Simplify MainWindowShell**

Remove `ActivityRail` and `InspectorDock` from the visible layout. Render
`ConversationWorkspace` as the whole main surface.

- [ ] **Step 4: Simplify MiniWindow**

Remove source badge, counts, mock command preview, quick action area, and monitor
copy. Pass through real `chatMessages`, `chatError`, `isAskingDesktop`, and
`onAskDesktop`.

- [ ] **Step 5: Simplify route rendering**

For main and dev surfaces, render the chat-first main shell. For mini, render the
chat mini. Stop passing `replayMockEvents` to user-facing surfaces.

- [ ] **Step 6: Run tests to verify GREEN**

Run:

```bash
npm --prefix apps/desktop run test
```

Expected: all frontend tests pass.

### Task 5: Verification And Browser Smoke

**Files:**
- Verify: `src/isotope/features/supervisor/desktop_chat.py`
- Verify: `src/isotope/features/supervisor/web.py`
- Verify: `tests/integration/supervisor/test_supervisor_desktop_chat.py`
- Verify: `apps/desktop/src`

- [ ] **Step 1: Run backend verification**

```bash
/home/lumber/Github/isotope/.venv/bin/python -m pytest tests/integration/supervisor/test_supervisor_desktop_chat.py -q
```

- [ ] **Step 2: Run frontend verification**

```bash
npm --prefix apps/desktop run test
npm --prefix apps/desktop run check
```

- [ ] **Step 3: Run browser smoke**

Start backend:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m isotope.features.supervisor.runner web --host 127.0.0.1 --port 8765
```

Start frontend:

```bash
VITE_ISOTOPE_DESKTOP_API_BASE=http://127.0.0.1:8765 npm --prefix apps/desktop run dev -- --host 127.0.0.1 --port 5173
```

Open:

```text
http://127.0.0.1:5173/?window=main
```

Expected: main window shows only AI chat, no Codex monitor rail/dock/event stream,
and capacity cards render when the backend emits capacity events.

- [ ] **Step 4: Commit implementation**

```bash
git add docs/superpowers/plans/2026-06-02-ai-chat-capacity-surface.md src/isotope/features/supervisor/desktop_chat.py src/isotope/features/supervisor/web.py tests/integration/supervisor/test_supervisor_desktop_chat.py apps/desktop/src
git commit -m "feat(desktop): show capacity calls in chat"
```
