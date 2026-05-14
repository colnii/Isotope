# Agent 任务队列

状态：`当前入口 / 命名审计`

## 当前事实

- Isotope 是 AI 应用软件，不是单纯内核项目。
- 本地只保留 `main`，远端只保留 `origin/main`。
- 旧功能分支已完成审计、代码抽取和清理。
- 可迁移代码已进入主线，剩余分支内容只保留历史参考价值。
- `docs/` 已分成 `current/`、`architecture/`、`features/`、`reviews/`、`archive/`。
- 主包已迁移到 `src/isotope/`，后续继续做应用内分层。

## 已完成批次

1. 协作入口清理：`AGENTS.md` 已改成中文主叙述，并控制在 100 行以内。
2. 文档分层整理：`docs/` 根目录没有 Markdown 残留，入口集中到 `docs/current/`。
3. 术语索引：保留英文定位词，补中文解释和主要位置。
4. 应用目录方案：已写 [application-structure-plan](./application-structure-plan.md)。
5. 分支审计清理：结果见 [branch-cleanup](../reviews/branch-cleanup-2026-05-15.md)。
6. 文档二次清理：当前入口已刷新，不再传播旧分支暂停口径。
7. 包名迁移：`src/isotope_kernel/` 已迁到 `src/isotope/`。
8. 应用内分层第一批：平台 schema、平台事件、能力目录已迁入子目录。
9. 聊天功能入口：产品聊天入口已迁入 `src/isotope/features/chat/`。
10. 核心循环入口：`agent_loop_*` 已从 `assistant/` 收束到 `src/isotope/core/`。
11. 资源层入口：workspace、artifact、RAG、memory 边界已迁入对应目录。
12. 权限与注册表入口：policy、action registry、errors 已迁入新目录。
13. 执行器入口：executor 已迁入 `src/isotope/execution/`。
14. HTTP facade 入口：`http_api.py` 已迁入 `src/isotope/interfaces/`。
15. LLM 与 Codex 集成：模型 provider、tool bridge、Codex task/CLI/server/live smoke 已迁入 `src/isotope/integrations/`。
16. 状态恢复入口：checkpoint store、event store、projector 已迁入 `src/isotope/platform/state/`。
17. 运行入口：`server.py` 已迁入 `src/isotope/runtime/server.py`。
18. CLI 入口：`apps/cli/` 已建立薄入口，`pyproject.toml` 已声明正式命令。
19. 运行时工具：`action_compiler.py` 迁入 `runtime/`，`ids.py` 迁入 `platform/`，活跃终端引用改到真实实现路径。
20. 平台 schema/event：活跃代码已切到 `platform/schemas/` 与 `platform/events/`，旧根路径保留兼容代理。
21. 资源/RAG 兼容入口：`artifact_store.py`、`retrieval.py`、`ingestion.py` 已改为模块代理。
22. `assistant` 命名收束：活跃循环实现已迁入 `core/`，`assistant/` 只保留兼容代理。
23. demo 旧叙事清理：活跃 agent-loop demo 统一改用 `app_friction`。
24. 命名与目录审计：已写 [naming-and-structure-review](./naming-and-structure-review.md)。
25. 外部审查吸收：已加入 [chatgpt审查](./chatgpt审查.md) 和 [import-map](./import-map.md)。

## 最近完成：命名与目录审计

完成内容：

- 对比 ChatGPT 设想的 `core/` 和真实 `src/isotope/core/`。
- 确认当前 `core/loop_*` 更像 agent loop，不像产品主流程。
- 提出先迁到 `src/isotope/agents/loop/` 的候选方案。
- 采纳审查意见：`core/` 暂不扩张空壳，`llm/` 优先于 `models/llm/`，
  `interfaces/` 只保留当前库内 facade。
- 新增 `import-map.md`，作为兼容代理和后续删除计划的清单。

验收：

- 文档只给审计和推荐，不直接要求改代码。
- 下一步代码迁移需等用户确认 `agents/loop/` 方向。
- 文档地图需要能找到审计入口。

## 下一批次：应用内分层迁移

目标：

- 保持 `src/isotope/` 作为长期 Python 包命名空间。
- 把当前平铺模块逐步迁入 `agents/loop/`、`features/`、`platform/` 等层级。
- 下一步优先确认并执行 agent loop 正名，或继续调整命名审计文档。
- 迁移完成后再恢复多分支并行开发。

初始参考：

- `apps/cli/`：命令行入口。
- `apps/api/`：后端入口。
- `src/isotope/core/`：目标上应是产品主流程；当前实际还需继续整理。
- `src/isotope/agents/loop/`：建议中的 agent loop 目标目录。
- `src/isotope/assistant/`：旧路径兼容代理，不再扩张新实现。
- `src/isotope/features/`：聊天、任务、项目、文件、研究等可用功能。
- `src/isotope/capabilities/`：工具、技能、能力注册。
- `src/isotope/execution/`：shell、python、浏览器、沙箱执行。
- `src/isotope/runtime/`：进程内运行入口。
- `src/isotope/workspace/`：文件、项目、git 工作区。
- `src/isotope/rag/`：接入、检索、索引。
- `src/isotope/llm/`：建议中的模型服务层，优先于 `models/llm/`。
- `src/isotope/memory/`：记忆、总结、上下文。
- `src/isotope/policy/`：权限、审批、风险。
- `src/isotope/platform/`：事件、schema、registry、state、lifecycle。
- `src/isotope/interfaces/`：当前只作为库内 HTTP facade，不扩张成 CLI / SDK。

## 验证命令

文档批次至少运行：

```bash
git diff --check
wc -l AGENTS.md
find docs -maxdepth 1 -type f -name '*.md' -print
```

代码未改时，不必运行完整测试。
代码迁移批次需运行相关测试；共享路径迁移后跑全量测试。
