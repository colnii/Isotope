# HTTP API Minimal Surface v0.2

状态：`surface and request validation slices implemented`

## 1. Purpose

v0.2 HTTP API 的目标，是把当前 in-process demo 能力暴露成最小 server-facing surface，而不是做完整 hosted platform。

这个 surface 应先证明现有 kernel loop 可以被外部进程以 HTTP 方式驱动和读取：create session、create run、submit input、read projected run state、read canonical events、read artifact summary。它不是 auth / streaming / hosted service / production API 设计。

当前前两批 green slice 已实现为 in-process `HttpApiApp` / `create_http_app(...)`，并补齐 request validation / no-side-effect error boundary。它是 test-client style boundary，不监听端口，不引入 FastAPI / Flask / 新依赖，也不是 production HTTP server。

## 2. Hard Boundaries

- HTTP API 不能绕过 action chain。
- HTTP API 不能直接修改 `RunState` / `SessionState`。
- HTTP API 只能通过 runtime / service boundary 创建 canonical events 或读取 projected state。
- executor 仍只能使用 `PolicyDecision.grants`。
- artifact / memory / checkpoint 仍不能成为第二事实源。
- memory 仍是 boundary-only，不能通过 HTTP 假装成真实 query / storage。
- API response 不能暴露 artifact full content，除非后续 retrieval policy 明确允许。
- HTTP handlers 不能直接解释 checkpoint state；checkpoint-assisted rebuild 仍必须走 projector-owned boundary。
- HTTP handlers 不能直接读取 executor in-memory state 作为 run truth。

## 3. Minimal Endpoints

v0.2 只定义这些 endpoint：

```text
POST /sessions
POST /sessions/{session_id}/runs
POST /runs/{run_id}/input
GET  /runs/{run_id}
GET  /runs/{run_id}/events
GET  /artifacts/{artifact_id}/summary
GET  /health
```

当前 `HttpApiApp.routes()` 只暴露上述 minimal surface。deferred endpoints 不在 route table 中，并以 not found / not enabled 风格处理。

暂不实现：

- SSE / streaming
- auth
- multi-user
- approval API
- memory query API
- external ingestion API
- full artifact content API
- checkpoint inspection API
- plugin / dynamic tool registration API

## 4. Endpoint Semantics

### POST /sessions

创建 session，只返回 session id 和状态。

该 endpoint 不应执行 action、不应创建 run、不应写 artifact，也不应暴露 memory/checkpoint internals。

### POST /sessions/{session_id}/runs

创建 run，不执行复杂工作。

run 创建只能产生当前 runtime/service boundary 允许的 canonical events；response 应返回 run id、session id 和最小状态。

### POST /runs/{run_id}/input

提交输入，必须走现有 AgentRuntime / `ActionCompiler` / `PolicyEngine` / `Executor` 路径。

该 endpoint 不能直接写 `ActionExecution`、不能直接创建 artifact、不能直接把 run 标记为 completed。success / failure 仍由 canonical events 和 projector read model 表达。

当前实现委托现有 `InProcessServer.submit_input(...)`，因此状态变更仍走 `ActionCompiler -> PolicyEngine -> Executor` action chain，不绕过 kernel contract。

### GET /runs/{run_id}

返回 `RunProjector` 生成的 read model，不读 executor 内存状态。

实现可以使用 full replay 或 checkpoint-assisted rebuild，但 HTTP 层不能直接解释 checkpoint state。

### GET /runs/{run_id}/events

返回 canonical event log 的只读视图。

这是 audit / debug surface，不是 mutation API。它不能补写、重排、压缩或修复 event log。

### GET /artifacts/{artifact_id}/summary

返回 artifact summary / ref / provenance，不返回 full content。

如果未来需要 full content 或 controlled expand，必须先定义 retrieval policy / grants / audit boundary，不能把 summary endpoint 扩成 raw content endpoint。

当前实现从 canonical `artifact.created` event 中读取 summary / ref / provenance metadata，不读取或返回 artifact full content / raw content。

### GET /health

返回 process health，不代表 run 状态。

它只回答 server process 是否可响应，不证明 event log、artifact store、checkpoint store 或 memory boundary 已完成业务动作。

## 5. Transport Choice

v0.2 可以使用 Python 标准库或轻量依赖，但先不要承诺长期 framework。

HTTP 是当前 implementation choice，不是永久 transport contract。后续如果引入 ASGI / WSGI / framework / hosted deployment，应先写独立 design note 和 red tests，避免把 framework assumptions 泄漏进 kernel contract。

## 6. Implemented Slices

第一批 minimal surface boundary tests 已新增并通过：

```text
tests/isotope_kernel/test_http_api_boundary.py
```

覆盖点：

- `isotope_kernel.http_api` module / `create_http_app(...)` exists。
- `HttpApiApp` exposes only the minimal v0.2 route surface。
- API 不能直接改 projected state。
- `POST /runs/{run_id}/input` 后 event log / run state / artifact summary 与 in-process demo 等价。
- artifact summary endpoint 不返回 full content。
- memory query endpoint 不存在或返回 `not_enabled`。
- no auth / SSE / external ingestion endpoints。
- HTTP layer 不 import `x_agent.*`。
- HTTP layer 不读取 checkpoint state 作为 truth。

这些 tests 只锁 server-facing boundary，不引入 real LLM、auth、streaming、external ingestion、memory query engine 或 hosted deployment。

第二批 request validation boundary tests 已新增并通过：

```text
tests/isotope_kernel/test_http_api_request_validation.py
```

覆盖点：

- unsupported route returns controlled `404` without events。
- known path with method mismatch returns controlled `405` without events。
- malformed / missing request body returns controlled `400` without events。
- unknown session / run / artifact returns controlled `404` without creating run state, action events, or artifacts。
- `POST /runs/{run_id}/input` requires non-empty string `text` and does not implicitly `str(...)`-coerce invalid values。
- invalid requests do not produce action lifecycle events or artifact side effects。
- deferred memory query / external ingestion / SSE / full artifact content routes remain absent / not enabled。

## 7. Still Deferred

- real listening HTTP server / hosted deployment
- FastAPI / Flask / ASGI / WSGI framework commitment
- auth / multi-user
- SSE / streaming
- approval API
- memory query API
- external ingestion API
- full artifact content API
- checkpoint inspection API
- plugin / dynamic tool registration API
