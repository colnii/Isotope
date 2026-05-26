# 兼容代理审计

状态：`当前清单 / 根层入口已复核`

本文记录旧导入路径和兼容代理，不直接要求马上删除。
目标是先知道哪些文件只是旧入口，哪些还承担命令或兼容测试职责。

## 当前结论

- `from isotope.xxx import ...` 形式的显式测试导入已改用新路径。
- 普通测试里的 `from isotope import xxx` 包级导入已改用新路径。
- 终端旧入口已删除，测试改用 `execution.terminal_runner`。
- `src/isotope/` 根目录已不再保留顶层兼容代理。
- `core/` 已开始承接产品主流程，当前不是兼容代理目录。
- `assistant` 旧包已删除。
- `demo/__init__.py`、`llm_live_smoke.py` 是正式命令入口。
- `capability_runner.py` 旧根入口已删除，正式命令指向
  `isotope.capabilities.runner`。
- `tools/` 旧空包已删除；工具能力以 `capabilities/tools/`
  和能力注册表为准。
- 兼容入口已有最小测试：
  `tests/unit/integrations/codex/test_compat_proxy_imports.py`。
- `core/runtime.py`、`agent_runtime.py`、`assistant/runtime.py`
  空壳链已删除。
- `state`、`events`、`schema refs`、`workspace artifact`、`rag`
  和 `tool protocol` 的顶层纯代理已删除，活跃代码直接使用新路径。
- `runtime`、`interface`、`registry`、`execution`、`ids`
  的第二批顶层纯代理也已删除。
- `models/errors` 根入口、LLM 旧入口、chat 旧入口已删除。
- terminal 顶层旧入口和 `execution.terminal_backend` 已删除。
- capability 顶层旧入口已删除，命令行改用 `isotope-capability`
  或 `python -m isotope.capabilities.runner`。
- Codex 顶层旧入口已删除，活跃代码直接使用 `integrations.codex`。
- agent-loop、core 和 assistant 旧入口已删除，活跃代码直接使用
  `agents.loop`。
- `platform.schemas.models` 汇总兼容入口已删除，测试直接使用具体
  schema 模块。

## 可优先进入删除计划

当前没有已确认应继续删除的兼容代理。
根层只剩 `__init__.py`（`loop_engine.py` 已移入 `agents/loop/`，`demo`/`llm_live_smoke` 已移入 `demo/` 子包）。

## 已删除代理

这些旧路径已不再可导入，主线代码和测试应直接使用新路径：

| 旧路径 | 新路径 |
| --- | --- |
| `isotope.platform.schemas.models` | `isotope.platform.schemas.*` |
| `isotope.models` | `isotope.platform.schemas.*` |
| `isotope.errors` | `isotope.platform.errors` |
| `isotope.integrations.llm` | `isotope.llm` |
| `isotope.integrations.llm.provider` | `isotope.llm.provider` |
| `isotope.integrations.llm.tool_bridge` | `isotope.llm.tool_bridge` |
| `isotope.llm_provider` | `isotope.llm.provider` |
| `isotope.model_tool_bridge` | `isotope.llm.tool_bridge` |
| `isotope.features.chat.product_chat` | `isotope.features.chat.flow` |
| `isotope.llm_product_chat_app` | `isotope.features.chat.flow` |
| `isotope.execution.terminal_backend` | `isotope.execution.terminal.runner` |
| `isotope.terminal` | `isotope.capabilities.tools.terminal` |
| `isotope.terminal_backend` | `isotope.execution.terminal_runner` |
| `isotope.terminal_system_runner` | `isotope.execution.terminal_runner` |
| `isotope.tools` | 无活跃新路径 |
| `isotope.tools.write_artifact` | 无活跃新路径 |
| `isotope.capability_catalog` | `isotope.capabilities.catalog` |
| `isotope.capability_runner` | `isotope.capabilities.runner` |
| `isotope.codex_cli` | `isotope.integrations.codex.cli` |
| `isotope.codex_live_smoke` | `isotope.integrations.codex.live_smoke` |
| `isotope.codex_server` | `isotope.integrations.codex.server` |
| `isotope.codex_task` | `isotope.integrations.codex.task` |
| `isotope.agent_loop_control` | `isotope.agents.loop.control` |
| `isotope.agent_loop_step` | `isotope.agents.loop.step` |
| `isotope.agent_loop_planner_adapter` | `isotope.agents.loop.planner_adapter` |
| `isotope.real_planner_adapter_contract` | `isotope.agents.loop.planner_contract` |
| `isotope.core.loop_control` | `isotope.agents.loop.control` |
| `isotope.core.loop_step` | `isotope.agents.loop.step` |
| `isotope.core.loop_planner_adapter` | `isotope.agents.loop.planner_adapter` |
| `isotope.core.real_planner_contract` | `isotope.agents.loop.planner_contract` |
| `isotope.assistant` | 无活跃新路径 |
| `isotope.assistant.loop_control` | `isotope.agents.loop.control` |
| `isotope.assistant.loop_step` | `isotope.agents.loop.step` |
| `isotope.assistant.loop_planner_adapter` | `isotope.agents.loop.planner_adapter` |
| `isotope.assistant.real_planner_contract` | `isotope.agents.loop.planner_contract` |
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
| `isotope.demo` | 正式 demo 入口包（`demo/__init__.py`），`isotope-demo` 指向它 |
| `isotope.demo.llm_live_smoke` | 正式 smoke 命令，`isotope-llm-smoke` 指向 `isotope.demo.llm_live_smoke` |

## 空壳和旧叙事

| 路径 | 状态 |
| --- | --- |
| `src/isotope/core/runtime.py` | 已删除，原本只是空壳 |
| `src/isotope/agent_runtime.py` | 已删除，原本只指向空壳 |
| `src/isotope/assistant/runtime.py` | 已删除，原本只指向空壳 |
| `src/isotope/core/loop_*` | 已删除，原本只是 agent loop 旧入口 |
| `src/isotope/assistant/loop_*` | 已删除，原本只是 assistant 旧入口 |

## 当前保留项

- `tests/unit/integrations/codex/test_compat_proxy_imports.py` 覆盖仍保留的兼容代理，
  也验证已删除旧入口不可再导入。
- `docs/architecture/` 和 `docs/reviews/` 仍有历史入口名，
  删除代理前不应按全文搜索结果机械改历史文档。

## 下一步建议

1. 后续若新增兼容代理，先登记到本文和 [import-map](./import-map.md)。
2. 下一轮目录工作应转向真实功能分层，不再围绕旧根路径清理。
