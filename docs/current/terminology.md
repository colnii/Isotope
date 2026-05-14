# 术语索引

状态：`当前索引 / 按新代码继续扩展`

本索引保留英文定位词，方便搜索代码和历史文档。
中文解释用于避免 AI 和人把项目重新误读成单纯底座工程。

| 英文定位词 | 中文解释 | 主要层级 | 主要位置 |
| --- | --- | --- | --- |
| `agent loop` | 智能体循环，AI 多步规划、调用工具、读取结果并继续执行 | 应用/智能体 | `src/isotope_kernel/demo.py`, `docs/features/` |
| `planner` | 规划器，把用户目标转成可执行步骤或工具选择 | 智能体 | `docs/architecture/planner-input-output-contract-v0.2.md`, `src/isotope_kernel/agent_loop_planner_adapter.py` |
| `planner adapter` | 规划器适配层，把规划输出接到现有执行循环 | 智能体 | `src/isotope_kernel/agent_loop_planner_adapter.py` |
| `tick policy` | 步进策略，决定智能体循环每轮是否继续、暂停或停止 | 智能体 | `src/isotope_kernel/agent_loop_step.py`, `docs/architecture/agent-loop-tick-policy-boundary-v0.2.md` |
| `executor` | 执行器，执行已批准的动作或工具调用 | 核心执行 | `src/isotope_kernel/executor.py` |
| `tool call` | 工具调用，模型请求系统执行某个能力 | 模型/工具 | `src/isotope_kernel/llm_provider.py`, `src/isotope_kernel/model_tool_bridge.py` |
| `terminal_exec` | 终端执行能力，受控运行命令并返回产物 | 工具 | `src/isotope_kernel/action_registry.py` |
| `terminal backend` | 终端后端，把终端命令封装成可测试执行层 | 工具 | `src/agents/executor/terminal_backend.py`, `src/isotope_kernel/terminal_backend.py` |
| `provider` | 模型服务适配器，连接外部模型服务 | 模型 | `src/isotope_kernel/llm_provider.py` |
| `product chat` | 产品聊天入口，让模型调用工具并返回面向用户的回答 | 产品能力 | `src/isotope_kernel/llm_product_chat_app.py` |
| `artifact` | 产物记录，保存执行结果摘要和引用 | 核心数据 | `src/isotope_kernel/models.py` |
| `ResourceRef` | 资源引用，指向产物等对象而不是直接暴露全文 | 核心数据 | `src/isotope_kernel/refs.py` |
| `checkpoint` | 检查点，用于恢复运行状态 | 状态恢复 | `src/isotope_kernel/checkpoint_store.py` |
| `event log` | 事件日志，记录系统发生过的事实 | 状态恢复 | `src/isotope_kernel/event_store.py` |
| `projector` | 投影器，把事件日志重建成可读状态 | 状态恢复 | `src/isotope_kernel/projector.py` |
| `RunState` | 运行状态，投影后的当前视图 | 状态恢复 | `src/isotope_kernel/models.py` |
| `policy` | 权限策略，决定动作是否允许、暂停或拒绝 | 安全/权限 | `src/isotope_kernel/policy.py` |
| `approval` | 人工确认，敏感动作执行前的暂停和恢复机制 | 权限/产品 | `src/isotope_kernel/server.py` |
| `capability` | 能力，产品可发现、可运行的功能单元 | 产品能力 | `src/isotope_kernel/capability_catalog.py` |
| `capability runner` | 能力运行器，用命令行方式搜索能力、生成计划或启动能力 | 产品能力 | `src/isotope_kernel/capability_runner.py` |
| `Codex task` | Codex 任务，把外部 Codex 执行封装成可路由能力 | 工具/任务 | `src/isotope_kernel/codex_task.py`, `src/isotope_kernel/codex_cli.py` |
| `workspace` | 工作区，任务运行时读写资源的边界 | 产品/资源 | `src/isotope_kernel/workspace.py` |
| `memory` | 记忆，后续用于保存和查询长期上下文 | 智能体 | `src/isotope_kernel/memory.py` |
| `RAG` | 检索增强生成，先检索资料再让模型回答 | 应用能力 | 待新目录设计 |
| `workflow` | 工作流，多个步骤组成的任务流程 | 应用能力 | 待新目录设计 |
| `feature` | 业务功能，如聊天、搜索、工作区、权限 | 产品能力 | 待新目录设计 |

后续整理文档时，应继续补充：

- 用户常用但文档未解释的词。
- 历史文档里反复出现、但当前方向已改变的词。
- 需要从英文保留为代码搜索锚点的类名、模块名和命令名。
