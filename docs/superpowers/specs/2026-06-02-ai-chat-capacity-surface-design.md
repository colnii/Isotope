# AI Chat Capacity Surface Design

状态：`design review`

日期：2026-06-02

## 1. Purpose

Desktop frontend 的下一步不是继续做 Codex 监控台，而是收敛成一个
AI 对话入口。用户在主窗口和小窗里主要看到对话；当 AI 通过 Supervisor
capacity 调用能力时，界面要透明展示这次能力调用的状态和低敏详情。

产品目标：

- 去掉默认用户路径里的 Codex 监控内容：activity rail、inspector、event
  replay、worker / goal / approval dashboard 信息不再占据 UI。
- 主窗口成为纯 AI 对话界面。
- 小窗成为轻量 AI 对话入口，只保留必要输入、最近对话和打开主窗口能力。
- capacity 调用以聊天内联卡片展示，默认折叠，展开后可读、可滚动、可关闭。
- 支持全屏查看同一份 capacity 详情，全屏可关闭。

## 2. Reuse Audit

应复用：

- `src/isotope/features/supervisor/web.py`
  - 现有 `/desktop/chat` SSE 路由已经负责桌面聊天流。
  - 新增 capacity 事件应沿用这条流，而不是新建独立聊天协议。
- `src/isotope/features/supervisor/desktop_chat.py`
  - 现有 chat context 已包含 low-sensitive Supervisor state 和 capacity manifest。
  - 后续应在这里定义对话层 capacity 展示事件的低敏投影。
- `src/isotope/features/supervisor/commands/handlers/capacity.py`
  - 已有 `agent_loop_json_summary()`、`capability_run` 提取和 capacity memory
    记录路径。
  - 前端详情应优先使用这些低敏字段，而不是 raw agent loop payload。
- `apps/desktop/src/lib/client/agentClient.ts`
  - 已能解析 `/desktop/chat` SSE 的 `delta` / `done` / `error`。
  - 应扩展为解析 capacity 事件。
- `apps/desktop/src/lib/stores/appState.ts`
  - 已维护 chat message 状态。
  - 应把 capacity calls 挂到对应 assistant message 上。
- `apps/desktop/src/lib/components/main/ConversationWorkspace.svelte`
  - 已是主聊天区域。
  - 可演进成主窗口和小窗共用的聊天主体。

不作为本轮用户路径复用：

- `ActivityRail.svelte`、`InspectorDock.svelte`、`EventStream.svelte`
  - 它们属于 Codex 监控台形态，本轮从主用户路径移除。
- `replayMockEvents`
  - 继续用于测试或旧 dev shell 时可以保留，但不能出现在 AI 对话主体验里。
- `runningToolCalls`
  - 这是 generic tool call 语义。本轮产品口径是 capacity 能力调用。

## 3. Scope

### Must Have

- `?window=main` 只显示 AI 对话体验，不显示 activity、inspector、event
  replay、worker、goal、approval dashboard。
- `?window=mini` 只显示轻量 AI 对话体验，不显示 Codex 监控状态。
- 对话提交继续走真实 `/desktop/chat` 后端。
- 后端 SSE 可表达 capacity 调用生命周期。
- 前端在 assistant message 内渲染 capacity 调用卡片。
- capacity 卡片默认折叠。
- 卡片展开后显示具体内容，但内容区域有最大高度和滚动条。
- 长文本和大 JSON 不扩大整个页面。
- 卡片可从展开状态收起。
- 卡片支持全屏查看。
- 全屏查看可关闭。
- 详情展示面向人类：字段分组、状态清晰、优先摘要，再给结构化详情。
- 后端不给前端直接暴露 raw prompt、raw model output、私密上下文或无限大 payload。

### Should Have

- 同一条 assistant message 支持多个 capacity 调用卡片。
- capacity 调用卡片显示能力名、状态、耗时或完成时间、输入摘要、结果摘要。
- JSON / 文本详情提供复制友好的排版，但不要求本轮实现复制按钮。
- 小窗中可以折叠显示 capacity 摘要；深度查看可打开主窗口或全屏详情。

### Later

- 全局 capacity 历史面板。
- 独立 artifact viewer。
- 右侧 inspector 或 event stream 的新形态。
- capacity 调用重试、批准、取消等控制按钮。
- 多会话历史检索。

## 4. Product Shape

### Main Window

主窗口是单列聊天界面：

```text
Main chat window
├── header: Isotope / active model status
├── conversation scroll area
│   ├── user messages
│   ├── assistant text deltas
│   └── inline capacity cards
└── composer
```

不再渲染 `ActivityRail`、`InspectorDock`、`EventStream` 或 snapshot dashboard。
如果当前实现仍需要加载 snapshot 作为 chat context 或 fallback 数据，它应留在
后端或 store 内部，不作为可见 UI。

### Mini Window

小窗是紧凑对话入口：

```text
Mini chat window
├── compact conversation preview
├── latest assistant / capacity summary
├── composer
└── open main window control
```

