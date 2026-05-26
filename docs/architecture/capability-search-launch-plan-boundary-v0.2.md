# Capability Search / Launch Plan Boundary v0.2

状态：`first slice implemented`

## 1. 结论

这是 `Capability Runner CLI` 之后的下一块 extract-only slice。它不是把 aggressive `capability_hub.py` 合进 main，而是从里面抽一个更小、更长期的接口：`Capability Search / Launch Plan`。

外行说法：现在 Isotope 已经有一个小“能力货架”，也能手动运行 3 个安全能力。下一步不是直接让 AI 自动乱跑，而是先给每个能力加一张“运行前说明书”：这个能力能不能跑、为什么不能跑、缺什么配置、会不会调用 provider、会不会暴露敏感内容、如果要跑应走哪个 runner。

## 2. 为什么先做这个

aggressive branch 里有很多 search / route / ask / interactive / workflow 想法。直接合并会重新变成大杂烩。

`LaunchPlan` 是更稳的底层接口，因为：

- deterministic search 可以先用 catalog metadata 实现。
- 未来 LLM router 也可以复用同一个 output shape。
- runner 在执行前只信任 launch plan + catalog + allowlist，不盲信 LLM 原话。
- provider-backed capability、workflow engine、product shell 都可以以后接在这个 plan 后面，不需要现在打开。

## 3. Scope

第一批只定义和后续实现以下概念：

- `search_capabilities(...)`: 在 `CapabilityCatalog` 里做低敏搜索。
- `plan_capability_run(...)`: 对一个 capability 生成低敏 launch plan。
- optional CLI:
  - `isotope-capability search ...`
  - `isotope-capability plan ...`
  - `python -m isotope.capabilities.runner search ...`
  - `python -m isotope.capabilities.runner plan ...`

第一批不执行 capability；后续 `supervisor.request_context` 和
`supervisor.worker_review` 已作为受限只读 capability 接入 `run`。

## 4. Search Boundary

Search 是 catalog-level helper，不是 LLM router。

允许：

- 使用 `capability_id`、`title`、`description`、`domain_tags`、`shelf` 做 deterministic match。
- 支持 `shelf` / `include_diagnostics` / `include_experimental` 过滤。
- 返回 low-sensitive result：id、title、description、shelf、domain_tags、readiness summary。

不允许：

- 调用 LLM。
- 调用 provider。
- 执行 capability。
- append canonical events。
- 创建 session / run / action / artifact。
- 读取 artifact full content。
- 返回 prompt / transcript / API key / local path / raw provider response。

## 5. Launch Plan Boundary

Launch plan 是运行前 preflight（预检查）结果。它回答“如果我要运行这个能力，当前是否安全且可用”。

建议最小 shape：

```json
{
  "kind": "capability_launch_plan",
  "capability_id": "artifact.review",
  "capability_title": "Artifact Review",
  "can_launch": true,
  "status": "launchable",
  "runner_kind": "deterministic_demo",
  "scenario": "artifact-review",
  "blocking_reasons": [],
  "required_inputs": [],
  "missing_inputs": [],
  "required_env": [],
  "missing_env": [],
  "network_required": false,
  "provider": null,
  "model": null,
  "shelf": "product_candidate",
  "safety_boundaries": ["low_sensitive_manifest_only", "no_full_content"],
  "output_policy": {
    "returns_full_content": false,
    "returns_artifact_refs": true,
    "low_sensitive_summary_only": true
  }
}
```

Allowed statuses:

- `launchable`: 当前 runner allowlist 支持，readiness ready，可执行。
- `not_ready`: catalog 存在，但缺 env / disabled / missing input。
- `deferred`: catalog 存在，但当前 mainline 不支持对应 runner。
- `not_allowlisted`: catalog 存在且 ready，但 runner 暂不允许执行。
- `unknown`: capability id 不存在。

第一批 plan 只描述，不执行。

## 6. Relationship To LLM Router

LLM router 不是第一批目标。

未来接 LLM router 时，LLM 可以帮助从自然语言里推荐 capability，但不能直接执行。推荐流程应是：

