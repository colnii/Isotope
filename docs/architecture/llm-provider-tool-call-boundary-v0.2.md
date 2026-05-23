# LLM Provider Tool Call Boundary v0.2

状态：`first slice complete / provider route, bounded two-step tool-result execution route, configurable product chat route tool allowlist, terminal-tool diagnosis, final-answer close-out, product-chat smoke, app-entry preflight / user-message / resume-state helpers, two-step app-entry local resume state diagnostics / CLI error hints, and app-entry demo available`

本文记录真实 LLM provider 接入的第一条窄边界。这里的真实 provider 只负责“从 Isotope 给出的工具目录里选择一个 tool call，或给出一次最终回答”，不直接执行工具、不直接改 RunState、不把模型回答当成 kernel truth。

本 slice 参考 aggressive branch 里的 DeepSeek provider 写法：无新增依赖、provider 配置从统一 `ISOTOPE_LLM_*` 入口解析、DeepSeek 专用 env 只保留兼容、transport 可替换、测试不需要真实网络。主线做了收窄：provider 输出必须再交给既有 `submit_model_tool_call(...)`，不能绕过 approval / policy / artifact / event log。

## 1. Boundary

当前链路是：

1. `submit_llm_tool_call(...)` 读取 `app.server.get_model_tool_catalog()`。
2. provider 收到 `messages` 和当前 enabled tools，只能返回一个 tool call。
3. `submit_llm_tool_call(...)` 把 provider 返回的 `tool_name + arguments` 交给 `submit_model_tool_call(...)`。
4. 后续仍走现有 in-process HTTP facade / approval / Codex task adapter path。
5. 批准执行完成后，Isotope 会先构造一条低敏 `assistant.tool_calls` 占位消息，只包含 provider tool call id、tool name 和空参数 `{}`，再由 `build_llm_tool_result_message(...)` 把 status、execution id 和 structured `artifact_ref` 包成可回给模型的 tool message。
6. `select_llm_tool_result_followup(...)` 可以把这个低敏 tool message 再交给 provider 做一次 follow-up tool choice，保持只选择不提交的旧边界。
7. `submit_llm_tool_result_followup(...)` 可以在调用方明确让第一次工具执行 `complete_run=False` 时，把第二次 provider choice 再走同一 catalog / approval / artifact path；第二次仍先停在 pending approval，批准后才执行。
8. `POST /runs/{run_id}/llm/tool-result-followups` 是上述 helper 的显式 in-process facade route；它只在 `create_llm_provider_http_app(...)` 中启用，不是 real HTTP server。
9. `POST /runs/{run_id}/llm/chat-turns` 是显式 product-chat in-process facade route；它只在 `create_llm_product_chat_http_app(...)` 中启用。默认 app 和 provider route app 仍返回 `501 not_enabled`。
10. product chat route first slice 每个 request 只允许一次 provider tool choice 或一次 final answer。默认 route 仍只给 provider 暴露 `codex_task`，但 explicit app 可用 `tool_names=("terminal_exec",)` 收窄成 terminal capacity：provider 只能选择被提供的工具，未提供工具会 fail closed 且无 action / artifact side effect；`terminal_exec` 结果通过同一 artifact-backed safe tool-result message 回给 provider。resume turn 必须带前一次 safe `llm_result` 和 approved / completed `tool_execution_result`，再提交下一次 pending approval、受控 terminal action，或在 provider 返回 final answer 时由 Isotope 通过 `write_artifact_tool` 记录回答并完成 run；`max_tool_steps > 1` fail closed。
11. `submit_llm_product_chat_turn_with_preflight(...)` 是较底层的应用层入口 helper；`submit_llm_product_chat_user_message_with_preflight(...)` 是一条用户消息入口。二者都不是新 route：它们只接受低敏 `preflight.ready=true` 作为放行信号；blocked / missing / malformed preflight 返回 `412 blocked_by_preflight`，且不联系 provider、不调用 runner、不追加 events、不回显 messages。用户消息入口还会在空消息时返回 `400 invalid_request`，并在 preflight blocked 时给出低敏 explanation。

