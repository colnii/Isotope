# CLI 入口

这里放面向人类和部署脚本的命令行入口。

当前入口保持很薄，只转发到 `src/isotope/` 内的稳定模块：

- `isotope-demo`：运行 demo 场景，包含 `v0.2`、`workbench`、`project-workspace` 和追加流程。
- `isotope-capability`：运行 capability 能力目录，对应 `isotope.capabilities.runner:main`。
- `isotope-task`：运行、读取和列出 tasks 摘要，对应 `isotope.features.tasks.runner:main`。
- `isotope-file`：运行 files 功能入口，对应 `isotope.features.files.runner:main`。
- `isotope-project`：运行 projects 功能入口，支持项目摘要、组合摘要、workspace 创建和追加。
- `isotope-search`：运行 search 功能入口，搜索低敏摘要并支持类型和数量过滤。
- `isotope-workbench`：运行 workbench 功能入口，读取产品首页低敏汇总、空状态和更新时间。
- `isotope-api`：检查 API 后端入口，当前可列出 ASGI 路由。
- `isotope-supervisor`：只读观察本机 Codex 会话，输出中文状态汇报。
- `isotope-llm-smoke`：运行 LLM smoke 检查，对应 `isotope.llm_live_smoke:main`。

本目录用于说明和本地直接调用；正式安装入口在 `pyproject.toml` 的
`[project.scripts]` 中声明。
