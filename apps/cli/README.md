# CLI 入口

这里放面向人类和部署脚本的命令行入口。

当前入口保持很薄，只转发到 `src/isotope/` 内的稳定模块：

- `isotope-demo`：运行 demo 场景，对应 `isotope.demo:main`。
- `isotope-capability`：运行 capability 能力目录，对应 `isotope.capabilities.runner:main`。
- `isotope-llm-smoke`：运行 LLM smoke 检查，对应 `isotope.llm_live_smoke:main`。

本目录用于说明和本地直接调用；正式安装入口在 `pyproject.toml` 的
`[project.scripts]` 中声明。