这意味着真实 LLM 不能：

- 自己启动 Codex。
- 自己执行 terminal / shell。
- 关闭 approval。
- 把 prompt、API key、provider raw response、stdout / stderr full content 写进 event / read model / safe result。

## 2. Current Slice

当前已实现：

- `src/isotope/llm_provider.py`
- `src/isotope/llm_live_smoke.py` 作为命令 facade（门面入口）
- `src/isotope/llm_live_smoke_config.py` 承接 smoke config（配置）
- `src/isotope/llm_live_smoke_runs.py` 承接 run/diagnose（运行/诊断）helper
- `src/isotope/llm_product_chat_app.py`
- `src/isotope/http_api.py`
- `src/isotope/demo.py`
- `DeepSeekToolCallProvider`
- `DeepSeekChatProvider`
- `LLMToolCall` / `LLMToolCallResponse`
- `LLMResponse`
- `LLMFinalAnswerResponse`
- `LLMProviderResolution`
- `resolve_llm_tool_call_provider(...)`
- `submit_llm_tool_call(app, run_id, provider, messages, max_tokens=..., complete_run=True)`
- `submit_llm_chat_turn(app, run_id, provider, messages, llm_result=None, tool_execution_result=None, max_tokens=..., complete_run=True)`
- low-sensitive assistant tool-call placeholder for provider follow-up messages
- `build_llm_tool_result_message(llm_result, tool_execution_result)`
- `select_llm_tool_result_followup(app, run_id, provider, messages, llm_result, tool_execution_result, max_tokens=...)`
- `submit_llm_tool_result_followup(app, run_id, provider, messages, llm_result, tool_execution_result, max_tokens=..., complete_run=True)`
- `run_llm_tool_call_live_smoke(...)`
- `diagnose_llm_tool_call_live_smoke(...)`
- `run_llm_terminal_tool_live_smoke(...)`
- `diagnose_llm_terminal_tool_live_smoke(...)`
- `python -m isotope.llm_live_smoke terminal-tool --json`
- `python -m isotope.llm_live_smoke terminal-tool --fake-provider --json`
- `python -m isotope.llm_live_smoke terminal-tool --diagnose --json`
- `LLMProductChatLiveSmokeConfig`
- `run_llm_product_chat_live_smoke(...)`
- `diagnose_llm_product_chat_live_smoke(...)`
- `python -m isotope.llm_live_smoke product-chat --json`
- `python -m isotope.llm_live_smoke product-chat --diagnose --json`
- product-chat readiness `preflight.ready`
- `submit_llm_product_chat_turn_with_preflight(app, run_id, preflight=..., messages=..., ...)`
- `submit_llm_product_chat_user_message_with_preflight(app, run_id, preflight=..., user_message=..., ...)`
- `build_llm_product_chat_entry_resume_state(response, root=..., run_id=..., preflight=...)`
- `submit_llm_product_chat_entry_resume(app, state, messages=..., max_tokens=...)`
- `summarize_llm_product_chat_entry_response(response)`
- `python -m isotope.llm_live_smoke product-chat-entry --message "..." --json`
- `python -m isotope.llm_live_smoke product-chat-entry --state-file <state.json> --message "..." --json`
- `python -m isotope.llm_live_smoke product-chat-entry --resume-state <state.json> --json`
- `python -m isotope.demo --scenario llm-product-chat-app-entry`
- `python -m isotope.demo --scenario llm-terminal-tool-loop`
- `run_deepseek_tool_call_live_smoke(...)`
- `diagnose_deepseek_tool_call_live_smoke(...)`
- `create_llm_provider_http_app(...)`
- `create_llm_product_chat_http_app(...)`
- `tests/isotope/test_llm_provider_tool_loop.py`
- `tests/isotope/test_llm_live_smoke.py`
- `tests/isotope/test_http_api_llm_provider_route.py`
- `tests/isotope/test_http_api_llm_product_chat_route_boundary.py`
- `tests/isotope/test_http_api_llm_product_chat_route_contract.py`
- `tests/isotope/test_llm_product_chat_app_entry.py`
- `tests/isotope/test_llm_product_chat_app_entry_demo_scenario.py`
- `tests/isotope/test_llm_terminal_tool_loop_demo_scenario.py`
- `tests/isotope/test_llm_provider_route_demo_scenario.py`
- `tests/isotope/test_llm_tool_result_loop_demo_scenario.py`

