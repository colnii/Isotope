# Capability Runner CLI Boundary v0.2

状态：`first slice implemented`

## 1. 结论

这是从 aggressive branch 剩余 `capability_hub.py` 里抽出的一个小片：不是把大 hub 合进 main，而是给 mainline 已有的 `CapabilityRunner` 加一个最小命令行入口。

外行说法：之前 mainline 已经有“能力试跑按钮”的 Python API，但普通人还不能直接在终端敲命令用它。现在可以用 `isotope-capability` 或 `python -m isotope.capabilities.runner` 做最小的 `list / describe / status / search / plan / run`。

## 2. 当前支持

支持：

```bash
PYTHONPATH=src .venv/bin/python -m isotope.capabilities.runner list --json
PYTHONPATH=src .venv/bin/python -m isotope.capabilities.runner describe artifact.review --json
PYTHONPATH=src .venv/bin/python -m isotope.capabilities.runner status artifact.review --json
PYTHONPATH=src .venv/bin/python -m isotope.capabilities.runner search worker-review --json
PYTHONPATH=src .venv/bin/python -m isotope.capabilities.runner search integration-review --json
PYTHONPATH=src .venv/bin/python -m isotope.capabilities.runner plan supervisor.worker_review --input-json '{"codex_home":"/home/lumber/.codex"}' --json
PYTHONPATH=src .venv/bin/python -m isotope.capabilities.runner run supervisor.worker_review --input-json '{"codex_home":"/home/lumber/.codex"}' --json
PYTHONPATH=src .venv/bin/python -m isotope.capabilities.runner plan supervisor.integration_review --input-json '{"codex_home":"/home/lumber/.codex"}' --json
PYTHONPATH=src .venv/bin/python -m isotope.capabilities.runner run supervisor.integration_review --input-json '{"codex_home":"/home/lumber/.codex"}' --json
```

当前 CLI 仍只复用 `CapabilityRunner` 的小 allowlist：

- `artifact.review`
- `external.snapshot.review`
- `approval.tool.runner`
- `supervisor.integration_review`
- `supervisor.request_context`
- `supervisor.worker_review`

## 3. 边界

CLI 只做一层薄包装：

- catalog 仍是 source of truth。
- runner allowlist 仍控制哪些能力能 run。
- unknown capability 会在 side effect 前 fail closed。
- JSON output 是低敏 summary。
- `supervisor.worker_review` 强制走 lightweight worker review，只返回压缩决策摘要。
- `supervisor.integration_review` 默认关闭 test gate 和候选 validation，只返回压缩分组摘要。
- 不返回 raw input、prompt、trace、artifact full content、API key 或 provider raw response。

明确不做：

- 不复制 aggressive `capability_hub.py`。
- 不实现 `ask` / `interactive`。
- 不实现 workflow engine / runbook engine。
- 不上架 aggressive 的 49 个能力全集。
- 不构造 real provider。
- 不新增 real HTTP server / product shell / QQ bot / desktop shell。

## 4. 为什么现在做 CLI

之前 closure review 说“不要默认继续扩 CLI”，是因为当时没有明确调用压力。现在用户明确要求继续消化 aggressive 分支里没被利用的代码，CLI 是最小、低风险、可维护的第一块：

- aggressive 里有大量 CLI 想法；
- mainline 已经有安全的 `CapabilityRunner`；
- CLI 能让这些能力真的被人从终端调用；
- 又不会把 aggressive 的 god module 带进 main。

## 5. First Slice Evidence

实现文件：

- `src/isotope/capabilities/runner.py`
- `src/isotope/capabilities/runner_cli.py`
- `src/isotope/capabilities/supervisor.py`
- `tests/integration/capability/test_capability_runner_cli.py`

验证目标：

- targeted runner tests pass。
- full regression pass。
- `/home/lumber/Github/x-agent` untouched。
- no `x_agent.*` import。
