# Capability Runner Thin Shell Boundary v0.2

状态：`first slice complete / closed for now`

## 1. 背景

`isotope_kernel.capability_catalog` 已经给 mainline 提供了一个小而稳定的 capability catalog（能力目录 / 货架）：它能列出能力、描述 shelf、输出低敏 manifest，并做本地 readiness summary。

但它刻意不执行能力。这个选择是对的，因为 aggressive branch 里的 `capability_hub.py` 已经证明：如果把 catalog、runner、CLI、diagnostics、LLM route、study companion、自我进化 harness 和 product shell 全塞进一个模块，短期看起来“功能很多”，长期会变成不可维护的大杂烩。

本 boundary 定义下一步可以合入 mainline 的最小能力执行壳：`Capability Runner Thin Shell`。它只把现有 catalog 上少数 product-candidate capability 接到已经存在的 public helpers / demo scenarios，不复制 aggressive hub。

## 2. 目标

Capability Runner Thin Shell 的目标是让未来 app shell / UI / bot / desktop shell 能做四件事：

- `list`: 看有哪些 capability。
- `describe`: 看某个 capability 的低敏说明。
- `status`: 看某个 capability 当前是否 ready。
- `run`: 对少数已验证 product-candidate capability 触发一个 deterministic in-process run。

它是 application-layer shell，不是 kernel workflow engine。

## 3. Mainline 接收范围

建议未来实现模块：

- `src/isotope_kernel/capability_runner.py`

第一批只允许复用当前 main 已有的 source of truth：

- `isotope_kernel.capability_catalog.default_catalog()`
- existing public `InProcessServer` helpers
- existing deterministic demo scenarios

第一批 `run` 只支持这些 already-registered product candidates：

- `artifact.review`
- `external.snapshot.review`
- `approval.tool.runner`

runner 返回值必须是 JSON-compatible low-sensitive summary。可以包含：

- `capability_id`
- `status`
- `scenario`
- `trace_steps` 或 `summary`
- `resource_refs`
- `replay_ok`
- `checkpoint_ok`
- `deferred_capabilities`

不得包含：

- raw user input
- prompt
- transcript
- API key
- local absolute path
- artifact full content
- provider raw response
- hidden run events that bypass read-model summaries

## 4. Runner / Catalog Boundary

Catalog 是“货架”，runner 是“从货架拿一个已允许能力去运行”的薄壳。

规则：

- runner 不维护第二套 capability registry。
- runner 不注册 capability metadata。
- runner 不改变 shelf / readiness / status 规则。
- runner 必须先从 `CapabilityCatalog` 读取 capability 并验证 shelf / readiness。
- runner 只能执行 explicit allowlist 中的 capability。
- unsupported capability id 必须 fail closed。
- diagnostic / experimental capability 默认不能 run。
- 需要 provider / network 的 capability 在第一批不能 run，即使 catalog metadata 存在。

这个边界的目的，是防止 aggressive `capability_hub.py` 那种“货架和执行器重新搅在一起”的形态进入 mainline。

## 5. Execution Boundary

第一批 `run` 不是新的 workflow language。

允许：

- 调用现有 deterministic demo scenario 的内部组合路径。
- 调用现有 public helpers，例如 source artifact setup、approval lookup、workspace binding、external snapshot import。
- 返回低敏 summary / trace。

不允许：

- private `server._append(...)`。
- 新增 workflow engine。
- 新增 scheduler。
- 自动串联任意 capability。
- 构造 real LLM provider。
- 发起真实网络请求。
- 打开 real HTTP server。
- 创建 process supervisor / interactive shell。
- 读写真实 workspace filesystem。
- 新增 container / git worktree / remote executor。

如果某个 capability 需要上述能力，它应返回 `not_enabled` / `deferred`，而不是偷偷实现。

## 6. Error / No-Side-Effect Rules

runner 必须在产生 side effect 前完成 validation。

必须先验证：

- `capability_id` 是已知稳定 id。
- capability 存在于 catalog。
- shelf 允许被 run。
- capability readiness 为 ready。
- capability 在 runner allowlist 内。
- request body 是 expected shape。

失败时：