`resolve_llm_tool_call_provider(...)` 是当前统一 provider 发现入口：

- primary env: `ISOTOPE_LLM_PROVIDER=deepseek`、`ISOTOPE_LLM_API_KEY`、optional `ISOTOPE_LLM_MODEL`、`ISOTOPE_LLM_BASE_URL`、`ISOTOPE_LLM_TIMEOUT_SECONDS`
- compatibility env: `DEEPSEEK_API_KEY`、optional `DEEPSEEK_MODEL`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_TIMEOUT_SECONDS`
- unsupported provider 会返回低敏 `llm_provider_unsupported`，不会把 API key 放进 repr / result。

`DeepSeekToolCallProvider` 使用 OpenAI-compatible `/chat/completions` tool-call / chat-turn shape：

- `model`: 默认 `deepseek-v4-flash`
- `base_url`: 默认 `https://api.deepseek.com`
- credential: 由统一 resolver 传入；直接构造 provider 时仍兼容 `DEEPSEEK_API_KEY`
- request: `select_tool(...)` 使用 `tool_choice="required"`；`select_chat_turn(...)` 使用 `tool_choice="auto"`，允许一个 tool call 或一个 final answer；两者都使用 `tools`、`thinking={"type": "disabled"}`、`temperature=0`、`stream=False`
- dependency: Python stdlib `urllib`，无新增依赖

`DeepSeekChatProvider` 是同一 provider boundary 的更窄 direct-chat wrapper：

- default model: `deepseek-v4-flash`
- endpoint: OpenAI-compatible `/chat/completions`
- request: `thinking={"type": "disabled"}`、`temperature=0`、`stream=False`
- output: `LLMResponse(provider, model, content, finish_reason, usage, raw)`
- dependency: Python stdlib `urllib`，无新增依赖
- scope: 只提供应用层 direct chat call boundary，不执行 tool，不写 event log，不修改 RunState，不替代 approval / policy / artifact handoff

当前测试覆盖：

