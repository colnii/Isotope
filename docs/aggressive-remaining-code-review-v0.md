# Aggressive Remaining Code Review v0

状态：`review complete / extract-only`

本文 review `origin/spike/aggressive-dev` 相对当前 `main` 仍未合入的代码。结论是：剩余 aggressive 代码有产品方向价值，但整体代码质量和分支形态不适合直接 merge；后续只能按小 slice 抽取。

## 1. Branch-Level Finding

`origin/spike/aggressive-dev` 当前不是一个可直接 fast-forward / squash merge 的干净功能分支。

主要原因：

- 它相对当前 `main` 会删除大量已经合入并验证过的 mainline 文件，例如 controlled terminal、LLM provider route、Agent loop control / step driver、Capability Catalog core 等。
- 它把 application shell、diagnostics、study companion、LLM direct calls、self-evolution harness 和 pressure tests 混在同一个大快照里。
- 它的 docs / tests 也带有 aggressive 分支内部状态，不是当前 main 的 source of truth。

因此后续策略应是：

- 不整体 merge。
- 不复制大文件。
- 只抽取可以独立测试、能嵌入当前 main 边界的小功能。

## 2. What Was Already Extracted

当前已从相关分支抽取 / 合入的能力：

- Controlled terminal / provider integration：来自 `feature/controlled-terminal-exec`，已合入 main。
- `DeepSeekChatProvider`：从 aggressive provider idea 中抽成最小 direct-chat wrapper，已合入 main。
- Capability Hub Core：已提前抽成 `isotope_kernel.capability_catalog`，只保留 metadata / shelf / manifest / readiness，不执行能力。

这些抽取都刻意避免了 aggressive 里的 product shell / self-evolution / workflow 大包。

## 3. Main Code Quality Findings

### 3.1 `capability_hub.py`

Aggressive branch 的 `src/isotope_kernel/capability_hub.py` 当前约一万行，里面同时包含：

- capability metadata
- capability execution runner
- CLI parsing
- study companion deterministic slices
- worker handoff pressure tests
- terminal task facade
- LLM chat / artifact review runner
- capability collection runbook
- output hygiene / contract diagnostics
- trace formatting

这说明它证明了一个重要方向：Isotope 需要一个 application-layer capability surface，让 UI / bot / desktop shell 能发现、检查、运行能力。

但它不适合直接合入：

- 单文件职责过多，后续维护成本很高。
- capability registry 和 capability execution 混在一起，容易把“货架”和“执行器”重新搅在一起。
- 许多 capability 是 pressure test / diagnostic，不是 product-ready capability。
- 大量测试是在锁 capability id 清单，而不是锁模块边界；后续新增 / 下架能力会很痛。
- 它会绕开当前 main 已经建立的 `capability_catalog` shelf discipline。

可保留的思路：

- capability manifest + readiness check。
- `status` 命令先检查 env / dependency，不直接构造 provider。
- capability runbook 可以作为 application shell 的组合层，不应成为 kernel workflow engine。

建议抽取方式：

- 先不要合 `capability_hub.py`。
- 下一步如果要做，应做 `Capability Runner Thin Shell`：只支持 2-3 个 main 已有 product-candidate capability，并且复用 `capability_catalog`，不要重新建一个大 hub。

### 3.2 DeepSeek Provider

Aggressive 的 `llm.chat` / `llm.artifact.review` 思路是：真实 DeepSeek 调用后，把模型输出写成 artifact，并保留 replay / checkpoint。

这条方向有价值，但 aggressive 里的实现和 capability hub 绑得太紧。

当前 main 已抽取最安全的一层：

- `DeepSeekChatProvider`
- fake transport tests
- no tool execution
- no event writes
- no product shell

后续如果继续做 real LLM capability，应基于当前 main 的 `DeepSeekChatProvider` 和 existing action / artifact path 重新写小 slice，而不是复制 aggressive 的 `llm.chat` runner。

### 3.3 `terminal.task.facade`

Aggressive 里的 terminal task facade 把用户任务文本变成几个 artifact：

- task request
- dry-run task plan
- approval boundary
- verification plan

这个思路像一个 task intake / preflight capability：先把任务变成可审查计划，不直接执行。

但当前 main 已经有更真实的 controlled `terminal_exec` 和 LLM terminal-tool loop；直接合 old facade 价值有限。

可保留的思路：

- 用户输入先落 artifact。
- 计划 / boundary / verification 都以 `ResourceRef` 形式流转。
- 默认 dry-run，不执行 shell / process / git。

建议后续改写为 `Task Intake Capability`，而不是直接复制 aggressive facade。

### 3.4 `self_evolution.py`

Aggressive 的 `self_evolution.py` 不是“AI 自己改代码并成长”。

它实际是一个 deterministic review harness：

- 生成 change plan。
- 生成 patch plan。
- 生成 safety review。
- 生成 review package artifacts。
- promotion 仍要求 human review。

这个方向适合以后做“自我修改前的变更计划 / 审查包”，但现在不适合合入：

- 它名字容易过度承诺。
- 它还没有接真实代码修改、真实 diff、真实 review gate。
- 它依赖 app-shell 语义，不能放进 kernel mainline 当成已实现 self-evolution。

建议保留为未来 concept，不进入当前 main。

### 3.5 Study Companion Slices

Aggressive 里有大量 study companion deterministic slices。它们有产品方向价值，但属于 domain app layer，不是当前 kernel / capability core。

当前不建议合入：

- 内容偏硬编码模板。
- 会扩大产品范围。
- 容易把 Isotope 误导成单一学习助手，而不是通用中台。

可以等 application layer 分支明确产品形态后再处理。

## 4. Recommended Next Slice

如果继续从 aggressive 中抽取，推荐下一步不是再合大块，而是做：

`Capability Runner Thin Shell`

目标：

- 基于当前 main 的 `capability_catalog`。
- 只支持少量 product-candidate capability，例如：
  - `artifact.review`
  - `external.snapshot.review`
  - `approval.tool.runner`
- 提供最小 `list / describe / status / run` shell。
- `run` 只调用现有 public helpers / demo runner，不新增 workflow engine。
- diagnostics / study companion / self-evolution / LLM real runner 先不进。

为什么选它：

- 它承接用户想要的“中台能力层”。
- 它能验证 UI / bot / desktop shell 未来如何发现和运行能力。
- 它比直接做 product shell 更小、更稳。
- 它不会破坏 kernel mainline。

## 5. Explicit Non-Goals

下一步不做：

- wholesale merge aggressive branch
- copy `capability_hub.py`
- copy `self_evolution.py`
- product chat shell
- QQ bot / desktop UI
- real workflow engine
- automatic self-evolution
- study companion productization
- new dependency
- tag / release

## 6. Review Conclusion

Aggressive 剩余代码不是“没用”，而是更像一堆 application-layer 试验田。

可合入 main 的不是这些大文件本身，而是其中被证明有价值的边界：

- capability manifest / readiness
- capability runner thin shell
- task intake as artifact-backed plan
- real LLM output as artifact-backed result
- self-evolution as review package, not autonomous mutation

当前最安全的下一步是先做 `Capability Runner Thin Shell` 的 docs-only boundary，再按 TDD 写 red tests。
