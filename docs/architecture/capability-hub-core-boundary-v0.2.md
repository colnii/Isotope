# Capability Hub Core Boundary v0.2

状态：`first slice complete / closed for now`

## 1. 背景

`codex/spike-aggressive-dev` 已经验证了 application-layer Capability Hub 的价值：能力可以被发现、搜索、预检、路由、运行，并且可以通过 shelf（货架）区分 product candidate、prototype、diagnostic 和 experimental。

但 aggressive branch 当前不是 mainline-ready 形态。它把 catalog、routing、LLM routing、launch plan、ask、interactive、capability implementations、diagnostics、study companion slices、self-evolution harness 和 provider experiment 放在同一个大模块里。该形态适合试验，不适合整体进入 `main`。

本 boundary 的目标是定义一个可从 aggressive branch 抽取进 mainline 的最小 `Capability Hub Core`，让 mainline 获得稳定的能力目录骨架，而不接收应用层试验场的全部内容。

## 2. 目标

Capability Hub Core 的目标是提供一个小而稳定的 ability catalog（能力目录）基础层：

- 记录 capability metadata。
- 区分 user-facing / prototype / diagnostic / experimental shelf。
- 默认只暴露接近用户可用的能力。
- 给 app shell / UI / bot / desktop shell 提供低敏 manifest。
- 给后续 application-layer prototype 一个稳定的 catalog contract。

它不是 workflow engine，也不是 product app shell。

## 3. Mainline 接收范围

第一批 mainline slice 只接收：

- `Capability` metadata model。
- `CapabilityShelf` / shelf validation。
- `CapabilityCatalog` 或等价小模块。
- `list_capabilities(...)`。
- `get_manifest(...)`。
- `get_capability_status(...)`。
- optional simple `search_capabilities(...)`，只做 metadata / tag / text search，不做 LLM route。
- 少量 built-in capability registration。

建议模块名：

- `src/isotope/capability_catalog.py`

建议测试：

- `tests/isotope/test_capability_catalog_core.py`
- `tests/isotope/test_capability_catalog_shelves.py`

## 4. Capability metadata

第一批 `Capability` 至少包含：

- `capability_id`
- `title`
- `description`
- `maturity`
- `shelf`
- `domain_tags`
- `input_contract`
- `output_contract`
- `safety_boundaries`
- `default_enabled`

metadata 必须满足：

- `capability_id` 唯一。
- `capability_id` 是稳定 identifier，不使用展示标题当 id。
- `shelf` 必须是已知值。
- `input_contract` / `output_contract` 只描述 shape，不包含真实用户输入、prompt、trace 或 artifact full content。
- `safety_boundaries` 是低敏摘要，不泄露 API key、local path、transcript 或 raw content。

## 5. Shelf 规则

允许的 shelf：

- `product_candidate`: 接近用户可用，可以默认展示。
- `prototype`: 可运行原型，可以默认展示，但不能宣称成熟产品能力。
- `diagnostic`: 开发验证 / pressure test，默认隐藏。
- `experimental`: 高风险或不稳定实验，默认隐藏，必须显式 opt-in。

默认可见规则：

- default list / manifest 只显示 `product_candidate` 和 `prototype`。
- `diagnostic` 需要显式 `include_diagnostics=True`。
- `experimental` 需要显式 `include_experimental=True`。
- `shelf="diagnostic"` 可以只看 diagnostic。
- `shelf="experimental"` 仍需要 experimental opt-in。

这些规则的目的不是隐藏代码，而是避免用户和维护者把 review / pressure-test capability 当成产品能力。

## 6. Minimal built-in capabilities

第一批 mainline built-ins 建议只包含三类已经在 kernel demos 中稳定存在的 product candidates：

- `artifact.review`
- `external.snapshot.review`
- `approval.tool.runner`

这些 entries 只是 metadata / manifest entries，不要求第一批实现 `run capability`。

