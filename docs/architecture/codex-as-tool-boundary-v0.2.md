# Codex-as-tool Boundary v0.2

状态：`in-process HTTP facade route complete / hosted product route deferred`

本文记录 `codex_task` 的边界。这里的 Codex-as-tool 指“把 Codex CLI 这类 agent CLI 当成 LLM 可请求的高阶工具”，不是 terminal backend，也不是把 Isotope 的 `terminal_exec` 变成开放 shell。

## 1. Boundary

`codex_task` 是未来的 agent CLI task 工具：

- 模型侧看到的是一个任务工具，输入是 `prompt`。
- 它不复用 `terminal_exec`，也不绕过 action / policy / approval / artifact / event log。
- 接入真实 Codex CLI 时，Codex 自己的执行 / 沙箱 / 权限模式属于外部 adapter 细节，Isotope 只负责外层约束和审计。
- 真实调用前必须有 selected adapter boundary、approval policy、artifact output policy 和 failure mapping。

## 2. Current Slice

当前已实现的最小 slice：

- `ActionTypeRegistry.model_tool_catalog(...)` 在 `deferred_tools` 中暴露 `codex_task`。
- `codex_task` 标记为 `tool_kind: agent_cli_task`，不是 terminal tool。
- Catalog 说明它需要 explicit Codex adapter boundary、approval，并且 full content 不进 event / read model。
- `ActionCompiler` 对 `codex_task` 给出明确 fail-closed 错误：`deferred tool codex_task is not callable`。
- 提交 `codex_task` 时不会 append `action.proposed`、`action.decided`、approval 或 execution event。
- `src/isotope/codex_task.py` 定义 adapter contract：`CodexTaskRequest` / `CodexTaskResult` / `CodexTaskAdapter` / structured errors。
- 只有显式使用 `ActionTypeRegistry.default(enable_codex_task=True)` 并配置 `codex_task_adapter` 时，`codex_task` 才能走 adapter path；默认仍 fail closed。
- adapter path 必须先经过 approval；批准后才 append `action.started`，输出通过 artifact / `ResourceRef` 交接。
- `action.completed` / `RunState.actions[*].codex_task` 只投影 adapter id / version / protocol / mode / status / reason code，不投影 prompt、adapter session id、本机路径、env 或输出全文。
- `src/isotope/codex_cli.py` 定义 first-slice `CodexCliBackend`：用 `codex --ask-for-approval never exec --json --sandbox read-only --cd <workspace> --ephemeral -` 作为后端调用形状，prompt 通过 stdin 传入，不进入 argv。
- `CodexCliBackendConfig.skip_git_repo_check=True` 可用于临时 smoke workspace；默认关闭，避免改变普通 repo workspace 行为。
- `CodexCliBackend` 使用 `shell=False`、不继承 `OPENAI_API_KEY` 等敏感环境变量、从 grants budget 读取 timeout、把 stdout / stderr / exit code 写入 `codex_task_transcript` artifact。
- `CodexCliBackendConfig.inherit_proxy_env=True` 只透传 proxy env allowlist（`HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` / `NO_PROXY` 及小写形式），不透传 API key；默认仍关闭，避免普通 backend 自动继承本机环境。
- `src/isotope/codex_server.py` 提供显式 `create_codex_cli_server(...)` helper：默认 `InProcessServer` 仍保持 `codex_task` deferred / not callable；只有调用该 helper 才启用 `ActionTypeRegistry.default(enable_codex_task=True, codex_task_budget_seconds=...)` 并接入 `CodexCliBackend`。
- `CodexCliServerConfig` 固定 first-slice server wiring 约束：默认 read-only Codex CLI、approval `never`、`shell=False`、server-level timeout 写入 registry budget、临时 workspace 默认允许 `skip_git_repo_check`，并默认只透传 proxy env allowlist 以支持本机网络路由。
- server wiring 测试覆盖默认 server 不变、未批准时不启动 Codex 子进程、批准后通过 Codex CLI backend 执行、低敏 `RunState.actions[*].codex_task` summary，以及 transcript 只进 artifact。
- `src/isotope/http_api.py` 提供显式 `create_codex_cli_http_app(...)` helper：默认 `create_http_app(...)` 仍不开放 Codex task route，并且 `POST /runs/{run_id}/codex-tasks` 返回 stable `501 not_enabled`。
- 只有通过 `create_codex_cli_http_app(...)` 创建的 in-process app 才把 `POST /runs/{run_id}/codex-tasks` 放进 supported route inventory。该 route 接受非空 `prompt` 和可选 `summary`，强制 approval-gated，先返回 `pending_user_approval`，不会在未批准时启动 Codex 子进程。
- 现有 approval resolve route 批准该 action 后，会经 `CodexCliBackend` 调本机 Codex CLI；HTTP response / run state 只返回低敏 action / approval / artifact refs，不返回 prompt、stdout、stderr、local path、env 或 transcript full content。
- malformed request、未知 run、idempotency replay / conflict 都走现有 HTTP facade error / idempotency contract，不产生 partial action / artifact side effects。
- `src/isotope/model_tool_bridge.py` 提供 `submit_model_tool_call(...)` deterministic bridge：它先验证当前 model-facing catalog，再把 enabled `codex_task` 转交给上述 in-process HTTP facade route；默认 deferred、unsupported route、模型关闭 approval 的尝试都会 fail closed。
- `src/isotope/codex_live_smoke.py` 提供 opt-in `run_codex_live_smoke(...)` / `diagnose_codex_live_smoke(...)` developer helpers：默认 skipped；显式 `CodexLiveSmokeConfig(enabled=True)` 时才创建临时 read-only workspace，经 `CodexTaskAdapter` 调用真实 `CodexCliBackend`，返回低敏 status / reason / `ResourceRef` / diagnosis，不返回 prompt 或 transcript full content。
- 当前测试使用 fake process runner 验证 argv / cwd / env / proxy env / timeout / failure mapping；default full regression 不依赖真实 Codex auth，live smoke 测试用 `ISOTOPE_RUN_LIVE_CODEX_SMOKE=1` 显式打开，server wiring live smoke 测试用 `ISOTOPE_RUN_LIVE_CODEX_SERVER_SMOKE=1` 显式打开，HTTP facade live smoke 测试用 `ISOTOPE_RUN_LIVE_CODEX_HTTP_SMOKE=1` 显式打开。
- 当前本机 live smoke、server-level live smoke 和 HTTP-facade live smoke 已证明 Isotope 能启动本机 Codex CLI、经 proxy env 完成真实 Codex 调用，并把 transcript 收进 artifact；它仍不代表 hosted/product route 已可用。

## 3. Not Implemented

仍未实现：

- Hosted / product route / live demo 中的 Codex task execution。
- Real LLM loop / provider adapter / automatic tool choice。
- Codex install health check / auth readiness check。
- Codex session / run / task 到 Isotope action 的完整映射。
- Streaming、real cancel、diff capture、changed-files policy。
- Workspace write policy、git worktree、container、remote executor。
- Product HTTP route、UI、auth / multi-user、public SDK。

## 4. Reopen Conditions

只有出现以下条件之一，才继续打开：

- 用户明确要求把当前 in-process HTTP facade route 升级成 hosted/product route、product flow 或更完整的 product read model。
- application-layer prototype 证明需要 Codex task 工具，而不是普通 terminal backend。
- external review 指出当前 deferred catalog / fail-closed 行为不够清楚。

下一步若继续，应先写 hosted/product route contract red tests，再把现有 in-process route 升级到真实服务入口；不要把 `codex_task` 混入 `terminal_exec`，也不要打开 `danger-full-access` / arbitrary shell。
