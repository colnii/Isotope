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
- 可选 `--llm-summary` 调用已配置 LLM 做中文智能摘要。

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

LLM 摘要：

```bash
export DEEPSEEK_API_KEY=你的_key
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner scan --limit 3 --llm-summary
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner watch --interval 180 --llm-summary
```

优先级：

- DeepSeek：优先读取 `ISOTOPE_LLM_API_KEY`、`DEEPSEEK_API_KEY`
  或 `YIFU_DEEPSEEK_API_KEY`，并复用 `src/isotope/llm/provider.py`
  里的 `DeepSeekChatProvider`。
- MiniMax：没有 DeepSeek key 时读取 `YIFU_MINIMAX_CODER_API_KEY`、
  `YIFU_MINIMAX_API_KEY`、`MINIMAX_API_KEY`、`MINIMAX_TOKEN`
  或 `MINIMAX_API_TOKEN`。

默认配置：

- DeepSeek base URL：默认 `https://api.deepseek.com`
- DeepSeek model：默认 `deepseek-v4-flash`
- MiniMax base URL：默认 `https://api.minimax.io/v1`
- MiniMax model：默认 `MiniMax-M2.7`
- 摘要 max tokens：默认 `512`

`--llm-summary` 只发送压缩后的会话摘要，不发送完整 session 文件。

## 当前边界

- 不接管普通终端窗口。
- 不自动给 Codex 发指令。
- 不直接检查 SSH 服务器内部进程。
- 不把完整日志发给 LLM，只发送短摘要和状态字段。

后续第二版再补控制通道，例如由 Supervisor 启动 Codex，
或要求被管理窗口运行在 tmux 等可控环境里。