- unified provider resolver 可在没有 `DEEPSEEK_API_KEY` 的情况下用 `ISOTOPE_LLM_PROVIDER=deepseek` + `ISOTOPE_LLM_API_KEY` 构造 provider。
- unsupported / missing provider config 返回低敏 reason code，不泄露 secret，不产生 action / artifact side effect。
- provider 会收到当前 model-facing tool catalog。
- provider-selected `codex_task` 只提交 pending approval；approval 前不启动 Codex。
- DeepSeek request 使用 OpenAI-compatible function tool-call shape。
- DeepSeek direct chat request 使用 OpenAI-compatible chat completions shape，测试通过 fake transport 离线验证，不需要真实网络或 API key。
- bad tool-call arguments fail closed，错误信息不带 raw arguments。
- provider 返回普通文本 / 无 tool call 时不产生 action / artifact side effect。
- API key、prompt、provider raw text 不进入 safe result / error details。
- generic live smoke 默认 skipped，不读取网络、不构造 provider、不产生事件。
- generic live smoke 显式开启时通过统一 resolver 检测 provider，只把 `codex_task` 这一个工具给 provider 看；成功时只到 pending approval，不批准、不启动 Codex。
- product-chat live smoke 默认 skipped，不建 session、不联系 provider、不调用 runner；显式开启后固定覆盖 direct final answer、tool choice pending approval、approval resolution、resume final answer 四个 checkpoint，返回值只包含低敏状态 / 布尔标记，不包含 messages、prompt、stdout / stderr、approval id 原值或 API key。
- `run_deepseek_tool_call_live_smoke(...)` / `diagnose_deepseek_tool_call_live_smoke(...)` 只作为 backward-compatible wrapper 保留，调用路径仍走 generic resolver。
- diagnosis helper 把常见卡点归类为低敏 `diagnosis.category`，例如 `missing_configuration`、`provider_request_failed`、`provider_response_invalid`、`tool_not_enabled`、`tool_route_not_enabled` 和 `ready`。
- diagnosis 不暴露 prompt、API key、provider raw text 或 Codex transcript；`codex_started` 在本 helper 中保持 `false`，因为它不批准 pending approval。
- `POST /runs/{run_id}/llm/tool-calls` 和 `POST /runs/{run_id}/llm/tool-result-followups` 只在 `create_llm_provider_http_app(...)` 显式启用时出现；默认 `create_http_app(...)` 返回 `501 not_enabled`。
- provider route 只把 `codex_task` 暴露给 provider，返回 pending approval，不批准、不启动 Codex，不把 request messages / provider-selected prompt 放进 safe HTTP response。
- provider route 覆盖 malformed request no-side-effect、provider failure no-action-side-effect、idempotency replay 和 route inventory contract。
- tool-result follow-up route 接受 `messages`、前一次 safe `llm_result` 和 approval resolve 返回的 `tool_execution_result`，调用同一 `submit_llm_tool_result_followup(...)` helper；follow-up provider messages 会先追加一条不含原始 prompt 的 `assistant.tool_calls` 占位消息，再追加 low-sensitive `tool` result message，以满足 OpenAI-compatible provider 的消息顺序要求；malformed body no-side-effect、completed run no-provider-contact、route inventory 和 prompt / transcript 不泄露均有测试覆盖。
- product chat route guard 覆盖 `POST /runs/{run_id}/llm/chat-turns`：默认 app 和 provider-enabled app 都返回 `501 not_enabled` / `llm_product_chat_route`，不列入 supported route inventory，不联系 provider，不调用 runner，不追加 events，也不回显 request messages。
- terminal-only live smoke 覆盖 `run_llm_terminal_tool_live_smoke(...)`、`diagnose_llm_terminal_tool_live_smoke(...)` 和 `python -m isotope.llm_live_smoke terminal-tool`：provider tool menu 只包含 `terminal_exec`，fake provider / real provider 都不能看到 `codex_task`；成功时 terminal action 直接走 `submit_action(...)`，safe result 只暴露 status / execution ids / artifact-ref presence，stdout / stderr 仍只进 artifact；缺 provider 配置时不创建 run。
- terminal-tool diagnosis 覆盖 `missing_configuration`、`unsupported_provider`、`provider_request_failed`、`provider_response_invalid`、`provider_selected_unoffered_tool`、`provider_tool_arguments_invalid`、`terminal_policy_denied`、`terminal_execution_failed` 和 `ready`；`preflight.ready` 只在 provider 选择 `terminal_exec` 且 terminal action completed 时为 true。失败诊断只返回低敏 reason code / flags，不暴露 argv full content、stdout / stderr、prompt、API key 或 provider raw response。
- 当前本机实测 `python -m isotope.llm_live_smoke terminal-tool --json` 已通过统一 provider 配置完成：provider 返回 `tool_calls`，选择 `terminal_exec`，Isotope 完成 terminal action，`codex_call_count=0`，safe JSON 不含 stdout / stderr。
- product chat route contract 覆盖显式 `create_llm_product_chat_http_app(...)`：该 route 列为 supported，但 provider helper routes 不列为 supported；默认只把 `codex_task` 暴露给 provider，initial turn 可提交一个 pending approval 或 artifact-backed final answer，不启动 Codex、不泄露 request messages / provider prompt；explicit `tool_names=("terminal_exec",)` 可把 product-chat route 收窄为 terminal capacity，initial turn 会通过 existing `submit_action(...)` 执行 structured argv，resume turn 只把 status / execution id / artifact ref 组成 low-sensitive tool-result message 回给 provider；provider 选择未提供工具时在 action side effect 前 fail closed；`max_tool_steps > 1` 在 provider contact 前 fail closed。
- product-chat app-entry preflight / user-message helpers 覆盖 ready / blocked / malformed preflight 和空用户消息：ready 时才转发到显式 in-process product-chat route；blocked 或 malformed 时返回 `412` 和低敏 explanation，空消息返回 `400`，且 provider / runner call count 不增加、event log 不变、request message / secret 不进入 safe response。
- product-chat app-entry resume helpers 已从 CLI 下沉到 `llm_product_chat_app.py`：`build_llm_product_chat_entry_resume_state(...)` 从 pending response 生成低敏本地 resume state；`submit_llm_product_chat_entry_resume(...)` 用该 state 批准 pending task、运行 fake Codex、再提交 safe tool-result context；`summarize_llm_product_chat_entry_response(...)` 给 CLI / app shell 使用，不携带 raw approval id、用户消息、provider prompt、transcript 或 answer content。
- resume state diagnosis 覆盖三类开发者常见错误：state 顶层 approval id 与 `llm_result.approval_id` 不一致时 fail closed；state 已标记 resumed 时在审批前 fail closed；审批上下文不存在时把底层 `unknown approval` 映射为低敏 `product_chat_entry_approval_unavailable`，不追加 events、不调用 provider / runner，也不泄露用户消息、provider prompt 或 answer content。
- `product-chat-entry --resume-state` CLI 现在会把这些 `IsotopeError` 映射成 JSON / plain failed payload：只输出 error code、category、reason、summary、next-step 和 runner call count，不抛 Python traceback，不输出 raw approval id、state file content、用户消息、provider prompt 或 answer content。
- `product-chat-entry` developer command 会先跑 product-chat preflight，再提交一条用户消息；如果 provider 选择 `codex_task` 并停在 pending approval，JSON / plain output 只暴露 `requires_approval`、`approval_id_present` 和低敏 next-step hint，不暴露 raw approval id、用户消息、provider prompt 或 assistant answer content。未传 `--state-file` 时，pending output 会提示用 `--state-file` 重跑以保存可恢复状态；传入 `--state-file <state.json>` 时会把 pending approval 所需的本地恢复上下文保存成 JSON，并提示下一步用 `--resume-state` 恢复；之后 `--resume-state <state.json>` 会读取该文件、批准 pending task、走 fake Codex 执行，再把安全 tool-result context 交回 provider 获取 final answer。为了 no-network 手工演练，`--fake-entry-pending` 只允许配合 `--fake-provider` 使用；`--resume-state` 混入 `--message`、`--state-file` 或 `--fake-entry-pending` 这类新建入口参数时，会在读取 state / 解析 provider 前 fail closed；显式 `--root` 与 state 中保存的 root 不一致时，也会在 provider resolution 前 fail closed；`--root` 或 state 中保存的 root 指向普通文件时会返回低敏 `product_chat_entry_root_invalid` 而不是 traceback；`--fake-provider --fake-entry-pending --state-file <state.json>` 会稳定生成 pending state，便于测试错文件、重复恢复、换 root 恢复错误、command root 不是目录、missing state file、already resolved approval with stale state、not-file state path、unreadable state file、not-file state-file save target、unwritable state-file parent、state-file parent not directory、unwritable post-resume state mark 和 malformed JSON state 文件。CLI 输出仍只给低敏状态；state file 是本地开发者文件，不是 event / read model / public HTTP response。
- restarted approval resolution now preserves the original `complete_run=False` choice, and restarted `submit_action(...)` can recover event-backed run context for selected non-terminal write paths. This keeps the two-step app-entry resume path open after approval without changing event append semantics.
- `python -m isotope.demo --scenario llm-product-chat-app-entry` 使用 fake provider 展示应用层入口门禁：先用 blocked preflight 验证 `412` 且无 provider / runner / event side effects，再用一条用户消息 + ready preflight 转发到显式 product-chat route 并得到 artifact-backed final answer；plain / trace / JSON 都只输出低敏状态，不输出 request messages 或 assistant answer content。
- product chat final-answer tests 覆盖 initial final answer 无 Codex / approval 直接完成、resume final answer 只使用低敏 assistant tool-call placeholder + 安全 tool-result message、HTTP safe response 不泄露 messages / prompt / stdout / stderr、terminal_exec product-chat route 只回传 safe tool-result message，以及 DeepSeek `select_chat_turn(...)` 使用 `tool_choice="auto"`。
- `python -m isotope.demo --scenario llm-provider-route` 使用 fake provider 模拟 application-layer 调用：用户消息进入 provider route，fake provider 选择 `codex_task`，Isotope 停在 pending approval；demo 同时验证 idempotency replay、event replay 和 checkpoint。
- `llm-provider-route` demo 不调用真实 LLM 网络、不启动 Codex、不批准 pending approval、不打开 real HTTP listener / product chat route，也不把 request messages / provider-selected prompt / Codex output 泄露到 plain / trace / JSON 输出。
- follow-up provider messages 会先追加 low-sensitive `assistant.tool_calls` placeholder，`function.arguments` 固定为 `{}`，避免把原始 provider prompt / tool arguments 发回 provider；随后 `build_llm_tool_result_message(...)` 将已批准执行结果转换成 OpenAI-compatible `role=tool` message，`content` 中只放 status、tool name、execution id 和 structured `artifact_ref`。
- completed tool result 缺少 structured `artifact_ref` 时 fail closed；source 缺少 provider tool call id 时 fail closed。
- `select_llm_tool_result_followup(...)` 会把低敏 tool-result message append 到 provider messages，再请求一次 provider tool choice；返回值只包含 provider / model / selected tool / previous tool call id / tool-result status / artifact ref / `submission_status=not_submitted`。
- follow-up selection 会先确认 `run_id` 存在；未知 run 在 provider contact 前 fail closed。
- `submit_llm_tool_result_followup(...)` 复用同一 safe tool-result message 和 provider choice，然后调用 `submit_model_tool_call(...)` 提交第二个工具请求；它不会绕过 catalog、approval、policy、artifact 或 event log。
- `submit_llm_tool_call(..., complete_run=False)` / provider route body `complete_run=false` 只表示“这次工具执行成功后 run 继续保持 running”，不是自动循环许可；默认仍是 `complete_run=True`，保持既有一次执行后完成 run 的行为。
- `submit_llm_tool_result_followup(...)` 要求目标 run 仍是 `running`；如果第一次工具执行已经让 run `completed`，它会在联系 provider 前 fail closed。
- `python -m isotope.demo --scenario llm-tool-result-loop` 使用 fake provider 模拟 application-layer 调用：provider 选择 `codex_task`，Isotope 先停在 pending approval，第一次 approval 后 fake Codex backend 执行但 run 保持 running，再准备低敏 tool-result message，把它交给 fake provider 做一次 follow-up choice，提交第二个 pending approval，第二次 approval 后才执行第二个 fake Codex task 并完成 run。
- `llm-tool-result-loop` demo 不调用真实 LLM 网络、不打开 real HTTP listener / product chat route，也不把 request messages / provider-selected prompt / transcript / stdout / stderr 泄露到 plain / trace / JSON 输出。
- `python -m isotope.demo --scenario llm-terminal-tool-loop` 使用 fake provider 模拟 terminal-only tool path：provider 只看见 `terminal_exec`，选择 structured argv 后由 Isotope 通过 `submit_action(...)` 执行，安全 tool-result message 只带 status / execution id / artifact ref，再由 provider 返回 artifact-backed final answer。
- `llm-terminal-tool-loop` demo 不调用真实 LLM 网络、不打开 real HTTP listener、不使用 Codex / `codex_task`，也不把 request messages / provider prompt / stdout / stderr 泄露到 plain / trace / JSON 输出。

