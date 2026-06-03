# Supervisor Desktop Capacity Agent Design

状态：`design review`

日期：2026-06-03

## 1. Purpose

本设计把 `desktop chat` 和 `Supervisor` 收敛为同一个产品方向：

- `desktop chat` 是用户和 Supervisor 对话的入口。
- `Supervisor` 从 Codex Supervisor 专用控制台，逐步转成通用 capacity agent。
- `agent loop` 是底层执行循环，负责让模型选择下一步、执行 capability、接收低敏观察结果，并继续推进。

这不是推倒重写。当前仓库已经有 chat、capacity runner、Supervisor LLM action 和 agent loop 的分散实现。本轮目标是把它们收敛成一个共享产品 contract，让产品入口都能：

1. 给模型可发现的 capability manifest。
2. 让模型自主选择 capability 或直接回答。
3. 由系统补充产品运行上下文。
4. 经 agent loop 执行 capability。
5. 把低敏 summary / observation 回传给模型继续判断。
6. 在没有合适 capability 时记录 capability gap，供后续开发基础能力。

## 2. Current State

### Desktop Chat

入口：

- `src/isotope/features/supervisor/web.py`
- `src/isotope/features/supervisor/desktop_chat.py`

已有能力：

- `/desktop/chat` 通过 SSE 返回 `start` / `delta` / `done` / `error`。
- system prompt 已包含 registry-derived `capacity_manifest`。
- recent history 只传 `{role, content}`，并限制为最近 12 条消息左右。
- 如果配置了 `desktop_chat_capacity_provider`，当前会先尝试一次 capacity selection，再把 `capacity_result` 注入给回答模型。

不足：

- capacity selection 和 final answer 是两段式前置流程，不是同一个多轮 product agent loop。
- 没有正式的 capability gap 记录面。
- context/discovery 主要靠预加载 manifest 和少量 history，不足时还没有统一的 discovery loop。

### Supervisor

入口：

- `src/isotope/features/supervisor/commands/handlers/capacity.py`
- `src/isotope/features/supervisor/llm_action/*`
- `src/isotope/features/supervisor/commands/llm/*`

已有能力：

- LLM 可以生成 `capacity_decisions`。
- ready 的 decision 会生成 `capacity_call_specs`。
- `call_capacity` 可以经 `_execute_agent_loop_capacity_step(...)` 进入 agent loop 的 `call_capability`。
- `agent_loop_json_summary(...)` 已提供低敏结果摘要。

不足：

- Supervisor 仍以 Codex Supervisor 私有 action 流为主，capacity 只是其中一个 action kind。
- 很多 Supervisor 操作还没有注册为 capability。
- `capacity_decisions` / `capacity_call_specs` 和 desktop chat 的 capacity path 没有共用一个 product conversation contract。

### Agent Loop

入口：

- `src/isotope/agents/loop/control.py`
- `src/isotope/agents/loop/step.py`
- `src/isotope/agents/loop/provider_planner.py`
- `src/isotope/agents/loop/runner.py`

已有能力：

- `next_actions` 中包含 `call_capability`。
- provider planner 可以让模型从 `next_actions` 里选择一步。
- step driver 会检查当前 phase，只允许执行当前可用 step。
- `call_capability` 复用 `CapabilityRunner` 并生成 low-sensitive artifact result。

不足：

- `direct_answer` 当前属于 chat 层，不是 agent loop step。
- `report_capability_gap` 还不是 agent loop step 或可记录产品事件。
- provider planner 的 prompt 是底层 step JSON，不适合作为用户产品对话 contract 直接暴露。

## 3. Reuse Audit

必须复用：

- `CapabilityRunner.list_capabilities()` 作为 capability discovery 来源。
- `CapabilityRunner.plan_capability_run(...)` / `run_capability(...)` 作为 launchability 和执行入口。
- `select_capacity_call(...)` 的 input contract 校验和参数填充能力。
- `run_agent_loop_step(...)` / `run_agent_loop_tick(...)` 的 step 执行和 phase guard。
- `agent_loop_json_summary(...)` 的低敏 summary 投影。
- `build_desktop_chat_context(...)` 现有 manifest 构造和 recent history 清洗。
- `/desktop/chat` SSE 路由，继续作为桌面对话入口。

暂不复用为主流程：

- Supervisor 私有 `llm_action` kind 扩写。它继续兼容旧路径，但新能力优先登记到 capability。
- 手写 prompt 里的固定 Supervisor 状态 dump。基本状态可以预加载，但不能替代 context/discovery capability。
- 单 tick deterministic `_execute_agent_loop_capacity_step(...)` 作为唯一形态。它可作为底层执行 helper，但产品入口需要多轮 loop contract。

## 4. Parameter And Context Policy

参数缺口不能统一处理成 `missing_inputs`。产品层要分类：

### User Intent

用户意图不要求用户显式填表。模型可以根据自然语言猜测、推进、调用 capability 验证猜测。产品不通过提示词限制模型必须先问用户。

实际副作用由 capability allowlist、approval、runner contract 和 input contract 控制。

### System Context

系统必须提供产品运行上下文，用户不需要填写：

- `state_root`
- `root`
- `cwd`
- `run_id`
- `session_id`
- current desktop chat history window
- capability manifest
- basic Supervisor status summary

这些字段由产品入口自动注入，且必须低敏、可裁剪。

### Environment Understanding

模型对环境缺乏理解时，应优先调用 context/discovery capability 查询更多内容。例如：

- 当前有哪些 worker / session？
- 当前 active goal 是什么？
- 哪个 run 等待 approval？
- 某个 capability 的详细 input contract 是什么？

