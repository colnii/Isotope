# Codex Supervisor 能力地图

状态：`当前能力登记 / 防止重复造轮子`

## 为什么要有这张图

Codex Supervisor 已经不只是一个小命令。
它是 Isotope 后续的核心管理层：LLM 参与判断和调度，
规则、事件、冷却、tmux 和白名单执行提供工程护栏。

本文件用于登记当前能力和后续拆分方向。
新增 Supervisor 能力时，应先看这里，避免重复造一套相似实现。

## 当前分层

| 层级 | 当前能力 | 主要位置 | 说明 |
| --- | --- | --- | --- |
| 用户功能层 | `scan`、`dashboard`、`web`、`watch`、`advise`、`supervise` | `features/supervisor/runner.py` | 面向人类使用的命令入口 |
| 托管控制层 | `launch`、`adopt`、`send`、托管登记 | `features/supervisor/registry.py` | 管理 Supervisor 登记的 Codex |
| Codex 集成层 | 读取 Codex session（会话记录） | `features/supervisor/flow.py` | 当前直接读取本机 `.jsonl` |
| tmux 集成层 | tmux 启动、`send-keys` 和 bell hook | `bell_events.py`、`flow.py`、`registry.py` | 只控制登记过的 tmux 会话 |
| 状态判断层 | 工作中、等待用户、疑似停住、疑似报错 | `features/supervisor/flow.py` | 规则判断，不等于模型判断 |
| 建议执行层 | `recommendation`、`command_suggestions`、`--execute` | `flow.py`、`runner.py` | 只允许白名单动作 |
| 模型管理层 | `LLM summary` 和 TOML 号池 | `llm_summary.py` | 当前先做摘要，后续承担白名单内动作选择 |
| 状态协议层 | `SUPERVISOR_STATUS` 等状态协议 | `flow.py`、`registry.py` | 给被托管 Codex 主动汇报状态 |
| 状态账本层 | lane state（窗口状态）和限频 | `lane_state.py` | 避免重复催促和刷屏 |
| 本地前端层 | `web` 和 `/dashboard.json` | `features/supervisor/web.py` | 先做本机可视化薄入口 |

## 已有轮子

- 读取本机 Codex `.jsonl` 会话记录。
- 识别工作中、等待用户、疑似停住、疑似报错、空闲和已退出。
- 输出中文 plain 报告和 JSON 报告。
- `dashboard` 按需要看、已完成和工作中分组。
- `web` 启动本机页面，复用 `dashboard` 分组 JSON。
- `watch --changes-only` 只在状态变化时输出。
- 本机托管登记表 `managed_sessions.jsonl`。
- `launch` 支持普通进程和 tmux 会话。
- `adopt` 可接管已存在的 tmux 会话。
- `send` 支持向登记过的 tmux 会话发送文本。
- `scan` 可识别托管 tmux 会话的 bell（提醒）信号。
- `launch/adopt` 会安装 tmux `alert-bell` hook。
- bell hook 会写入 `bell_events.jsonl`，让提醒不只依赖轮询。
- `launch` 会注入 `SUPERVISOR_STATUS/SUMMARY/NEXT` 汇报要求。
- `scan` 会从 Codex `.jsonl` 解析状态协议字段。
- `scan --json` 输出结构化建议。
- `SUPERVISOR_STATUS=blocked/done/needs_user` 会影响结构化建议。
- bell 事件会让建议优先提示查看对应托管窗口。
- `advise` 输出建议和命令草案。
- `--execute` 只执行 `send_status` 和 `send_continue`。
- `supervise` 循环执行扫描、建议、摘要和显式发送。
- lane state 记录最近状态、最近催促时间和催促次数。
- `--prompt-cooldown` 可避免短时间重复催促同一个 lane。
- `--llm-summary` 通过本机 TOML 号池生成中文摘要。

## 当前不要重复实现

- 不要在其他目录再建一套 Supervisor CLI。
- 不要绕过托管登记表直接写新的 tmux 发送器。
- 不要给 Supervisor 再造一套独立 LLM 号池。
- 不要另写状态分类系统，除非同步更新本文件。
- 不要另写一套 dashboard 数据接口，先复用 `/dashboard.json`。
- LLM 动作选择必须落到可审计的白名单能力上。

## 后续拆分方向

- `features/supervisor/advice.py`：建议、命令草案和执行白名单。
- `features/supervisor/protocol.py`：后续可下沉状态协议解析和提示语注入。
- `features/supervisor/tmux_control.py`：后续可下沉 tmux 会话、发送和 bell hook。
- `features/supervisor/lane_state.py`：每个窗口的最近状态、催促次数和限频。
- `integrations/codex/session_reader.py`：后续可把 Codex `.jsonl` 读取下沉。

## 下一步顺序

1. 给本地页面补受控操作按钮，先只生成命令或调用 send 白名单。
2. 讨论 LLM 在白名单内选择动作的策略和提示词。

## 登记规则

新增 Supervisor 能力时，至少同步：

- 本文件。
- [当前状态](./status.md)。
- [任务队列](./agent-task-queue.md)。
- 新术语或新命令还要同步 [术语索引](./terminology.md)。