真实 LLM provider smoke 是 opt-in；当前 resolver 支持 DeepSeek：

```bash
ISOTOPE_RUN_LIVE_LLM_SMOKE=1 \
ISOTOPE_LLM_PROVIDER=deepseek \
ISOTOPE_LLM_API_KEY=... \
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/isotope/test_llm_live_smoke.py::test_live_llm_tool_call_smoke_reaches_provider_without_starting_codex -q
```

当前本机实测结果（通过统一 resolver 解析到 DeepSeek）：

- model: `deepseek-v4-flash`
- finish_reason: `tool_calls`
- selected tool: `codex_task`
- Isotope result: `pending_user_approval`
- diagnosis: `ready`
- Codex process calls before approval: `0`

Product-chat live smoke 现在也可直接调用 helper 做固定健康检查；它会在同一个 in-process app 内走“直接回答 -> 工具选择并暂停审批 -> 批准执行 -> 带安全 tool result 恢复最终回答”的完整路径，但仍不是 hosted product chat route：

Terminal-tool smoke 也有对应的开发命令；`--diagnose` 会把常见卡点翻译成低敏 category 和 `preflight.ready`：

```bash
# 不联网，验证真实 provider 只能看到 terminal_exec 这一条工具
PYTHONPATH=src .venv/bin/python -m isotope.llm_live_smoke \
  terminal-tool --fake-provider --diagnose --json

# 走真实 provider 配置，仍不暴露 codex_task
ISOTOPE_LLM_PROVIDER=deepseek \
ISOTOPE_LLM_API_KEY=... \
PYTHONPATH=src .venv/bin/python -m isotope.llm_live_smoke \
  terminal-tool --diagnose --json
```