小窗不展示 Supervisor 状态徽标、goal 数量、审批数量、worker 状态或事件流。
capacity 详情在小窗里默认只给摘要；需要查看大内容时打开全屏详情或主窗口。

### Orb And Dev Shell

orb 只作为打开聊天入口，不展示 Codex 监控数字。dev shell 可以继续作为开发
辅助入口存在，但不能成为默认产品体验，也不能影响主窗口和小窗的去监控化目标。

## 5. Capacity Data Contract

`/desktop/chat` SSE 保留现有事件：

- `start`
- `delta`
- `done`
- `error`

新增 capacity 事件：

- `capacity_start`
- `capacity_update`
- `capacity_result`

事件 payload 使用低敏 projection：

```json
{
  "id": "capacity_call_...",
  "capacity_id": "memory.query",
  "title": "Memory query",
  "status": "running",
  "input_summary": {
    "query": "capacity arguments",
    "max_results": 5
  },
  "result_summary": {
    "status": "ok",
    "result_count": 3
  },
  "details": [
    {
      "label": "Inputs",
      "kind": "json",
      "content": {
        "query": "capacity arguments",
        "max_results": 5
      }
    },
    {
      "label": "Results",
      "kind": "json",
      "content": {
        "status": "ok",
        "results": []
      }
    }
  ]
}
```

Projection rules:

- Prefer semantic fields over raw blobs.
- Include `capacity_id`, status, selected operation, safe inputs, safe result summary,
  artifact refs and domain-specific summaries.
- For `memory.query`, show query, result count, content policy and safe result previews.
- For `research.search`, show provider, source count, artifact count and source previews.
- For `screen.report`, show observe/control status and screenshot availability metadata,
  not raw screenshots unless a safe artifact viewer exists.
- For `supervisor.codex_operation`, show operation, target worker/session labels and
  low-sensitive operation result summary.
- Unknown large objects are rendered as JSON detail blocks with size caps.

Payload limits:

- Backend sends bounded detail content.
- Frontend enforces visual bounds even if content is long.
- Over-limit content is summarized with an explicit truncation note and safe artifact ref
  when available.

## 6. Frontend State Model

Extend chat state from text-only messages to messages with capacity calls:

```ts
type DesktopChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  provider?: string;
  model?: string;
  capacityCalls?: DesktopCapacityCall[];
};
```

`DesktopCapacityCall` stores:

- stable id
- capacity id and title
- status
- input summary
- result summary
- detail sections
- timestamps if provided
- expanded flag in local UI state
- fullscreen flag or selected fullscreen id in component state

`agentClient` should parse capacity SSE events and call handlers such as
`onCapacityStart`, `onCapacityUpdate`, and `onCapacityResult`. `appState` maps
those events into the active assistant message.

## 7. UI Behavior

Capacity cards:

- Default collapsed.
- Collapsed view: icon, title, status, one-line summary, expand button.
- Expanded view: grouped sections, each with label and type-aware renderer.
- Large text or JSON sits inside a scrollable region.
- Expanded card has a close/collapse button.
- Fullscreen button opens a modal-like full-window viewer.
- Fullscreen viewer can close with a visible close button and Escape key.

Detail rendering:

- Short scalar fields render as key-value rows.
- Lists render as compact rows with labels and counts.
- JSON renders in a monospace scroll region.
- Long prose renders in a readable scroll region with normal wrapping.
- Raw-looking payload keys are not shown unless they have passed the low-sensitive projection.

## 8. Error Handling

- If a capacity event is malformed, the assistant message shows a compact error card
  instead of breaking the whole chat stream.
- If the backend chat stream errors, existing chat error handling remains.
- If a capacity result is missing after `capacity_start`, the card remains in a
  non-completed state and the final `done` event does not falsely mark it successful.
- If detail content is truncated, the UI says so explicitly.

## 9. Testing

Backend tests:

- `/desktop/chat` can emit capacity SSE events without leaking raw content.
- Projection includes expected fields for at least one representative capability.
- Malformed or over-large result data is bounded.

Frontend tests:

- `agentClient` parses `capacity_start`, `capacity_update`, and `capacity_result`.
- `appState` attaches capacity calls to the active assistant message.
- Capacity cards default collapsed.
- Expanded cards show detail sections without expanding the page unboundedly.
- Fullscreen viewer opens and closes.
- Main window no longer renders Codex monitor components.
- Mini window no longer renders Codex monitor status.

Verification:

- `npm --prefix apps/desktop run test`
- `npm --prefix apps/desktop run check`
- Relevant Python tests for `/desktop/chat`
- Browser smoke at `http://127.0.0.1:5173/?window=main`

## 10. Acceptance Criteria

- A user can ask in the chat and see AI text streaming as before.
- When a capacity call happens, the chat shows an inline capacity card.
- The card is folded by default.
- Expanding the card reveals concrete, human-readable details.
- Large content scrolls inside the detail area instead of enlarging the whole UI.
- Fullscreen detail view opens and closes.
- Expanded view closes.
- Main window and mini window no longer show Codex monitoring UI.
- The visible product reads as AI chat with transparent capacity calls, not a
  Supervisor dashboard.
