# Model Tool Call Bridge Boundary v0.2

状态：`terminal_exec bridge follow-up implemented / provider boundary separate`

本文记录模型工具调用桥的最小边界。这里的 model tool call bridge 指“把一个已经确定的模型工具选择，转成 Isotope 内部受控工具入口”。它本身不是 OpenAI / Claude / provider adapter；真实 provider 选择工具的第一条窄边界另见 [LLM Provider Tool Call Boundary](./llm-provider-tool-call-boundary-v0.2.md)。

## 1. Boundary

当前目标很窄：

- 模型侧先通过 `InProcessServer.get_model_tool_catalog(...)` 看到工具目录。
- 外层 caller 把一个 deterministic model decision 传给 bridge。
- bridge 只负责验证这个工具在当前 catalog 中是 enabled，并把 `terminal_exec` 交给既有 `submit_action(...)` 受控执行链，或把 `codex_task` 转交给显式 in-process HTTP facade route。
- approval、policy、artifact、event log、read model 仍走既有 Isotope 边界。

它不让模型绕过 approval，也不把 prompt / stdout / stderr / transcript full content 放进 bridge result、HTTP response、event 或 read model。

## 2. Current Slice

当前已实现：

- `src/isotope_kernel/model_tool_bridge.py`
- `submit_model_tool_call(app, run_id, call)`
- `tests/isotope_kernel/test_model_tool_bridge.py`
- `python -m isotope_kernel.demo --scenario model-tool-bridge`
- `python -m isotope_kernel.demo --scenario model-tool-bridge --trace`
- `python -m isotope_kernel.demo --scenario model-tool-bridge --json`

当前行为：

- 只接受 deterministic `call` dict，例如 `{"tool_name": "codex_task", "arguments": {"prompt": "...", "summary": "..."}}`。
- 读取 `app.server.get_model_tool_catalog()`，确认工具在 `tools` 中 enabled。
- 如果 `codex_task` 仍在 `deferred_tools`，fail closed 为 `KernelError(code="model_tool_not_enabled")`，不追加 events / artifacts。
- `terminal_exec` 通过 `app.server.submit_action(...)` 进入既有 action / policy / approval / executor / artifact path；模型只能提交 structured argv，不能提交 shell string。
- `terminal_exec` 默认不强制 approval；如果模型显式传 `requires_approval=true`，bridge 会先停在 existing approval pause / resume boundary，批准前不启动命令。
- `terminal_exec` bridge result 只返回低敏 status / route / proposal id / decision id / approval id / execution id / run state / artifact ref，不返回 stdout / stderr full content。
- 如果模型选择当前 bridge 没有 route 的其他 enabled tool，fail closed 为 `KernelError(code="model_tool_route_not_enabled")`。
- `codex_task` 必须保持 approval required；模型不能用 `requires_approval=False` 关闭审批。
- 通过 `POST /runs/{run_id}/codex-tasks` 提交 pending approval；未批准前不启动 Codex。
- route 返回的 structured error 会保留为 `KernelError`，例如 unknown run 仍是 `not_found`，而不是退化成普通异常。
- 批准后仍由既有 approval resolve route 触发 `CodexCliBackend`。
- bridge 返回低敏 status / route / approval id / proposal id / decision id / run state / artifact ref，不返回 prompt、stdout、stderr 或 transcript full content。
- `model-tool-bridge` demo 用 fake runner 默认展示完整链路：catalog check -> deterministic `codex_task` selection -> pending approval -> approval resolution -> Codex CLI backend handoff -> artifact / replay / checkpoint。它不启动 hosted/product route，也不把 prompt / transcript full content 打印到 plain / trace / JSON。

## 3. Not Implemented

仍未实现：

- product-level real LLM chat / agent loop。
- OpenAI / Responses / Claude provider router。
- hosted/product HTTP route。
- automatic tool-result loop。
- streaming。
- real cancel。
- workspace write / diff / changed-files policy。
- UI / auth / multi-user。

## 4. Reopen Conditions

只有出现以下情况，才继续打开：

- 用户明确要求接入新的真实 LLM provider 或 live smoke。
- application-layer prototype 需要更完整的 model planning loop。
- external review 指出当前 deterministic bridge 不足以解释模型工具调用边界。

下一步若继续，应从 `docs/llm-provider-tool-call-boundary-v0.2.md` 的 reopen conditions 走；不要让模型绕过 approval。