暂不默认注册：

- study companion slices
- worker handoff diagnostics
- capability collection runbooks
- self-evolution review
- `llm.chat`
- `llm.artifact.review`

其中 `llm.chat` / `llm.artifact.review` 可以之后作为 provider-aware application capability 单独设计，不能混入第一批 core extraction。

## 7. Status / readiness

`get_capability_status(...)` 第一批只做本地 readiness：

- 是否 default enabled。
- 是否需要 env vars。
- 是否缺少 required env vars。
- 是否 network-required。
- provider / model 只作为 metadata 输出。

它不得：

- 构造真实 provider。
- 发起网络请求。
- 调用 LLM。
- 读取 artifact full content。
- 执行 capability。

## 8. Manifest contract

`get_manifest(...)` 返回低敏 JSON-compatible dict：

- `kind: "capability_manifest"`
- `capabilities: [...]`
- 每个 capability 包含 metadata。
- 每个 capability 可包含 readiness summary。

manifest 不得包含：

- raw user input
- prompt
- transcript
- API key
- local absolute paths
- artifact full content
- run trace
- capability execution result

## 9. Deferred

以下内容继续留在 aggressive branch 或后续单独设计：

- 49 个 aggressive capabilities 全量进入 main。
- diagnostic / review / pressure-test capability 默认进入用户 catalog。
- `ask` product entry。
- `interactive` REPL。
- LLM route / LLM route-plan / LLM diagnose route。
- DeepSeek provider implementation。
- real provider adapter。
- self-evolution harness。
- study companion product surface。
- workflow engine。
- product UI / QQ bot / desktop shell。
- hosted HTTP route。
- dynamic plugin loading。
- remote capability registry。
- marketplace / domain pack system。

## 10. First red tests

下一批 implementation 应先写 red tests：

`tests/isotope/test_capability_catalog_core.py`

- module `isotope.capability_catalog` exists。
- `Capability` can serialize to low-sensitive dict。
- duplicate `capability_id` fails fast。
- malformed capability id / unknown shelf fails fast。
- manifest returns JSON-compatible metadata and readiness only。
- manifest does not include raw content / trace / prompt fields。

`tests/isotope/test_capability_catalog_shelves.py`

- default catalog only includes `product_candidate` and `prototype`。
- `diagnostic` hidden by default。
- `experimental` hidden by default。
- `include_diagnostics=True` exposes diagnostics。
- `include_experimental=True` exposes experimental only when explicit。
- filtering by shelf is stable and deterministic。

可选后续：

`tests/isotope/test_capability_catalog_search.py`

- simple query / tag search works without LLM。
- search does not execute capability。
- search does not construct provider or perform network calls。

## 11. Merge rule

Do not copy `src/isotope/capability_hub.py` wholesale from aggressive branch.

Mainline implementation must be a small extraction from the idea, not a direct transplant of the aggressive module.

## 12. First green slice evidence

已实现：

- `src/isotope/capability_catalog.py`
- `tests/isotope/test_capability_catalog_core.py`
- `tests/isotope/test_capability_catalog_shelves.py`

当前 first slice 只提供：

- `Capability` metadata model。
- `CapabilityCatalog`。
- `list_capabilities(...)`。
- `get_manifest(...)`。
- `get_capability_status(...)`。
- module-level default catalog helpers。
- 三个 product-candidate built-ins：`artifact.review`、`external.snapshot.review`、`approval.tool.runner`。

验证：

- red：`19 failed`，失败集中在缺少 `isotope.capability_catalog`。
- green：targeted `19 passed`。
- full regression：`1083 passed`。

边界保持：

- 没有复制 aggressive `capability_hub.py`。
- 没有接收 aggressive 的 49 个 capabilities。
- 没有实现 capability execution。
- 没有实现 LLM route、provider construction、`ask`、`interactive`、diagnostics、self-evolution harness、workflow engine 或 product shell。
