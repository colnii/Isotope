# 兼容代理审计

状态：`当前清单 / 第三批低风险代理已删除`

本文记录旧导入路径和兼容代理，不直接要求马上删除。
目标是先知道哪些文件只是旧入口，哪些还承担命令或兼容测试职责。

## 当前结论

- `from isotope.xxx import ...` 形式的显式测试导入已改用新路径。
- 普通测试里的 `from isotope import xxx` 包级导入已改用新路径。
- 仅 `test_terminal_compatibility_imports.py` 保留 3 行旧导入，
  专门覆盖终端兼容入口。
- `src/isotope/` 根目录仍保留很多兼容代理，方便旧代码导入。
- `core/` 和 `assistant/` 当前没有活跃实现，只保留 agent loop 旧入口。
- `capability_runner.py`、`demo.py`、`llm_live_smoke.py` 仍有命令入口价值。
- 兼容入口已有最小测试：
  `tests/isotope/test_compat_proxy_imports.py`。
- `core/runtime.py`、`agent_runtime.py`、`assistant/runtime.py`
  空壳链已删除。
- `state`、`events`、`schema refs`、`workspace artifact`、`rag`
  和 `tool protocol` 的顶层纯代理已删除，活跃代码直接使用新路径。
- `runtime`、`interface`、`registry`、`execution`、`ids`
  的第二批顶层纯代理也已删除。
- `models/errors` 根入口、LLM 旧入口、chat 旧入口已删除。
- `platform.schemas.models` 仍暂留，因为测试还把它当 schema 汇总入口。

## 可优先进入删除计划

这些路径已有新实现路径，且显式测试导入已迁走：

| 旧路径 | 新路径 |
| --- | --- |
| `isotope.platform.schemas.models` | `isotope.platform.schemas.*` |

## 已删除代理

这些旧路径已不再可导入，主线代码和测试应直接使用新路径：

| 旧路径 | 新路径 |
| --- | --- |
| `isotope.models` | `isotope.platform.schemas.*` |
| `isotope.errors` | `isotope.platform.errors` |
| `isotope.integrations.llm` | `isotope.llm` |
| `isotope.integrations.llm.provider` | `isotope.llm.provider` |
| `isotope.integrations.llm.tool_bridge` | `isotope.llm.tool_bridge` |
| `isotope.llm_provider` | `isotope.llm.provider` |
| `isotope.model_tool_bridge` | `isotope.llm.tool_bridge` |
| `isotope.features.chat.product_chat` | `isotope.features.chat.flow` |
| `isotope.llm_product_chat_app` | `isotope.features.chat.flow` |
| `isotope.runtime.server` | `isotope.runtime.in_process` |
| `isotope.server` | `isotope.runtime.in_process` |
| `isotope.http_api` | `isotope.interfaces.http` |
| `isotope.action_compiler` | `isotope.runtime.action_compiler` |
| `isotope.action_registry` | `isotope.platform.registry.actions` |
| `isotope.executor` | `isotope.execution.executor` |
| `isotope.ids` | `isotope.platform.ids` |
| `isotope.checkpoint_store` | `isotope.platform.state.checkpoint_store` |
| `isotope.event_store` | `isotope.platform.state.event_store` |
| `isotope.projector` | `isotope.platform.state.projector` |
| `isotope.events` | `isotope.platform.events.events` |
| `isotope.event_schema` | `isotope.platform.events.event_schema` |
| `isotope.refs` | `isotope.platform.schemas.refs` |
| `isotope.artifact_store` | `isotope.workspace.artifacts` |
| `isotope.retrieval` | `isotope.rag.retrieval` |
| `isotope.ingestion` | `isotope.rag.ingestion` |
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
| `src/isotope/core/runtime.py` | 已删除，原本只是空壳 |
| `src/isotope/agent_runtime.py` | 已删除，原本只指向空壳 |
| `src/isotope/assistant/runtime.py` | 已删除，原本只指向空壳 |
| `src/isotope/core/loop_*` | agent loop 旧入口 |
| `src/isotope/assistant/loop_*` | assistant 旧入口 |

## 当前保留项

- `tests/isotope/test_terminal_compatibility_imports.py` 里保留 3 行
  `from isotope import ...`，用于验证旧终端入口仍兼容。
- `tests/isotope/test_compat_proxy_imports.py` 覆盖仍保留的兼容代理，
  也验证已删除旧入口不可再导入。
- `docs/architecture/` 和 `docs/reviews/` 仍有历史入口名，
  删除代理前不应按全文搜索结果机械改历史文档。

## 下一步删除顺序建议

1. 继续按 `terminal / capability / codex / agent-loop` 分组评估旧代理。
2. 每删一批，都更新本文和 [import-map](./import-map.md)。
