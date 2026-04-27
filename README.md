# Isotope

Isotope 是一个独立的 kernel-first agent runtime 项目。当前仓库用于沉淀最小 kernel slice：file event log、action chain、policy grants、artifact provenance、structured ResourceRef、projector replay 和 RunState rebuild。

当前代码来自 `x-agent` 中的 Isotope staging snapshot。`x-agent` 不是 Isotope 的 canonical repo，后续 Isotope 的设计和实现应以本仓库为准。

## Current Status

当前状态入口：[docs/current-status.md](docs/current-status.md)。

当前测试命令：

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope_kernel -q
```

当前预期：`29 passed`。

当前 deferred 边界：real LLM、memory write、external ingestion / `ImportedSnapshot`、checkpoint、SSE、multi-agent concurrency、real HTTP API。

## Current Slice

当前 slice 只验证最小闭环：

- compact intent 编译为 `ActionProposal` 后才能进入 policy。
- executor 只能使用 `PolicyDecision.grants`。
- file event log 使用 JSONL append-only。
- artifact 带 execution provenance。
- artifact identity 使用 structured `ResourceRef`。
- projector 只从 canonical events 重建 `RunState`。
- in-process server facade 只暴露当前 slice 的同步调用入口，不包含 real HTTP。

以下能力仍然 deferred：real LLM、memory write、external ingestion、checkpoint、SSE、multi-agent concurrency、real HTTP API。

## Verify

```bash
python -m venv .venv
.venv/bin/python -m pip install -U pip pytest
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope_kernel -q
```