- 返回 stable error code / message。
- 不创建 session / run / action / artifact。
- 不构造 provider。
- 不读取 artifact full content。
- 不 append canonical event。

## 7. Relationship To Aggressive Branch

本 boundary 接收 aggressive branch 的一个思路：用户需要一个 capability surface，可以发现、检查和运行能力。

但明确不接收：

- `capability_hub.py` wholesale copy。
- `self_evolution.py`。
- `ask` / `interactive`。
- study companion slices。
- diagnostics / pressure-test capability 默认上架。
- capability collection runbook engine。
- LLM real runner。
- product shell。

aggressive branch 可以继续作为 application-layer 试验田；mainline 只抽取小而可维护的边界。

## 8. First Red Tests

建议下一批先写 red tests：

`tests/isotope_kernel/test_capability_runner_thin_shell.py`

- module `isotope_kernel.capability_runner` exists。
- runner uses `CapabilityCatalog` as source of truth。
- `list_capabilities(...)` mirrors catalog default list。
- `describe_capability(...)` returns low-sensitive metadata。
- `get_capability_status(...)` mirrors catalog status。
- `run_capability("artifact.review", ...)` returns deterministic low-sensitive summary。
- `run_capability("external.snapshot.review", ...)` returns deterministic low-sensitive summary。
- `run_capability("approval.tool.runner", ...)` returns deterministic low-sensitive summary。
- unknown capability id fails closed with no side effects。
- diagnostic / experimental capability fails closed by default。
- provider-required capability fails closed and does not construct provider。
- result does not expose artifact full content / prompt / raw input.

Optional later:

`tests/isotope_kernel/test_capability_runner_cli_boundary.py`

- CLI `list` / `describe` / `status` / `run` works if a CLI is introduced。
- CLI remains in-process and no-network。
- JSON output remains machine-readable。
- plain output remains human-readable。

CLI first slice 已在后续单独实现，见 `capability-runner-cli-boundary-v0.2.md` 和 `tests/isotope_kernel/test_capability_runner_cli.py`。

## 9. Deferred

继续 deferred：

- product capability hub。
- product UI / QQ bot / desktop shell。
- remote capability registry。
- dynamic plugin loading。
- marketplace / domain pack system。
- workflow engine / runbook engine。
- study companion product surface。
- self-evolution / autonomous framework mutation。
- real LLM capability runner。
- provider router。
- hosted HTTP route。
- streaming output。
- new dependency。
- tag / release。

## 10. Acceptance For First Slice

第一批实现可以被认为 complete 的条件：

- `CapabilityRunner` 或等价薄壳存在。
- catalog 仍是 metadata source of truth。
- runner 只支持 allowlisted product-candidate capability。
- `artifact.review` / `external.snapshot.review` / `approval.tool.runner` 至少一个或全部可以通过 runner deterministic 运行。
- unsupported / diagnostic / experimental / provider-required capability fail closed。
- full regression 通过。
- README / AGENTS / current status / queue 同步。

第一批不要求：

- real provider。
- product UI。
- shell / bot / desktop app。
- workflow engine。
- aggressive capability list 全量迁移。

## 11. First Green Slice Evidence

已实现：

- `src/isotope_kernel/capability_runner.py`
- `tests/isotope_kernel/test_capability_runner_thin_shell.py`

当前 first slice 提供：

- `CapabilityRunner`。
- module-level `list_capabilities(...)` / `describe_capability(...)` / `get_capability_status(...)` / `run_capability(...)`。
- catalog 仍是 capability metadata / shelf / readiness source of truth。
- `run_capability(...)` 只执行 allowlisted product-candidate capability：
  - `artifact.review` -> `artifact-review` deterministic scenario
  - `external.snapshot.review` -> `external-snapshot-review` deterministic scenario
  - `approval.tool.runner` -> `approval-tool-runner` deterministic scenario
- unknown / diagnostic / experimental / provider-required / unallowlisted capability 在产生 side effect 前 fail closed。
- result 只返回 low-sensitive summary，不返回 artifact full content / prompt / raw input。

仍未实现：

- CLI。
- product capability hub。
- real provider runner。
- workflow engine。
- study companion / self-evolution / product shell。
