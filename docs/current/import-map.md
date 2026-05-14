# 导入路径迁移表

状态：`当前清单 / terminal runner 批次已执行`

本文记录旧导入路径到新导入路径的迁移关系。
目标是让目录迁移有清单可查，而不是靠记忆维护兼容代理。

## 规则

- 新路径必须成为活跃实现路径。
- 旧路径只做兼容代理。
- 兼容代理暂不发 `DeprecationWarning`，避免测试输出变吵。
- 每个代理都应写明新路径和计划删除节点。
- 删除旧路径前，先确认主线代码、测试和 current 文档不再引用旧路径。

## 计划删除节点

当前统一写作：

```text
planned removal: after import-map confirms no active internal imports
```

等版本号或里程碑明确后，再替换成具体版本。

## 第一批：agent loop 正名

| 旧路径 | 新路径 | 状态 |
| --- | --- | --- |
| `isotope.core.loop_control` | `isotope.agents.loop.control` | 已迁移，旧路径保留兼容代理 |
| `isotope.core.loop_step` | `isotope.agents.loop.step` | 已迁移，旧路径保留兼容代理 |
| `isotope.core.loop_planner_adapter` | `isotope.agents.loop.planner_adapter` | 已迁移，旧路径保留兼容代理 |
| `isotope.core.real_planner_contract` | `isotope.agents.loop.planner_contract` | 已迁移，旧路径保留兼容代理 |
| `isotope.core.runtime` | 暂不迁移，当前为空壳兼容占位 | 待判断 |
| `isotope.assistant.loop_control` | `isotope.agents.loop.control` | 已迁移，旧路径保留兼容代理 |
| `isotope.assistant.loop_step` | `isotope.agents.loop.step` | 已迁移，旧路径保留兼容代理 |
| `isotope.assistant.loop_planner_adapter` | `isotope.agents.loop.planner_adapter` | 已迁移，旧路径保留兼容代理 |
| `isotope.assistant.real_planner_contract` | `isotope.agents.loop.planner_contract` | 已迁移，旧路径保留兼容代理 |
| `isotope.agent_loop_control` | `isotope.agents.loop.control` | 已迁移，旧路径保留兼容代理 |
| `isotope.agent_loop_step` | `isotope.agents.loop.step` | 已迁移，旧路径保留兼容代理 |
| `isotope.agent_loop_planner_adapter` | `isotope.agents.loop.planner_adapter` | 已迁移，旧路径保留兼容代理 |
| `isotope.real_planner_adapter_contract` | `isotope.agents.loop.planner_contract` | 已迁移，旧路径保留兼容代理 |

## 后续候选

| 旧路径 | 新路径候选 | 状态 |
| --- | --- | --- |
| `isotope.runtime.server` | `isotope.runtime.in_process` | 已迁移，旧路径保留兼容代理 |
| `isotope.server` | `isotope.runtime.in_process` | 已迁移，旧路径保留兼容代理 |
| `isotope.integrations.llm.provider` | `isotope.llm.provider` | 已迁移，旧路径保留兼容代理 |
| `isotope.integrations.llm.tool_bridge` | `isotope.llm.tool_bridge` | 已迁移，旧路径保留兼容代理 |
| `isotope.llm_provider` | `isotope.llm.provider` | 已迁移，旧路径保留兼容代理 |
| `isotope.model_tool_bridge` | `isotope.llm.tool_bridge` | 已迁移，旧路径保留兼容代理 |
| `isotope.features.chat.product_chat` | `isotope.features.chat.flow` | 已迁移，旧路径保留兼容代理 |
| `isotope.llm_product_chat_app` | `isotope.features.chat.flow` | 已迁移，旧路径保留兼容代理 |
| `isotope.execution.terminal_backend` | `isotope.execution.terminal_runner` | 已迁移，旧路径保留兼容代理 |
| `isotope.terminal_backend` | `isotope.execution.terminal_runner` | 已迁移，旧路径保留兼容代理 |
| `isotope.terminal_system_runner` | `isotope.execution.terminal_runner` | 已迁移，旧路径保留兼容代理 |
| `isotope.platform.schemas.models` | 拆成更具体 schema 文件 | 待设计 |

## 兼容代理模板

```python
"""Compatibility proxy.

New path:
    isotope.agents.loop.control

Planned removal:
    after import-map confirms no active internal imports.
"""

from isotope.agents.loop.control import *  # noqa: F401,F403
```
