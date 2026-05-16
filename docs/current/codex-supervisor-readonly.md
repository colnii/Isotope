# Codex Supervisor 只读第一版

状态：`第一版 / 本机只读监控`

## 目标

Codex Supervisor 用来观察本机多个 Codex 终端窗口。
第一版只做读取和汇报，不向窗口自动输入指令。

它解决的问题是：

- 不用反复问每个 Codex “下一步”。
- 快速看到哪些窗口在工作、等待用户、疑似停住或疑似报错。
- 先把状态判断跑通，再做后续自动发指令。

## 当前能力

- 从 `~/.codex/sessions` 读取本机 Codex 会话记录。
- 识别 session id、工作目录、git 分支和最近消息。
- 按最近事件时间排序，默认展示最近 10 个会话。
- 用规则判断 `工作中`、`等待用户`、`疑似停住`、`疑似报错`、`空闲`。
- 输出中文报告，也支持 JSON。

## 运行方式

开发态：

```bash
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner scan
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner watch --interval 180
```

安装后：

```bash
.venv/bin/isotope-supervisor scan
.venv/bin/isotope-supervisor watch --interval 180
```

调试 JSON：

```bash
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner scan --json
```

## 当前边界

- 不接管普通终端窗口。
- 不自动给 Codex 发指令。
- 不直接检查 SSH 服务器内部进程。
- 不把完整日志发给 LLM，只先做本地规则判断。

后续第二版再补控制通道，例如由 Supervisor 启动 Codex，
或要求被管理窗口运行在 tmux 等可控环境里。