1. LLM 或 deterministic search 产出 candidate capability id。
2. 系统调用 `plan_capability_run(...)`。
3. 只有 plan 是 `launchable`，runner 才能执行。

这样 deterministic search 不会阻碍 LLM router；它只是当前的候选生成方式。长期稳定的是 `LaunchPlan` contract。

## 7. Relationship To Provider-Backed Runner

Provider-backed runner 排在 launch plan 之后。

如果 capability 需要 DeepSeek / OpenAI / other provider，第一批 plan 可以显示：

- `network_required=true`
- `provider=...`
- `model=...`
- `missing_env=[...]`
- `status=not_ready` 或 `deferred`

但不得构造 provider，也不得发起真实网络请求。

## 8. No-Side-Effect Rule

Search / plan 必须是 no-side-effect。

失败或成功都不得：

- 创建 session / run / action / artifact。
- append event。
- 调用 provider。
- 运行 terminal。
- 读取 workspace filesystem。
- 修改 checkpoint / event store。

## 9. First Red Tests

建议下一批 red tests：

`tests/isotope/test_capability_search_launch_plan.py`

覆盖：

- `CapabilityRunner.search_capabilities(query="artifact")` 返回 `artifact.review`。
- search result 只包含 low-sensitive metadata。
- search 不产生 side effects。
- search 支持 shelf / diagnostics / experimental filters。
- `CapabilityRunner.plan_capability_run("artifact.review")` 返回 `launchable` plan。
- `plan_capability_run("external.snapshot.review")` 返回 deterministic scenario plan。
- `plan_capability_run("unknown.capability")` 返回 controlled unknown plan 或 controlled error，且无 side effect。
- provider-required capability 只返回 `not_ready` / `deferred` plan，不构造 provider。
- diagnostic / experimental capability 默认返回 `deferred` / `not_allowlisted`，不执行。
- plan output 不包含 full content / prompt / transcript / API key / local path。

Optional CLI tests：

`tests/isotope/test_capability_runner_cli_search_plan.py`

- `search --json` returns machine-readable search results。
- `plan artifact.review --json` returns launch plan。
- CLI error output remains stable and low-sensitive。

## 10. Deferred

继续 deferred：

- LLM router。
- provider-backed capability execution。
- `ask`。
- `interactive`。
- workflow engine / runbook engine。
- product capability hub。
- study companion productization。
- autonomous self-evolution。
- real HTTP server。
- QQ bot / desktop shell。
- filesystem / container / git worktree。
- new dependency。
- tag / release。

## 11. Acceptance

这个 boundary 完成后，下一步 implementation first slice 可以认为 complete 的条件：

- `CapabilityRunner` 或等价 helper 支持 deterministic search。
- `CapabilityRunner` 或等价 helper 支持 launch plan。
- CLI 可选支持 `search` / `plan`，但不作为第一批必须项。
- search / plan 都 no-side-effect。
- launch plan 不执行 capability。
- launch plan 对 allowlisted deterministic capability 给出 `launchable`。
- launch plan 对 provider-required / diagnostic / experimental / unallowlisted capability fail closed / deferred。
- full regression 通过。
- README / AGENTS / current status / queue 同步。

## 12. First Green Slice Evidence

已实现：

- `CapabilityRunner.search_capabilities(...)`
- module-level `search_capabilities(...)`
- `CapabilityRunner.plan_capability_run(...)`
- module-level `plan_capability_run(...)`
- CLI `search`
- CLI `plan`
- tests: `tests/isotope/test_capability_search_launch_plan.py`
- tests: `tests/isotope/test_capability_runner_cli.py`

当前 first slice 支持：

- deterministic catalog metadata search。
- low-sensitive search result。
- no-side-effect launch plan。
- allowlisted deterministic capability 返回 `launchable`。
- unknown capability 返回 controlled `unknown` plan。
- provider-required capability 只返回 `not_ready` / missing env，不构造 provider。
- diagnostic / experimental capability 默认不可 launch。

当前未实现：

- LLM router。
- provider-backed capability runner。
- `ask` / `interactive`。
- workflow engine。
- product shell。
