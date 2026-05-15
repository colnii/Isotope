# Isotope 当前状态

状态：`主线已收束 / 应用目录收束中`

## 当前判断

Isotope 是 AI 应用软件，不是单纯内核项目。

过去的开发过度强调底座、谨慎和边界，导致产品功能推进偏慢。
此前暂停过所有功能分支，现已完成分支审计、代码抽取和分支清理。

当前所在分支只表示代码位置，不代表项目方向。
项目方向由产品目标决定：秋招前搭出可展示、可继续扩展的 AI 应用。

## 当前分支状态

- 本地只保留 `main`。
- 远端只保留 `origin/main`。
- 旧暂停分支中的可用代码已抽入主线。
- 旧分支剩余内容只保留在历史提交中，不再作为待迁移代码。
- 后续功能应从 `main` 新开分支或新 worktree。

## 当前优先级

1. 保持当前 `main` 干净。
2. 后续功能从明确产品目标出发新开分支。
3. 目录结构设计另行讨论；当前继续把 `core` 薄主流程接到真实功能层。
4. 继续避免把产品功能降级成诊断或半成品。
5. `assistant` 不再作为新目录叙事，旧路径入口已删除。
6. 活跃 demo 输出使用 `app_friction` 描述应用摩擦，不再传播旧的底座摩擦字段。
7. agent loop 活跃实现已迁入 `src/isotope/agents/loop/`。
8. 兼容代理迁移需同步维护 `docs/current/import-map.md`，并写明计划删除节点。
9. `core` 当前薄包 `InProcessServer`，已有 conversation（对话）、
   task（任务）和 turn（回合）状态，不承载 agent loop 内部实现。
10. `features/tasks` 已有薄入口、低敏摘要索引、`isotope-task`
    CLI 和 tasks API，当前提供任务创建、读取和列表。
11. `features/files` 已有薄入口，当前可把文本保存成
    artifact-backed file summary，已接入 `isotope-file` 和 `/files`
    HTTP facade。
12. `features/projects` 已有薄入口，当前可创建项目摘要、关联
    task/file id、读取关联 task/file 低敏组合摘要，并通过
    `isotope-project` 和 `/projects` 调用。
13. `features/search` 已有薄入口，当前可统一搜索 project/task/file
    低敏摘要，支持类型过滤和结果数量限制，并通过 `isotope-search`
    和 `POST /search` 调用。

## 文档策略

- 入口文档要短、中文、可执行。
- 历史文档只在有追溯价值时保留。
- 已过期的暂停规则不再作为 AI 行为依据。
- 文档结构要兼顾 AI 检索和人类审阅。
- 术语和目录命名要从 AI 应用角度重新整理。
- 历史归档里的旧说法不代表当前方向。

## 开发策略

- 速度和质量都重要。
- 测试用于保护交付，不用于拖慢交付。
- 真实产品功能不能被自动降级成诊断或预检查。
- 需要收窄范围时，先向用户说明并对齐。

## 当前验证

常用检查：

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope -q
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario v0.2 --trace
.venv/bin/isotope-demo --scenario v0.2 --trace
git status --short
```

是否运行完整测试，由具体任务风险决定。