如果缺少对应 context/discovery capability，模型应记录 capability gap，而不是把问题都转成用户缺参数。

### Capability Gap

capability gap 表示产品基础能力不足，不是本轮失败的普通错误。gap 记录应包含：

- `gap_id`
- `requested_capability` 或 `missing_capability_kind`
- `reason`
- `user_goal_summary`
- `needed_context`
- `suggested_next_capability`
- `source_entrypoint`

gap 记录必须低敏，不保存 raw prompt、raw response、完整 transcript、secret、token 或大段 artifact content。

## 5. Target Product Flow

共享产品流程：

```text
User message
  -> Product conversation context
  -> Model decision
       -> direct answer
       -> call capability
       -> report capability gap
  -> If capability call:
       -> system fills known context inputs
       -> agent loop executes call_capability
       -> low-sensitive observation returned
       -> model continues
  -> Final low-sensitive assistant summary
```

这个流程服务两个入口：

- Desktop chat: 用户和 Supervisor 对话。
- Supervisor automation: 后台或 CLI 也可以用同一 contract 做 capacity decision 和执行。

## 6. Product Conversation Contract

新增一个产品层 contract，暂命名为 `SupervisorConversationLoop`。它不是 agent loop core，也不是新 capability runner。它是入口适配层，负责把产品对话翻译成底层 agent loop 调用。

输入：

```json
{
  "entrypoint": "desktop_chat | supervisor",
  "state_root": "string",
  "cwd": "string",
  "user_message": "string",
  "history": [{"role": "user | assistant", "content": "string"}],
  "max_turns": 3
}
```

每一轮模型决策输出：

```json
{
  "kind": "direct_answer | call_capability | report_capability_gap",
  "answer": "string",
  "capacity_id": "string",
  "arguments": {},
  "gap": {
    "missing_capability_kind": "string",
    "reason": "string",
    "needed_context": ["string"]
  },
  "rationale": "short low-sensitive string"
}
```

规则：

- `direct_answer` 直接生成 assistant text。
- `call_capability` 必须通过 `CapabilityRunner.plan_capability_run(...)` 和 agent loop `call_capability` 执行。
- `report_capability_gap` 只记录低敏 gap，不执行副作用。
- 模型输出只是 request，实际执行由 product loop 校验。
- 不把 raw provider messages 或 raw provider response 放入 result。

## 7. Context Preload

产品入口可以预加载少量基本信息，减少无谓 discovery call：

- capability manifest summary。
- 当前 `cwd`。
- 当前 `state_root`。
- recent history。
- Supervisor status 的摘要级字段，例如 active goals count、pending decisions count、recent notification count。

不预加载：

- full dashboard JSON。
- full event log。
- raw prompt / transcript。
- artifact full content。
- large worker/session dumps。

需要详细环境信息时，模型应调用 context/discovery capability。

## 8. First Implementation Slice

第一批实现只做后端 product loop，不做大规模前端重塑：

1. 新增 `src/isotope/features/supervisor/conversation_loop.py`。
2. 新增 product decision parser / sanitizer。
3. 复用 `build_desktop_chat_context(...)` 构造 manifest。
4. 复用 `CapabilityRunner` 做 plan 和 execution。
5. 复用 agent loop `call_capability` 执行 capability。
6. 新增 capability gap 低敏记录 helper。
7. 将 `stream_desktop_chat_events(...)` 切到 conversation loop，仍输出现有 SSE：
   - `capacity_start`
   - `capacity_result`
   - `delta`
8. 保留旧 `desktop_chat_capacity_provider` 兼容路径，但新路径优先。
9. 给 Supervisor capacity command 增加同一 product loop helper 的可测试入口，先不替换所有 CLI 行为。

第一批不做：

- 全量迁移 Supervisor 私有 `llm_action`。
- 重命名整个 `features/supervisor`。
- 前端视觉大改。
- hosted API。
- unbounded multi-agent scheduling。
- 自动执行非 allowlisted 写操作。

## 9. Testing

优先测试：

- desktop chat plain greeting 仍直接回答，不产生 capacity result。
- desktop chat 模型选择 capability 时，经 agent loop 执行并把低敏 observation 注入后再回答。
- 系统自动补 `state_root` / `root` / `cwd` / `run_id`。
- 模型缺环境理解时可选择 context/discovery capability，而不是被要求问用户。
- provider 报告 capability gap 时，写入低敏 gap record，SSE 不泄漏 raw prompt / messages。
- capability 不可 launch 时 fail closed，并把低敏 blocked summary 回给模型。
- history 仍遵守 12-message window 和 compaction contract。

验证命令：

```bash
.venv/bin/python -m pytest tests/integration/supervisor/test_supervisor_desktop_chat.py -q
.venv/bin/python -m pytest tests/unit/agents/loop tests/unit/capabilities -q
git diff --check
```

## 10. Migration Notes

长期方向：

- `Supervisor` 保留为 product agent 名称，但不再等同于 Codex Supervisor 单功能。
- Codex worker/session 管理迁成一组 `supervisor.*` capabilities。
- `desktop chat` 和 Supervisor automation 都调用同一 conversation loop。
- agent loop 继续保持底层，不吸收产品 UI 语义。
- capability gap 成为基础能力开发 backlog 的输入。

本轮完成后，后续可以单独开 slice：

- 注册更多 Supervisor context/discovery capabilities。
- 将 `llm_action` 的私有 action kind 逐步迁到 capability。
- 给 capability gap 增加 UI 展示和开发状态。
- 把 desktop frontend 默认体验改成和 Supervisor agent 对话。
