# 兼容代理审计

状态：`当前清单 / 第一轮显式测试导入已切换`

本文记录旧导入路径和兼容代理，不直接要求马上删除。
目标是先知道哪些文件只是旧入口，哪些还承担命令或兼容测试职责。

## 当前结论

- `from isotope.xxx import ...` 形式的显式测试导入已改用新路径。
- `from isotope import xxx` 形式的包级测试导入仍是下一批 blocker；
  当前测试中还有 126 处。
- `src/isotope/` 根目录仍保留很多兼容代理，方便旧代码导入。
- `core/` 和 `assistant/` 当前没有活跃实现，只保留 agent loop 旧入口。
- `capability_runner.py`、`demo.py`、`llm_live_smoke.py` 仍有命令入口价值。
- 删除代理前，需要先建立专门的兼容入口测试，再逐批移除。

## 可优先进入删除计划

这些路径已有新实现路径，且显式测试导入已迁走：

| 旧路径 | 新路径 |
| --- | --- |
| `isotope.server` | `isotope.runtime.in_process` |
| `isotope.http_api` | `isotope.interfaces.http` |
| `isotope.checkpoint_store` | `isotope.platform.state.checkpoint_store` |
| `isotope.event_store` | `isotope.platform.state.event_store` |
| `isotope.projector` | `isotope.platform.state.projector` |
| `isotope.events` | `isotope.platform.events.events` |
| `isotope.event_schema` | `isotope.platform.events.event_schema` |
| `isotope.refs` | `isotope.platform.schemas.refs` |
| `isotope.models` | `isotope.platform.schemas.*` |
| `isotope.errors` | `isotope.platform.errors` |
| `isotope.artifact_store` | `isotope.workspace.artifacts` |
| `isotope.retrieval` | `isotope.rag.retrieval` |
| `isotope.ingestion` | `isotope.rag.ingestion` |
| `isotope.action_compiler` | `isotope.runtime.action_compiler` |
| `isotope.action_registry` | `isotope.platform.registry.actions` |
| `isotope.executor` | `isotope.execution.executor` |
| `isotope.ids` | `isotope.platform.ids` |
| `isotope.tool_protocol` | `isotope.platform.schemas.tool_protocol` |

## 继续保留到下一轮判断

这些路径可能仍有命令、历史文档或外部调用价值：

| 路径 | 原因 |
| --- | --- |
| `isotope.demo` | 正式 demo 入口，`isotope-demo` 指向它 |
| `isotope.llm_live_smoke` | 正式 smoke 命令，`isotope-llm-smoke` 指向它 |
| `isotope.capability_runner` | 可用 `python -m isotope.capability_runner`，但正式命令已指向新路径 |
| `isotope.capability_catalog` | 早期架构文档仍大量引用 |
| `isotope.codex_*` | 外部 Codex 集成历史入口，需单独评估 |
| `isotope.terminal*` | 终端兼容测试仍覆盖旧入口 |

## 空壳和旧叙事

| 路径 | 状态 |
| --- | --- |
| `src/isotope/core/runtime.py` | 空壳，建议下一批删除或改成明确兼容占位 |
| `src/isotope/agent_runtime.py` | 指向 `core.runtime` 的旧代理 |
| `src/isotope/assistant/runtime.py` | 指向 `core.runtime` 的旧代理 |
| `src/isotope/core/loop_*` | agent loop 旧入口 |
| `src/isotope/assistant/loop_*` | assistant 旧入口 |

## 当前 blocker

- `tests/isotope/` 里还有 126 处 `from isotope import ...` 包级导入。
- `src/isotope/agent_runtime.py` 和 `src/isotope/assistant/runtime.py`
  仍指向空壳 `src/isotope/core/runtime.py`。
- `docs/architecture/` 和 `docs/reviews/` 仍有历史入口名，
  删除代理前不应按全文搜索结果机械改历史文档。

## 下一步删除顺序建议

1. 先处理 `core/runtime.py`、`agent_runtime.py`、`assistant/runtime.py` 空壳链。
2. 再把 `from isotope import xxx` 包级测试导入切到新路径。
3. 给根目录兼容代理建立最小兼容测试。
4. 然后按 `state / schema / rag / workspace / llm / terminal` 分组删除。
5. 每删一批，都更新本文和 [import-map](./import-map.md)。
