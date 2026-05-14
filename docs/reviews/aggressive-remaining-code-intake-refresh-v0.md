# Aggressive Remaining Code Intake Refresh v0

状态：`review complete / extract-only`

本文是在 `Capability Runner Thin Shell` 和 `Capability Runner CLI` 已合入 main 后，对 aggressive 剩余代码重新做的一次 intake review。目标不是继续把 aggressive branch 大块合并进来，而是判断剩余代码里哪些思路还值得切成 mainline 小片。

当前对比点：

- `origin/main`: `506efcd`
- `origin/codex/spike-aggressive-dev`: `432f941`
- `origin/spike/aggressive-dev`: `18cd7df`

## 1. 结论

aggressive 剩余代码仍然不能 wholesale merge。

外行说法：aggressive 里像一个“实验室大杂烩”，里面确实有好想法，但很多东西混在一起。mainline 现在已经把其中最稳的几块抽出来了：能力目录、薄 runner、CLI、provider wrapper、terminal / model-tool bridge。剩下的不能直接搬，要继续按“小零件”拆。

下一步最推荐的 extract-only slice 是：

`Capability Search / Launch Plan Boundary`

它解决的问题是：现在 mainline 已经有能力货架和最小 CLI，但用户或应用层还缺一个“先问清楚能不能跑、要准备什么、会不会触碰敏感能力”的 preflight（预检查）层。

不要下一步直接做：

- aggressive `capability_hub.py` wholesale copy
- aggressive `ask` / `interactive`
- aggressive workflow engine
- product shell
- study companion productization
- autonomous self-evolution

## 2. 已经吸收的 aggressive 价值

这些不需要重复搬：

- Capability metadata / shelf / manifest：已抽成 `isotope_kernel.capability_catalog`。
- Deterministic capability runner：已抽成 `isotope_kernel.capability_runner`。
- CLI `list / describe / status / run`：已实现为 `python -m isotope_kernel.capability_runner`。
- CLI `search / plan`：已抽成低敏查询和运行前计划，不执行 capability。
- DeepSeek direct chat wrapper：mainline 已有更完整的 `llm_provider.py`，aggressive 旧 wrapper 已被 superseded。
- Controlled terminal / model-tool bridge / LLM provider routes：已从 terminal/provider integration 分支合入 mainline。

## 3. 剩余代码分类

### 3.1 `capability_hub.py`

仍然是最大剩余块，也是最不能直接合入的一块。

它包含很多方向：

- capability search / route / plan
- ask / interactive
- diagnostics
- study companion
- provider-backed runner
- output hygiene checks
- product shell behavior

其中最值得先抽的是 search / launch plan 思路，不是整个 hub。

原因：

- search / plan 是能力中台的基础入口。
- 它可以保持 deterministic / no provider。
- 它不会把 LLM router、workflow engine、product shell 绑死。
- 后续 LLM router 可以替换“怎么选能力”，但仍复用同一个 launch plan output shape。

### 3.2 `self_evolution.py`

仍然不建议直接合入。

它实际不是“AI 自己改代码并成长”，而是 deterministic review package harness：生成 change plan / patch plan / safety review / promotion dry run，然后等人审。

这个方向有价值，但 mainline 目前缺底层组件：

- patch / diff application boundary
- branch / worktree / rollback boundary
- CI gate / promotion gate
- code review package schema
- safe write sandbox

因此它可以作为后续 `Change Review Package Boundary` 的输入材料，但现在不能叫 self-evolution，也不能直接进 mainline runtime。

### 3.3 Provider-backed capability runner

方向有价值，但不应作为下一步。

mainline 已有 `DeepSeekChatProvider` 和 LLM tool-call/provider routes。真正缺的不是“怎么调模型”，而是 capability-level preflight：

- 这个 capability 是否需要 provider？
- provider env 是否存在？
- 运行会不会写 artifact？
- 失败时如何返回 low-sensitive error？
- JSON / trace 如何保持低敏？

所以 provider-backed runner 应排在 launch plan / preflight 之后。

### 3.4 Study companion / personal assistant slices

继续留在 application-layer experiment。

它们可以未来变成能力包，但不能现在混进 kernel / mainline core。否则 Isotope 会被误导成单一学习助手，而不是通用中台。

### 3.5 Diagnostics / pressure tests

这些价值主要是暴露 friction，而不是成为产品功能。

如果 aggressive 后续给出新的 concrete `kernel_friction`，可以继续按 mainline queue 消化。但不要把 diagnostics capability 全部上架。

## 4. Recommended Next Slice

推荐下一步：

`Capability Search / Launch Plan Boundary`

最小目标：

- 继续复用 `CapabilityCatalog` 作为 source of truth。
- 给 `CapabilityRunner` 增加 search / preflight 或 launch plan helper。
- CLI 已增加低敏 `search` / `plan`，但不执行能力。
- Launch plan 只回答：
  - 找到哪些候选 capability。
  - 该 capability 当前能不能 run。
  - 缺哪些输入 / env / grant / provider。
  - 它会走 deterministic runner、provider runner，还是 deferred。
  - 它会不会返回 artifact full content。
- 不用 LLM，不调用 provider，不做 workflow engine。

外行说法：先做“开能力前的安全说明书”，不是直接让 AI 自动干活。

## 5. 为什么这不阻碍未来 LLM Router

这一步不是长期用 rule matching 取代 LLM router。

它只固定 output contract：

- 搜索 / 选择可以先 deterministic。
- 未来 LLM router 也必须输出同样的 launch plan。
- runner 只相信 launch plan + catalog + allowlist，不盲信 LLM 原话。

也就是说，当前 deterministic search 是临时选择器；launch plan 是长期接口。

## 6. Explicit Non-Goals

下一步不做：

- copy aggressive `capability_hub.py`
- `ask`
- `interactive`
- workflow engine
- autonomous self-evolution
- provider-backed capability execution
- study companion productization
- product shell
- QQ bot / desktop shell
- real HTTP server
- real filesystem / container / git worktree
- new dependency
- tag / release

## 7. Stop Condition

如果下一步实现中发现：

- 需要真实 LLM router 才能完成；
- 需要 provider-backed execution；
- 需要新增依赖；
- 需要复制 aggressive hub；
- 需要把 diagnostics / test capabilities 上架成 product capabilities；

就应停止，不继续 green。
