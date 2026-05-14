# 应用目录迁移方案

状态：`方案初稿 / 尚未移动代码`

当前 `src/isotope_kernel/` 是历史遗留包名。
后续 Isotope 应按 AI 应用软件组织目录，而不是继续围绕 `kernel` 命名。

## 目标结构

```text
apps/
  api/
  web/
  worker/
src/
  core/
  models/
  agents/
  rag/
  features/
  workflows/
  prompts/
  schemas/
tests/
docs/
docker/
deployments/
datasets/
notebooks/
scripts/
```

## 初步映射

- `core/`：配置、日志、事件、状态恢复、权限策略、通用工具。
- `models/`：LLM、embedding、reranker 和模型服务适配器。
- `agents/`：规划器、执行器、记忆、工具调用和智能体循环。
- `rag/`：摄入、切分、检索、索引。
- `features/`：聊天、搜索、工作区、权限等业务功能。
- `workflows/`：LangGraph、DAG 或 pipeline。
- `prompts/`：系统提示词、模板、评测提示词。
- `schemas/`：Pydantic 模型、类型定义、接口结构。

## 迁移原则

- 先出映射表，再移动代码。
- 先迁移低风险模块，再迁移入口和测试。
- 保持测试可运行，不做一次性大爆炸重命名。
- 每次迁移都更新导入路径、测试路径和文档入口。
- 历史包名可保留短期兼容层，但不作为长期方向。
