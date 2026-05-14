# Capability Runner Thin Shell Closure Review

状态：`closed for now`

## 1. 结论

`Capability Runner Thin Shell` first slice 可以标为 `complete / closed for now`。

外行说法：现在 mainline 里已经有一个很薄的“能力试跑按钮”。它不是完整中台，也不是产品壳；它只是让应用层可以从现有 capability catalog（能力货架）里挑少数已允许的能力，安全地跑一个 deterministic in-process scenario。

当时不建议默认继续做 CLI / product hub / workflow engine。原因是这一步的目标已经达成：证明“货架”和“执行按钮”可以分开，而且不会把 aggressive branch 里的大杂烩 `capability_hub.py` 搬进 main。

后续用户明确要求继续消化 aggressive 分支里尚未利用的代码后，CLI 已作为单独 first slice 抽取，见 `../architecture/capability-runner-cli-boundary-v0.2.md`。这不改变本 closure 的主结论：仍不整体合并 aggressive hub，也不打开 product hub / workflow engine。

## 2. 已证明什么

已证明：

- catalog 仍是 metadata source of truth。
- runner 不维护第二套 registry。
- runner 可以 `list / describe / status / run`。
- runner 只 allowlist 三个 product-candidate capabilities：
  - `artifact.review`
  - `external.snapshot.review`
  - `approval.tool.runner`
- `run` 复用已有 deterministic demo scenario，不新增 workflow language。
- unknown capability 在 side effect 前 fail closed。
- diagnostic / experimental capability 默认不能 run。
- provider-required capability 在缺少配置时 fail closed，且不构造 provider。
- unallowlisted but ready 的 capability 也 fail closed。
- result 是 low-sensitive summary，不返回 artifact full content / prompt / raw input。

## 3. 没有做什么

没有实现：

- CLI。
- product capability hub。
- `ask` / `interactive`。
- study companion product surface。
- self-evolution harness。
- real LLM capability runner。
- provider router。
- workflow engine / runbook engine。
- product UI / QQ bot / desktop shell。
- dynamic plugin loading。
- remote capability registry。
- new dependency。
- tag / release。

这些都不是本 slice 的 blocker。

## 4. 为什么当时不默认扩 CLI

CLI 是有价值的，但在没有明确调用压力时不是最优下一步。

原因：

- 当前 runner 已经提供 Python API，可被应用层或后续 shell 调用。
- CLI 会开始引入 output contract、参数设计、help text、error UX、可能还会诱导 product-shell 设计。
- 目前还没有第二个真实调用者证明 CLI 是 blocker。
- 继续做 CLI 容易把薄壳重新推向 aggressive `capability_hub.py` 的方向。

因此 CLI 当时被保留为 later / app-pressure driven，而不是默认继续。当前 CLI first slice 是在用户明确要求继续做 aggressive 剩余代码 intake 后，以独立边界实现的。

## 5. Remaining Friction

剩余 friction：

- `run_capability(...)` 目前内部复用 demo scenarios，而不是更正式的 app-layer capability implementation module。
- 输出是 summary，不是完整 product result object。
- 没有 CLI。
- 没有 HTTP facade route。
- 没有真实 provider-backed capability。
- 没有用户级 capability permission / profile / favorites。

这些是 application-layer / product-shell pressure，不是当前 kernel blocker。

## 6. Recommended Next Path

推荐下一步回到 application-layer friction intake。

可选路径：

1. 如果应用层马上要用 capability runner：先在应用层调用 Python API，记录真实 friction。
2. 如果需要命令行：再开 `Capability Runner CLI Boundary`，先 docs-only，再 TDD。
3. 如果要接 real LLM capability：单独开 `Provider-backed Capability Runner Boundary`，不要塞进当前 thin shell。
4. 如果要做中台 UI / bot / desktop shell：在应用层分支设计 product shell，不在 kernel mainline 里直接扩 hub。

默认不要继续添加 capability ids，也不要复制 aggressive branch 的 `capability_hub.py`。

## 7. Verification Evidence

最近一次 green slice 验证：

- `tests/isotope_kernel/test_capability_runner_thin_shell.py` -> `12 passed`
- latest post-CLI full regression -> `1379 passed, 5 skipped`
- `artifact-review --trace` passed
- `external-snapshot-review --trace` passed
- `approval-tool-runner --trace` passed
- GitHub Actions run `25866071229` passed

本 closure review 不修改 `src/` / `tests`。
