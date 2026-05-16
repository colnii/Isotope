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
| Codex 集成层 | 读取 Codex session（会话记录）、索引标题和 agent 元数据 | `features/supervisor/flow.py` | 当前读取本机 `.jsonl`、`session_index.jsonl` 和 SQLite |
| 扫描优化层 | 最近候选、首尾读取和标题兜底 | `features/supervisor/flow.py` | 避免每次页面刷新全量读历史 |
| tmux 集成层 | tmux 启动、`send-keys` 和 bell hook | `bell_events.py`、`flow.py`、`registry.py` | 只控制登记过的 tmux 会话 |
| 状态判断层 | 工作中、等待用户、疑似停住、疑似报错 | `features/supervisor/flow.py` | 规则判断，不等于模型判断 |
| 状态依据层 | `status_evidence` 说明每个状态标签的来源 | `features/supervisor/flow.py` | 避免只给结论、不说明证据 |
| 建议执行层 | `recommendation`、`command_suggestions`、`--execute` | `flow.py`、`runner.py` | 只允许白名单动作 |
| 模型管理层 | `LLM summary`、`LLM action` 和 TOML 号池 | `llm_summary.py` | 摘要和白名单动作建议 |
| 状态协议层 | `SUPERVISOR_STATUS` 等状态协议 | `flow.py`、`registry.py` | 给被托管 Codex 主动汇报状态 |
| 状态账本层 | lane state（窗口状态）和限频 | `lane_state.py` | 避免重复催促和刷屏 |
| 本地前端层 | `web`、`/dashboard.json`、`/managed/send`、`/llm-action` | `features/supervisor/web.py` | 本机视图、白名单发送和手动模型建议入口 |

## 已有轮子

- 读取本机 Codex `.jsonl` 会话记录。
- 读取 SQLite `threads.title` 和 `session_index.jsonl` 的标题。
- 解析匹配当前 session 的 `thread_name_updated`。
- 忽略 JSONL 中其他 thread id 的标题更新事件。
- 标题缺失时，使用首条用户消息截断标题，最后才退回短 hash。
- 扫描优先读取最近候选 session，不再默认全量解析历史 JSONL。
- 超过阈值的大 session 文件只读取开头和尾部。
- 读取 `agent_nickname` 和 `agent_role`，补充 agent 元数据。
- 识别工作中、等待用户、疑似停住、疑似报错、空闲和已退出。
- 每个状态带 `status_evidence`，说明来自状态协议、文本规则、超时、bell 或托管检查。
- 输出中文 plain 报告和 JSON 报告。
- `dashboard` 按需要看、已完成和工作中分组。
- `dashboard` 保留可读标题、短 hash、Codex 标题和 agent 元数据。
- `dashboard` 为每个窗口输出完整 `resume_command`。
- `web` 启动本机页面，复用 `dashboard` 分组 JSON。
- `web` 优先展示可读标题，同时保留短 hash 方便辨认窗口。
- `web` 可复制完整 `codex resume <session_id>`。
- `web` 可复制 attach/send 命令，也可对白名单 send 动作发起本机 POST。
- `web` 可手动请求 `/llm-action`，展示 LLM 白名单动作建议。
- `/managed/send` 成功发送后会更新 lane state。
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
- `--llm-action` 通过本机 TOML 号池选择一个白名单建议动作。

## 当前不要重复实现

- 不要在其他目录再建一套 Supervisor CLI。
- 不要绕过托管登记表直接写新的 tmux 发送器。
- 不要给 Supervisor 再造一套独立 LLM 号池。
- 不要另写状态分类系统，除非同步更新本文件。
- 不要只展示状态标签而不展示判断依据。
- 不要另写一套 dashboard 数据接口，先复用 `/dashboard.json`。
- 不要在 web 里放任意文本发送框；先走白名单动作。
- 不要让 `/llm-action` 自动调用 `/managed/send`。
- LLM 动作选择必须落到可审计的白名单能力上。

## 后续拆分方向

- `features/supervisor/status.py`：后续可下沉状态分类和状态依据生成。
- `features/supervisor/advice.py`：建议、命令草案和执行白名单。
- `features/supervisor/protocol.py`：后续可下沉状态协议解析和提示语注入。
- `features/supervisor/tmux_control.py`：后续可下沉 tmux 会话、发送和 bell hook。
- `features/supervisor/lane_state.py`：每个窗口的最近状态、催促次数和限频。
- `integrations/codex/session_reader.py`：后续可把 Codex `.jsonl` 读取下沉。

## 下一步顺序

1. 让模型建议在页面上高亮或预选对应按钮，仍由人类确认点击。
2. 后续再决定是否增加人工输入框；默认仍保持白名单。

## 登记规则

新增 Supervisor 能力时，至少同步：

- 本文件。
- [当前状态](./status.md)。
- [任务队列](./agent-task-queue.md)。
- 新术语或新命令还要同步 [术语索引](./terminology.md)。
