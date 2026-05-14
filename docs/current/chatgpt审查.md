我觉得这份文档**整体方向是对的，而且比我前面给的版本更贴近真实工程状态**。
它没有继续追求“宏大目录”，而是抓住了真正的问题：**当前 Isotope 的目录不是包名错，而是包内命名带着迁移痕迹，导致语义不稳定。**

我会给它一个评价：

> **可以作为迁移依据，但建议再收紧几处命名边界，尤其是 `core / runtime / execution / interfaces / models` 这几个词。**

---

## 我认可的部分

最重要的一条我完全同意：

```text
当前 core/loop_* 不应长期留在 core/，应迁到 agents/loop/
```

这是目前最该先做的。
因为你真实代码里的 `core/` 放的是 agent loop 控制逻辑，而不是产品主流程。继续留在 `core/` 会让后续真正的产品入口没有位置。

OpenAI Agents SDK 里也把 agent 的运行看成 turns、tools、guardrails、handoffs、sessions 等运行过程；如果你自己掌控 loop，那这些 loop 逻辑本来就更接近 `agents/loop/`，而不是泛泛的 `core/`。([OpenAI][1])

---

## 这份文档最大的优点

它没有说：

```text
立刻重构成最终架构
```

而是说：

```text
每批迁移必须可验证
旧路径仍可导入
新路径成为活跃导入路径
```

这个很工程化。

尤其是：

```text
新路径是活跃导入路径。
旧路径仍可导入，直到明确删除。
相关测试通过。
```

这比“目录好看”重要得多。

Python 项目继续使用 `src/isotope/` 也合理。Python Packaging User Guide 对 `src` layout 的解释是，它把真正可导入的包放进 `src/`，避免项目根目录里的配置、脚本、测试等内容被错误导入；这正适合你这种逐渐变复杂的应用项目。([Python 打包用户指南][2])

---

## 我建议改的第一处：`core/` 不要急着保留

文档里说：

```text
core/ # 产品主流程：session / conversation / dispatch / response
```

这个方向没错，但我建议现阶段不要急着建一个空的 `core/`。

如果现在还没有真正的：

```text
session.py
conversation.py
dispatch.py
response.py
```

那 `core/` 可以先作为**兼容代理目录**或暂时弱化，而不是强行变成“未来产品主流程”的空壳。

更稳的写法是：

```text
core/                 # 预留给产品主流程；当前不承载 agent loop
```

或者更严格一点：

```text
core/                 # 暂不扩展；仅在产品主流程稳定后启用
```

这样可以避免第二轮“为了目录语义而搬代码”。

---

## 我建议改的第二处：`runtime/` 和 `execution/` 还要再划清

你们现在的文档里：

```text
runtime/              # 进程内运行容器和启动边界
execution/            # terminal / process / sandbox / browser
```

这个区分是可以的，但容易继续撞。

我建议把定义写得更死一点：

```text
runtime/      只管 Isotope 自己怎么被启动、挂载、运行、关闭
execution/    只管 Isotope 代表用户去执行外部动作
```

比如：

```text
runtime/in_process.py      # Isotope 自己的进程内运行模式
runtime/lifespan.py        # 启动/关闭生命周期
runtime/container.py       # 运行容器

execution/terminal_runner.py
execution/process_runner.py
execution/sandbox.py
execution/browser_runner.py
```

这样以后不会出现：

```text
runtime/shell.py
execution/server.py
```

这种再次混乱。

所以 `runtime/server.py` 改成 `runtime/in_process.py` 是对的。
因为 `InProcessServer` 如果不是真 HTTP server，继续叫 server 会误导。

---

## 我建议改的第三处：`interfaces/` 要小心

目标结构里有：

```text
interfaces/           # HTTP / CLI / SDK facade
```

但顶层又有：

```text
apps/cli/
apps/api/
```

这两个容易冲突。

如果你保留 `apps/`，我建议：

```text
apps/cli/      真正的 CLI 入口
apps/api/      真正的 API 入口
```

而 `src/isotope/interfaces/` 只放**库内 facade / adapter interface**，比如：

```text
interfaces/
  cli_facade.py
  api_facade.py
  sdk.py
```

但如果现在没有明确需要，我甚至建议先删掉 `interfaces/`，避免多一个模糊层。

更干净的早期结构可以是：

```text
apps/
  cli/
  api/

src/isotope/
  core/
  features/
  agents/
  capabilities/
  ...
```

等真的要给外部开发者提供 SDK 时，再建：

```text
sdk/
```

或者：

```text
interfaces/sdk.py
```

---

## 我建议改的第四处：`models/` 可能会有歧义

文档里建议：

```text
models/
  llm/
```

这比放在 `integrations/llm/` 好，因为 LLM provider 确实不是外部应用集成，而是模型层。

但 `models` 在 Python 项目里容易有三种含义：

```text
数据库模型
Pydantic 数据模型
机器学习模型
LLM provider
```

你们又已经有：

```text
platform/schemas/models.py
```

所以我建议慎用 `models/`。

更明确的替代有三个：

### 方案 A：直接叫 `llm/`

```text
llm/
  provider.py
  tool_bridge.py
  router.py
```

优点是最清楚。

### 方案 B：叫 `model_providers/`

```text
model_providers/
  llm/
  embeddings/
  rerank/
```

优点是不会和 domain models 撞。

### 方案 C：保留 `models/llm/`

可以，但文档里要明确：

```text
models/ 仅指 AI model providers，不放 Pydantic schema，不放数据库模型。
```

如果你们未来会做 embedding、rerank、本地模型，`models/llm/` 可以接受；否则我更倾向于直接叫：

```text
llm/
```

---

## 我建议改的第五处：`rag/` 不一定要成为一等目录

文档里有：

```text
rag/                  # 接入、切分、检索、索引
```