```python
from isotope.llm_live_smoke import (
    LLMProductChatLiveSmokeConfig,
    run_llm_product_chat_live_smoke,
)

result = run_llm_product_chat_live_smoke(
    app,
    config=LLMProductChatLiveSmokeConfig(enabled=True),
)
```

当前本机实测 product-chat smoke（通过统一 env 解析 DeepSeek，Codex runner 使用 fake runner）：

- direct final answer: `completed`
- tool choice: `codex_task` / `pending_user_approval`
- approval resolution: `running`
- resume final answer: `completed`
- fake Codex runner call count: `1`

对应的开发命令：

```bash
# 不联网，验证命令和 product-chat route 链路
PYTHONPATH=src .venv/bin/python -m isotope.llm_live_smoke \
  product-chat --fake-provider --json

# 走真实 provider 配置，但 Codex 仍使用 fake runner
ISOTOPE_LLM_PROVIDER=deepseek \
ISOTOPE_LLM_API_KEY=... \
PYTHONPATH=src .venv/bin/python -m isotope.llm_live_smoke \
  product-chat --json
```

命令退出码：

- `0`: smoke completed / skipped
- `1`: route 或 provider 返回异常结果
- `2`: provider 配置缺失或命令参数错误

## 3. Not Implemented

仍未实现：

- product chat UI / hosted route；当前 `POST /runs/{run_id}/llm/chat-turns` 只有 explicit in-process first-slice contract，不是 real listening HTTP route。
- application shell；当前 app-entry helper 只是“先看 preflight 再转发”的薄包装，不渲染 UI、不管理 session 列表、不做多轮自动循环。
- OpenAI / Claude / Anthropic provider router。
- 完整多轮 tool loop / agent loop execution；当前只有一个 bounded two-step path，且第二步仍需要显式 follow-up submission 和 approval。
- multiple tool calls。
- streaming。
- real cancel。
- workspace write / diff / changed-files policy。
- memory query / promotion。

## 4. Reopen Conditions

下一步只有在以下情况继续打开：

- 用户明确要求做 live provider smoke。
- application-layer prototype 需要把当前 in-process product chat route 提升为 hosted route，或需要 streaming / more than one tool step per request。
- external review 指出当前 one-tool-call boundary 不足。

默认下一步应等待 application-layer feedback / external review，或在明确需求下再做 hosted/product route contract；不要直接做产品化聊天入口。
