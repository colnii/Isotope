# Planner Input / Output Contract v0.2

状态：`draft / branch-local design`

## 1. Plain Summary

这份文档定义未来 LLM 自动规划怎么接进 Isotope。

白话说，就是先定三件事：

- AI 能看到什么。
- AI 能决定什么。
- AI 说错、乱说、越权时，系统怎么拦住。

这不是 real LLM integration，也不是完整 Agent loop 产品实现。它只是把“AI 大脑”和 Isotope 底座之间的接口先定清楚。

## 2. Why This Comes Next

前面的 Agent loop 分支已经证明底座能支撑几条关键路：

- 创建输入 artifact。
- 交给 worker helper。
- 等人审批。
- 程序重启后继续审批和执行。

下一步不应该继续凭空造 demo 场景。更有价值的是定义 planner contract：未来 LLM 只能通过这个 contract 影响 Isotope，不能直接改 event log、checkpoint、artifact store 或 private server state。

## 3. Planner Input

Planner input 是给 LLM / planner 看的“任务地图”。它应该是 summary-first（先摘要），不是把所有原文塞进去。

最小 input 包含：

| Field | Meaning |
| --- | --- |
| `session_summary` | 当前 session 的目标和约束摘要 |
| `run_summary` | 当前 run 的 goal、status、最近 action 状态 |
| `available_artifacts` | artifact 的 summary、structured `ResourceRef`、provenance；不含 full content |
| `pending_approvals` | 待审批事项摘要和 approval id |
| `workers` | worker / delegation 的状态摘要 |
| `workspaces` | 已授权 workspace binding / lease 摘要 |
| `available_capabilities` | 这次 planner 被允许请求的能力 |
| `memory_recall` | 可选 recall 结果；没有需要时可以为空 |
| `deferred_capabilities` | 明确告诉 planner 哪些能力现在不可用 |

Hard boundary：

- input 不能包含 artifact full content，除非已有 explicit retrieval grant。
- input 不能包含 raw secret、private payload、checkpoint blob 或 full event log dump。
- memory query 是 on-demand recall，不是每次 planner 都必须运行的一步。

## 4. Planner Output

Planner output 不是直接执行命令。它只是提交一组 symbolic decisions（符号化决定），再由 Isotope validator / runner 检查后执行。

最小 output shape：

```json
{
  "planner_run_id": "planner_run_001",
  "basis": {
    "run_id": "run_001",
    "input_digest": "input_summary_hash"
  },
  "decisions": [
    {
      "step": 1,
      "action": "submit_approval_gated_action",
      "reason": "Need human approval before writing result",
      "intent": {
        "action": "call_tool",
        "tool": "write_artifact_tool",
        "text_summary": "write final review artifact"
      }
    }
  ]
}
```

Allowed first actions:

- `create_source_artifact`
- `submit_worker_handoff`
- `submit_approval_gated_action`
- `get_pending_approvals`
- `resolve_approval`
- `bind_workspace`
- `verify_replay_checkpoint`

Future actions may include `query_memory`, `request_retry`, `request_cancel`, or `request_supersede`, but only after their public helper / policy boundary is explicit.

## 5. Validation Rules

Planner output must fail closed before execution when:

- JSON / structure is malformed.
- `action` is unknown.
- required fields are missing.
- requested capability is not in `available_capabilities`.
- output asks for real LLM / provider / scheduler / filesystem when disabled.
- output asks to read artifact full content without retrieval grant.
- output tries to write event log, checkpoint, artifact store, or private state directly.
- output tries to treat memory query as mandatory when no memory recall is needed.

Fail closed means:

- no partial canonical events appended.
- no artifact created.
- no worker created.
- no approval resolved.
- return a structured planner error summary.

## 6. Execution Boundary

The planner does not execute anything directly.

Flow:

1. Runtime builds planner input from projected read models and allowed refs.
2. Planner returns symbolic decisions.
3. Validator checks the decisions.
4. Runner maps allowed decisions to existing public helpers.
5. Kernel truth still comes only from canonical events, artifacts, and projected read models.

The runner may call public helpers such as:

- `create_source_artifact(...)`
- `submit_worker_handoff(...)`
- `submit_action(...)`
- `get_pending_approvals(...)`
- `resolve_approval(...)`
- `bind_workspace(...)`

It must not call private `_append(...)`.

## 7. What This Does Not Implement

This contract does not add:

- real LLM provider call
- prompt template
- model selection
- streaming
- scheduler
- real worker process
- real HTTP server
- filesystem mutation
- memory query engine
- public SDK
- product UX

## 8. Next Development Step

Next suggested branch-local batch:

`Planner I/O Validator Spike`

Plain meaning: build a small gatekeeper for fake planner output. It should accept one valid symbolic output and reject malformed / unknown / overpowered output before anything runs.

Do not connect a real LLM yet. The next useful proof is: **even if the AI says something wrong, Isotope will not blindly execute it.**
