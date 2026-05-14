# controlled-terminal-exec 深审：2026-05-15

状态：`深审完成`

## 审计范围

- 分支：`feature/controlled-terminal-exec`
- 基准：`main` 的文档整备提交 `c4d24ed`
- 方式：只读阅读源码、提交链、差异统计和针对性测试。
- 未合并代码，未修改该功能分支。

## 验证结果

外部 worktree 没有自己的 `.venv`，所以使用主仓库虚拟环境解释器。

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/isotope_kernel/test_controlled_terminal_execution.py \
  tests/isotope_kernel/test_terminal_backend_adapter_contract.py \
  tests/isotope_kernel/test_linux_system_terminal_runner.py \
  tests/isotope_kernel/test_codex_task_adapter_contract.py \
  tests/isotope_kernel/test_codex_cli_backend.py \
  tests/isotope_kernel/test_model_tool_bridge.py \
  tests/isotope_kernel/test_llm_provider_tool_loop.py \
  tests/isotope_kernel/test_llm_product_chat_app_entry.py -q
```

结果：`81 passed`

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/isotope_kernel/test_terminal_backend_executor_integration.py \
  tests/isotope_kernel/test_http_api_codex_task_route.py \
  tests/isotope_kernel/test_http_api_llm_provider_route.py \
  tests/isotope_kernel/test_http_api_llm_product_chat_route_contract.py \
  tests/isotope_kernel/test_http_api_llm_product_chat_route_boundary.py \
  tests/isotope_kernel/test_http_api_route_inventory.py -q
```

结果：`52 passed, 1 skipped`

## 总体结论

这个分支不是低价值半成品。

它已经做出了 AI 应用需要的关键骨架：

- 受控终端执行：`terminal_exec`
- 真实终端后端：`TerminalBackendAdapter`
- 本地 Linux runner：`LinuxSystemTerminalRunner`
- Codex CLI 任务适配：`codex_task`
- 模型选工具桥：`model_tool_bridge`
- LLM provider：`DeepSeekToolCallProvider`
- 产品聊天入口：`llm_product_chat_app`

但它也不能整分支合并：

- 所有代码仍在旧 `src/isotope_kernel/` 里。
- 文档路径已经和当前 `main` 的新结构冲突。
- 分支里有大量诊断、preflight、resume 防御提交。
- 产品入口还是薄封装，不是完整前端或正式后端应用。

正确处理方式是“抽能力，不合旧形态”。

## 可迁移切片

### 1. 终端执行层

候选文件：

- `src/isotope_kernel/terminal.py`
- `src/isotope_kernel/terminal_backend.py`
- `src/isotope_kernel/terminal_system_runner.py`
- `tests/isotope_kernel/test_controlled_terminal_execution.py`
- `tests/isotope_kernel/test_terminal_backend_adapter_contract.py`
- `tests/isotope_kernel/test_linux_system_terminal_runner.py`

建议迁移到：

- `src/agents/tools/terminal.py`
- `src/agents/executor/terminal_backend.py`
- `src/core/artifacts/`

价值：这是最清楚、最可复用的第一批代码。

需要调整：

- `ControlledTerminalRunner` 当前用 artifact store root 当执行目录。
- 应改成显式 workspace binding，而不是隐式跑在存储目录。
- `LinuxSystemTerminalRunner` 里时间戳是固定测试值，生产化前要替换成真实时间。

### 2. LLM 工具调用桥

候选文件：

- `src/isotope_kernel/model_tool_bridge.py`
- `src/isotope_kernel/llm_provider.py`
- `tests/isotope_kernel/test_model_tool_bridge.py`
- `tests/isotope_kernel/test_llm_provider_tool_loop.py`

建议迁移到：

- `src/models/llm/`
- `src/agents/tools/`

价值：它把“模型选择工具”和“平台执行工具”分开了，这正是 AI 应用需要的形状。

需要调整：

- 当前 provider 只实现 DeepSeek OpenAI-compatible HTTP。
- 后续应把 provider 抽成配置层，而不是写死一个默认模型。
- 可以参考 OpenAI SDK、LiteLLM 或其他成熟项目实现 provider 适配。

### 3. 产品聊天入口

候选文件：

- `src/isotope_kernel/llm_product_chat_app.py`
- `tests/isotope_kernel/test_llm_product_chat_app_entry.py`
- `tests/isotope_kernel/test_http_api_llm_product_chat_route_contract.py`

建议迁移到：

- `src/features/chat/`
- `apps/api/`

价值：这是分支里最接近“真正 AI 应用”的部分。

需要调整：

- 当前入口仍是 in-process helper，不是 FastAPI 后端。
- `max_tool_steps` 当前限制为 `1`，不能当完整 agent loop。
- preflight / resume 防御很多，迁移时只保留用户能感知的必要状态。

### 4. Codex 任务适配

候选文件：

- `src/isotope_kernel/codex_task.py`
- `src/isotope_kernel/codex_cli.py`
- `src/isotope_kernel/codex_server.py`
- `tests/isotope_kernel/test_codex_task_adapter_contract.py`
- `tests/isotope_kernel/test_codex_cli_backend.py`

建议迁移到：

- `src/agents/executor/codex_adapter.py`
- 或作为开发期工具保留，不进入第一版产品主路径。

价值：可以让 Isotope 调用 Codex 做子任务。

限制：

- 当前强制 `read-only` sandbox 和 `approval_policy=never`。
- 适合作为只读分析 / 建议工具，不适合作为第一版可写执行 agent。

## 不建议直接迁移的部分

- 旧 `docs/` 路径下的分支文档。
- 大量 product-chat resume 错误文案微调提交。
- 旧 `AGENTS.md` / `README.md` 改动。
- 绑定 `src/isotope_kernel/` 命名的整体结构。

这些内容可以作为参考，但不应覆盖当前文档整备结果。

## 合并策略

建议拆成三步：

1. 新建迁移分支，先迁移终端执行层。
2. 再迁移 LLM provider 和 model tool bridge。
3. 最后把 product chat 做成 `apps/api` 下的真实入口。

不建议从 `feature/controlled-terminal-exec` 直接 rebase 合入当前 `main`。

## 下一步

先做第一步：迁移终端执行层。

目标不是保留旧 `kernel` 叙述，而是在新应用结构里建立：

- `src/agents/tools/terminal.py`
- `src/agents/executor/terminal_backend.py`
- 对应测试路径
- 最小 HTTP / app 接入口可以后置
