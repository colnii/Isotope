# 术语索引

状态：`当前索引 / 按新代码继续扩展`

本索引保留英文定位词，方便搜索代码和历史文档。
中文解释用于避免 AI 和人把项目重新误读成单纯底座工程。

| 英文定位词 | 中文解释 | 主要层级 | 主要位置 |
| --- | --- | --- | --- |
| `core` | 产品主流程，串起会话、对话循环、调度和响应 | 应用核心 | `src/isotope/core/` |
| `assistant` | 助手，只作为产品描述或旧路径兼容词，不作为新目录叙事 | 兼容/产品描述 | `src/isotope/assistant/` |
| `agent loop` | 智能体循环，AI 多步规划、调用工具、读取结果并继续执行 | 应用/智能体 | `src/isotope/agents/loop/step.py`, `docs/features/` |
| `app_friction` | 应用摩擦，应用层试跑暴露的卡点或待收束问题 | 应用验证 | `src/isotope/demo.py`, `docs/features/` |
| `planner` | 规划器，把用户目标转成可执行步骤或工具选择 | 智能体 | `docs/architecture/planner-input-output-contract-v0.2.md`, `src/isotope/agents/loop/planner_adapter.py` |
| `planner adapter` | 规划器适配层，把规划输出接到现有执行循环 | 智能体 | `src/isotope/agents/loop/planner_adapter.py` |
| `tick policy` | 步进策略，决定智能体循环每轮是否继续、暂停或停止 | 智能体 | `src/isotope/agents/loop/control.py`, `docs/architecture/agent-loop-tick-policy-boundary-v0.2.md` |
| `executor` | 执行器，执行已批准的动作或工具调用 | 执行 | `src/isotope/execution/executor.py` |
| `ActionCompiler` | 动作编译器，把紧凑意图转换成可审批的动作提案 | 运行时 | `src/isotope/runtime/action_compiler.py` |
| `tool call` | 工具调用，模型请求系统执行某个能力 | 模型/工具 | `src/isotope/llm/provider.py`, `src/isotope/llm/tool_bridge.py` |
| `terminal_exec` | 终端执行能力，受控运行命令并返回产物 | 工具 | `src/isotope/platform/registry/actions.py` |
| `terminal backend` | 终端后端，把终端命令封装成可测试执行层 | 工具 | `src/isotope/execution/terminal_backend.py` |
| `provider` | 模型服务适配器，连接外部模型服务 | 模型 | `src/isotope/llm/provider.py` |
| `product chat` | 产品聊天流程，让模型调用工具并返回面向用户的回答 | 产品能力 | `src/isotope/features/chat/flow.py` |
| `CLI` | 命令行入口，给人类和部署脚本直接调用 | 应用入口 | `apps/cli/`, `pyproject.toml` |
| `HttpApiApp` | 进程内 HTTP 风格接口，用于测试和应用边界，不监听端口 | 接口 | `src/isotope/interfaces/http.py` |
| `InProcessServer` | 进程内运行入口，串起会话、run、策略、执行和状态读取 | 运行时 | `src/isotope/runtime/in_process.py` |
| `CanonicalEvent` | 标准事件，所有状态回放的事实来源 | 平台事件 | `src/isotope/platform/events/events.py` |
| `artifact` | 产物记录，保存执行结果摘要和引用 | 平台数据 | `src/isotope/platform/schemas/models.py` |
| `ArtifactStore` | 产物存储，负责保存和读取 artifact 元数据与内容 | 工作区资源 | `src/isotope/workspace/artifacts.py` |
| `ResourceRef` | 资源引用，指向产物等对象而不是直接暴露全文 | 平台数据 | `src/isotope/platform/schemas/refs.py` |
| `RetrievalService` | 检索服务，按权限读取产物摘要或内容 | RAG/检索 | `src/isotope/rag/retrieval.py` |
| `ExternalIngestionService` | 外部输入接入，把结构化原始输入保存为 artifact-only 产物 | RAG/接入 | `src/isotope/rag/ingestion.py` |
| `checkpoint` | 检查点，用于恢复运行状态 | 状态恢复 | `src/isotope/platform/state/checkpoint_store.py` |
| `event log` | 事件日志，记录系统发生过的事实 | 状态恢复 | `src/isotope/platform/state/event_store.py` |
| `projector` | 投影器，把事件日志重建成可读状态 | 状态恢复 | `src/isotope/platform/state/projector.py` |
| `RunState` | 运行状态，投影后的当前视图 | 状态恢复 | `src/isotope/platform/state/projector.py` |
| `ToolInvocation` | 工具调用协议对象，给内部工具处理器传递参数 | 平台 schema | `src/isotope/platform/schemas/tool_protocol.py` |
| `ActionTypeRegistry` | 动作类型注册表，记录工具元数据、能力要求和版本信息 | 平台注册表 | `src/isotope/platform/registry/actions.py` |
| `new_id` | 简单 ID 生成器，给测试和进程内运行生成稳定前缀 ID | 平台工具 | `src/isotope/platform/ids.py` |
| `KernelError` | 结构化错误，给 HTTP 和 helper 返回稳定错误码 | 平台错误 | `src/isotope/platform/errors.py` |
| `policy` | 权限策略，决定动作是否允许、暂停或拒绝 | 安全/权限 | `src/isotope/policy/` |
| `approval` | 人工确认，敏感动作执行前的暂停和恢复机制 | 权限/产品 | `src/isotope/runtime/in_process.py` |
| `capability` | 能力，产品可发现、可运行的功能单元 | 产品能力 | `src/isotope/capabilities/catalog.py` |
| `capability runner` | 能力运行器，用命令行方式搜索能力、生成计划或启动能力 | 产品能力 | `src/isotope/capabilities/runner.py`, `isotope-capability` |
| `Codex task` | Codex 任务，把外部 Codex 执行封装成可路由能力 | 工具/任务 | `src/isotope/integrations/codex/task.py`, `src/isotope/integrations/codex/cli.py` |
| `workspace` | 工作区，任务运行时读写资源的边界 | 产品/资源 | `src/isotope/workspace/` |
| `memory` | 记忆，后续用于保存和查询长期上下文 | 智能体 | `src/isotope/memory/` |
| `RAG` | 检索增强生成，先检索资料再让模型回答 | 应用能力 | `src/isotope/rag/` |
| `workflow` | 工作流，多个步骤组成的任务流程 | 应用能力 | 待新目录设计 |
| `feature` | 业务功能，如聊天、搜索、工作区、权限 | 产品能力 | 待新目录设计 |

后续整理文档时，应继续补充：

- 用户常用但文档未解释的词。
- 历史文档里反复出现、但当前方向已改变的词。
- 需要从英文保留为代码搜索锚点的类名、模块名和命令名。