如果 Isotope 当前已有明确 RAG 模块，那保留没问题。

但如果现在只是未来可能会有，我建议先不要提前建满。
RAG 在应用层可能只是 `features/research/` 的内部能力，等它被多个 feature 复用后再提升为一等目录。

也就是：

早期：

```text
features/research/retrieval.py
features/research/ingestion.py
```

成熟后：

```text
rag/
  ingestion.py
  retrieval.py
  indexing.py
```

这样更符合你们文档里“不为了目录漂亮提前建空功能”的原则。

---

## 我建议改的第六处：兼容代理要加“死亡日期”

文档里说：

```text
旧路径仍可导入，直到明确删除。
```

这个对，但最好再加一句：

```text
每个兼容代理必须标注 planned removal version 或 planned removal milestone。
```

否则兼容代理会永久存在，最后项目里永远有：

```text
assistant/
codex_*
llm_*
capability_*
```

我的建议是给兼容代理统一格式：

```python
# src/isotope/core/loop_control.py

"""
Compatibility proxy.

New path:
    isotope.agents.loop.control

Planned removal:
    after v0.3 or after docs/current/import-map.md is updated.
"""

from isotope.agents.loop.control import *  # noqa: F401,F403
```

如果项目还在快速变化期，可以先不发 `DeprecationWarning`，因为测试里会很吵；但文档里一定要标清。

---

## 对“建议归位”表的逐项判断

| 项目                                                                | 我的意见                                               |
| ----------------------------------------------------------------- | -------------------------------------------------- |
| `core/loop_control.py` → `agents/loop/control.py`                 | 同意                                                 |
| `core/loop_step.py` → `agents/loop/step.py`                       | 同意                                                 |
| `core/loop_planner_adapter.py` → `agents/loop/planner_adapter.py` | 同意                                                 |
| `real_planner_contract.py` → `planner_contract.py`                | 同意，但 `planner_protocol.py` 也可以                     |
| `core/runtime.py`                                                 | 如果只是空壳，删；如果有 loop state，进 `agents/loop/runtime.py` |
| `runtime/server.py` → `runtime/in_process.py`                     | 同意                                                 |
| `features/chat/product_chat.py` → `features/chat/flow.py`         | 同意，`product_` 前缀很像历史命名                             |
| `integrations/llm/provider.py` → `models/llm/provider.py`         | 方向同意，但建议考虑 `llm/provider.py`                       |
| `execution/terminal_backend.py` → `execution/terminal_runner.py`  | 同意                                                 |
| `platform/schemas/models.py`                                      | 强烈建议拆，不要叫 `models.py`                              |
| `platform/errors.py` 的 `KernelError`                              | 应该迁，但不要第一批动                                        |
| 顶层 `codex_*`、`llm_*`、`capability_*`                               | 保留薄代理，但要列清单和删除计划                                   |

---

## 我会额外加一条原则

你们现在的 10 条原则很好，但我建议加第 11 条：

> **同一概念只能有一个主目录，其他位置只能是 adapter 或 compatibility proxy。**

例如：

```text
LLM provider 的主目录只能是 llm/ 或 models/llm/
不能同时在 integrations/llm/、platform/schemas/models.py、capabilities/tool_bridge.py 里各有一份主实现。
```

这条很关键，因为 Isotope 这种项目最容易出现“一物多名”。

---

## 我会微调后的目标结构

我会稍微收紧成这样：

```text
src/isotope/
  core/                 # 产品主流程；当前不承载 agent loop
  features/             # 用户功能：chat / tasks / projects / files / research
  agents/               # 智能体角色与 agent loop
    loop/
  capabilities/         # 可注册、可调用能力
    tools/
    skills/
  llm/                  # LLM / embedding / rerank provider；比 models/ 更不歧义
  rag/                  # 仅在已有独立 RAG 复用需求时保留
  memory/               # 长期记忆、总结、上下文检索
  workspace/            # 项目、文件、artifact、git 工作区
  execution/            # terminal / process / sandbox / browser
  integrations/         # Codex / MCP / GitHub / VS Code 等外部系统接入
  runtime/              # Isotope 自身运行容器和启动边界
  platform/             # events / schemas / state / registry / errors / ids
  common/               # 少量无业务含义的通用工具
```

我这里主要改了两点：

```text
models/llm/ → llm/
interfaces/ 暂时移除
```

理由是早期项目越少模糊层越好。

---

## 第一批迁移我赞成，但建议补一个 import map

批次一之前，先建一个文档：

```text
docs/current/import-map.md
```

内容类似：

```text
旧路径                                新路径
isotope.core.loop_control             isotope.agents.loop.control
isotope.core.loop_step                isotope.agents.loop.step
isotope.core.loop_planner_adapter     isotope.agents.loop.planner_adapter
isotope.core.real_planner_contract    isotope.agents.loop.planner_contract
```

然后批次一验收增加两条：

```text
- grep 确认内部主线导入已经使用新路径。
- import-map.md 中列出的旧路径仍可导入。
```

这会让迁移非常稳。

---

## 最终结论

这份文档可以用，而且我认为它抓住了核心问题：

> **Isotope 现在不是缺宏大架构，而是需要把迁移痕迹从主语义里剥离出去。**

我建议你确认它的主结论：

```text
core/loop_* → agents/loop/
```

然后稍微修改三处：

```text
models/llm/ 先考虑改成 llm/
interfaces/ 暂时不进目标结构
兼容代理必须有 import map 和删除计划
```

改完后，这份文档就可以作为第一轮命名迁移的依据。

[1]: https://openai.github.io/openai-agents-python/agents/?utm_source=chatgpt.com "OpenAI Agents SDK"
[2]: https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/?utm_source=chatgpt.com "src layout vs flat layout"
