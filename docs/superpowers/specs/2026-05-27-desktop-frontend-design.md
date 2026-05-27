# Isotope Desktop Frontend Design

状态：`design review`

日期：2026-05-27

## 1. Purpose

Isotope 第一版桌面前端是 Windows-first 的通用 Supervisor / main agent
companion，不是网页 dashboard，也不是完整 IDE。

第一版必须验证一条薄但真实的产品闭环：

```text
Floating Orb -> MiniWindow -> MainWindow
             + real Supervisor / worker / event minimal chain
```

MVP 最低验收必须能展示真实 Supervisor snapshot。目标验收应完成一次
MiniWindow -> Supervisor 的最小真实交互。如果后端暂时不支持真实交互，
必须写 Backend Gap；mock 回复不能计入真实交互验收。

核心体验要求：

- 快速、省资源，不和电脑抢 CPU / GPU / memory。
- 简约，less is more，但不牺牲效率。
- 友好易用，不让用户迷路、不制造强打扰。
- 信息完整，agent 调用、上下文、证据和状态必须能追溯。
- 动效是体验硬要求，但动效必须服务状态理解和窗口连续性。

## 2. Reuse Audit

现有可复用边界：

- `src/isotope/features/supervisor/web.py`
  - 已有本地 dashboard server、`/dashboard.json`、`/events`、`/llm-action`、
    `/goal/add`、daemon/watcher control 等入口。
  - 可作为第一版真实 Supervisor snapshot 的来源之一，但不是最终桌面契约。
- `src/isotope/features/supervisor/state/projection.py`
  - 已提供 Supervisor state projection，聚合 active goals、decision requests、
    failed lanes、worker events 和 notifications。
  - 第一版应优先复用它来生成 desktop snapshot。
- `src/isotope/features/supervisor/commands/dashboard.py`
  - 已集中 dashboard payload、current batch、multi-worker read model 等视图数据。
  - 可做 adapter 输入，但不要让桌面 UI 直接绑定 dashboard 分组形状。
- `src/isotope/platform/state/*`
  - 已有 Supervisor snapshot、active goal、decision request、goal status、
    lane state、worker event summary 和 notification summary schema。
  - 桌面契约应尽量映射这些低敏 schema，而不是重造后端账本。
- `src/isotope/workspace/artifacts.py` 和 `src/isotope/platform/schemas/refs.py`
  - artifact 和 `ResourceRef` 边界已存在，桌面端只展示低敏 ref / summary。
- `src/isotope/apps/api.py` 与 `src/isotope/interfaces/http/`
  - 已有 API facade 和 HTTP 风格入口，可为后续 desktop API 聚合提供参考。

暂不直接复用或不作为最终契约：

- 不把现有 `/dashboard.json` 当作最终桌面前端 contract。
- 不把现有 bell `/events` 当作通用 agent event stream。
- 不把当前 Codex session / worker 二层结构硬编码成永久产品模型。
- 不为了迁就已有接口降低 orb / MiniWindow / MainWindow 的产品形态。

## 3. MVP Strategy

采用方案 C：双线最小闭环。

第一阶段同时验证两件事：

1. 桌面形态成立：
   - orb 常驻。
   - 点击展开 MiniWindow。
   - MiniWindow 可打开 MainWindow。
   - 有基本动效、置顶、透明、快捷键、窗口状态记忆。
2. Agent 产品形态成立：
   - MiniWindow 和 MainWindow 接入真实 Supervisor snapshot。
   - 至少展示 supervisor session 基本信息。
   - worker session / active goal 至少真实接入其中一类。
   - EventStream 可以先 derived / replay_mock，但必须符合最终 event contract。

第一版不做大而全工作台。每个区域可以很薄，但必须真实连通。

## 4. Scope

### Must Have

- Windows 10/11 可运行桌面应用。
- Floating Orb 可显示、拖动、点击打开 MiniWindow。
- Orb 支持头像、颜色、透明度基础配置。
- MiniWindow 可输入消息或命令。
- MiniWindow 至少展示真实 Supervisor snapshot 的最小状态。
- 如果 MiniWindow 支持输入提交，提交路径必须明确是 `real`、`mock` 或
  `disabled`。
- Mock 回复不能计入真实交互验收。
- MiniWindow 可最小化、关闭、打开 MainWindow。
- MiniWindow 打开 MainWindow 后默认收起到 orb；MiniWindow 被 pin 时保持显示。
- MainWindow 至少包含 ActivityTree / AgentTree、supervisor 对话或当前目标、
  EventStream。
- MainWindow 至少展示真实 supervisor session 基本信息。
- worker session / active goal 至少真实接入其中一类。
- EventStream 按最终 event contract 渲染。
- 所有 mock / replay_mock / derived 数据必须标注 `DataSourceInfo`。
- Backend Gap 必须逐模块记录，不能静默降级产品形态。

### Should Have

- Orb / MiniWindow 位置、大小、透明度、颜色、置顶模式持久化。
- 全局快捷键唤起 MiniWindow。
- MiniWindow Quick Action Area 支持 2-4 个最相关动作。
- `/` command menu。
- EventStream 支持 message、worker、tool、approval、artifact、error 核心事件。
- Approval / artifact / worker summary 入口或占位 card，标注 real/mock source。

### Later

- 复杂 evidence graph。
- 完整 artifact viewer。
- 完整 worker inspector。
- 完整 worker 管理控制台。
- 复杂独占全屏 / 游戏 overlay 保证。
- macOS / Linux 体验验收。
- 插件市场。
- 完整自定义快捷键系统。
- 重型主题系统。
- 多 agent 多 orb。

## 5. Technology Direction

技术路线暂定：

```text
apps/desktop/
  Tauri 2
  Svelte 5
  TypeScript
  SvelteKit SPA/static
  Tailwind CSS
  Svelte motion/transition first
  Motion library optional later
```

边界：

- Tauri/Rust 负责 window commands、global shortcuts、local settings、
  app lifecycle，以及可选 Python backend bridge。
- Python/Supervisor API 负责 snapshot、event replay、event stream、
  approval resolve 和 artifact refs。
- 前端统一通过 `isotopeClient`，组件里不直接散落 `fetch()` / `invoke()`。
- `isotopeClient` 下再分 `windowClient`、`agentClient`、`eventClient`、
  `settingsClient`。

第一版不重新争论 React / Electron / PWA。Electron 仅作为 Tauri 在关键
overlay 场景不可接受时的 Plan B。

## 6. Window And Motion Design

窗口系统由 Tauri/Rust window manager 与 Svelte UI 共同负责。

Svelte 处理窗口内部动效；Tauri/Rust 处理窗口创建、位置、透明度、置顶、
快捷键、焦点策略和状态持久化。窗口级动效不能只依赖前端动画库。

### Floating Orb

Must Have:

- 独立轻量窗口，默认常驻屏幕边缘附近。
- 支持拖动位置，松手后记住位置。
- 支持头像图像、颜色、透明度基础配置。
- 单击展开 MiniWindow。
- 当前状态徽标：`idle`、`running`、`needs_attention`、`error`。
- quiet mode / notification level 状态。
- 右键菜单：打开 MiniWindow、打开 MainWindow、通知设置、窗口设置、退出。

Should Have:

- 支持吸附屏幕边缘。
- 支持 unread / needs_attention 数量徽标。
- Hover tooltip 显示 current activity / active agent / active goal 摘要。

Notification policy:

- 默认低打扰。
- `approval_required` 默认不抢焦点，只进入 `needs_attention`。
- bell、pulse、toast、系统通知都可配置开启/关闭。
- 高风险 approval 可允许更强提醒，但必须尊重用户设置。
- quiet mode 下不 pulse、不放声音、不弹通知，只保留静态状态或小徽标。

### MiniWindow

Must Have:

- 小、轻、可拖动。
- 默认承载输入框、最近状态、最近回复或当前目标摘要。
- 右上角：最小化、打开 MainWindow、关闭。
- 左上角：置顶模式入口。
- 置顶模式切换以菜单为主；连续点击 3/4 次只作为高级快捷操作。
- 高级快捷操作必须有 toast / 状态反馈，不能作为唯一入口。
- 输入框聚焦、提交、等待回复、错误状态都有明确反馈。

Position behavior:

- MiniWindow 首次从 orb 附近出现。
- 用户拖动过 MiniWindow 后，记住 MiniWindow 自身位置。
- 下次点击 orb 时从 MiniWindow 上次位置打开。
- 如果位置因显示器变化、DPI 变化等原因失效，再回退到 orb 附近。

Open MainWindow behavior:

- MiniWindow 打开 MainWindow 后默认收起到 orb。
- 如果 MiniWindow 被 pin，则保持显示。

### MainWindow

第一版职责要薄：至少包含 ActivityTree / AgentTree、supervisor 对话或当前
目标、EventStream。Approval、artifact、worker 状态先做摘要入口或占位
card，不要求深做。

Default layout:

```text
MainWindow
├── Left Sidebar
│   ├── settings / workspace / search
│   └── ActivityTree / AgentTree
├── Main Content
│   ├── supervisor conversation
│   ├── current goal / mission summary
│   └── composer / command entry
└── Right Dock
    ├── EventStream
    ├── Approval summary
    ├── Artifact summary
    └── Worker / agent summary
```

Narrow layout:

```text
MainWindow
├── Left Drawer / collapsible sidebar
├── Main Content
└── Bottom Drawer
    └── EventStream / details panels
```

MainWindow 的 EventStream 默认在右侧。窗口较窄时降级成底部抽屉或可展开面板。

### Motion Acceptance

Must pass:

- Orb -> MiniWindow 展开不突兀。
- MiniWindow -> orb 收回有连续感。
- MiniWindow 首次从 orb 附近出现；用户拖动后记住自身位置；位置失效时回退到
  orb 附近。
- MainWindow Right Dock 展开/收起不造成主对话区闪烁。
- EventStream 新事件进入时使用轻量 slide/fade，高度变化不能造成整屏跳动。
- 连续事件批量到来时合并渲染节奏，避免列表抖动。
- `approval_required` 用明确但不刺眼的强调，默认不抢焦点。
- `error_reported` 醒目，但不能抢走输入焦点。
- `worker_started` / `worker_finished` 在 ActivityTree 上同步状态变化。
- reduced motion 开启后，保留状态变化，但关闭大部分位移和弹性动效。
- 动效不造成明显 CPU/GPU 占用异常。

Reduced motion:

- 提供应用内 reduced motion 设置。
- 尊重系统 `prefers-reduced-motion`。
- Reduced motion 下 orb pulse 降低或关闭。
- 窗口展开改为短 fade。
- 事件新增不做滑动。
- 面板切换不做弹性位移。
- Reduced motion 不能减少信息，只降低动效强度。

### EventStream Scroll Policy

- 默认跟随最新事件。
- 用户手动向上滚动后暂停自动跟随。
- 自动跟随暂停时，新事件只显示提示，不强制滚动。
- 点击提示后回到底部并恢复自动跟随。

## 7. Information Architecture

第一版信息架构原则：MiniWindow 用来快速介入，MainWindow 用来解释发生了什么。

### Orb

Orb 只显示最小状态，不展示复杂内容。

Information:

- Agent avatar。
- 状态徽标。
- Quiet mode / notification level。
- Current activity / active agent / active goal tooltip。

### MiniWindow

MiniWindow 是小而完整的快速入口，不是纯聊天气泡。

```text
MiniWindow
├── Header
│   ├── pin / priority mode
│   ├── current agent status
│   └── minimize / open main / close
├── Status Strip
│   ├── active activity / agent / goal
│   ├── running worker count
│   └── needs attention count
├── Conversation Preview
│   ├── last supervisor reply
│   └── latest user turn / command result
├── Composer
│   ├── input
│   └── submit / command trigger
└── Quick Action Area
    ├── slash command suggestions
    ├── answer approval
    ├── view events
    ├── open artifacts
    └── open main window
```

Quick Action Area 是输入框下半部分功能区。默认只显示 2-4 个最相关动作，避免挤满。

主入口顺序：

1. MiniWindow composer。
2. MainWindow composer。
3. `/` command menu。

辅助入口：

- Quick Action Area。
- Right Dock panel actions。
- ActivityTree context menu。

### ActivityTree / AgentTree

左侧概念使用 ActivityTree / AgentTree，不写死成 SessionTree。

第一版视觉可以渲染成：

```text
supervisor_session
├── worker_session
├── worker_session
└── active_goal / capability_run
```

但底层 contract 支持 `parentId`、`childIds`、`relatedRefs`、`sourceRef`，未来可扩展
graph / DAG。

First version:

- 展示 supervisor session 基本信息。
- worker session / active goal 至少真实接入其中一类。
- 节点状态徽标。
- 点击节点切换主区上下文。
- 展开/折叠记忆。

### Right Dock

Right Dock 默认显示 EventStream。其他内容先做摘要入口。

Must Have:

- EventStream。
- Approval summary card 或占位 card，标注 source。
- Artifact summary card 或占位 card，标注 source。
- Worker / agent summary card 或占位 card，标注 source。

Should Have:

- Panel tabs。
- Panel expand to full screen。
- Panel close / reopen。
- 事件点击后联动主区或 ActivityTree。

## 8. Data Contract

数据层分三类：

```text
Snapshot：当前状态
Event Stream：过程记录
Activity Projection：给 UI 展示的 agent/activity 关系视图
```

原则：

- `snapshot` 回答“现在是什么状态”。
- `event stream` 回答“发生过什么 / 正在发生什么”。
- `activity projection` 回答“agent、goal、worker、tool、artifact 之间怎么关联”。
- 前端可以 typed mock，但必须先定义未来真实 contract。
- 现有 `/dashboard.json`、Supervisor state projection 能复用，但不能当最终桌面契约。

### Types

```ts
type DataSourceKind = "real" | "mock" | "replay_mock" | "derived";

type ResourceRef = {
  kind:
    | "activity"
    | "session"
    | "agent"
    | "goal"
    | "event"
    | "artifact"
    | "approval"
    | "tool_call"
    | "capability_run";
  id: string;
  label?: string;
};

type DataSourceInfo = {
  kind: DataSourceKind;
  label: string;
  backendRef?: string;
  sourceRef?: ResourceRef;
  replacementCondition?: string; // human-readable only
  mockReason?: string;
  expectedRealContract?: string;
};

type ActivityNodeKind =
  | "supervisor"
  | "worker"
  | "agent"
  | "goal"
  | "capability_run"
  | "tool_call"
  | "artifact"
  | "group";

type ActivityStatus =
  | "idle"
  | "running"
  | "needs_attention"
  | "done"
  | "blocked"
  | "error"
  | "unknown";

type ActivityNode = {
  id: string;
  kind: ActivityNodeKind;
  title: string;
  status: ActivityStatus;
  source: DataSourceInfo;
  parentId?: string;
  childIds?: string[];
  relatedRefs?: ResourceRef[];
  sourceRef?: ResourceRef;
  order?: number;
  createdAt?: string;
  updatedAt?: string;
  summary?: string;
};

type ActivitySummary = {
  id: string;
  kind: ActivityNodeKind;
  title: string;
  status: ActivityStatus;
  source: DataSourceInfo;
};

type AgentSummary = {
  id: string;
  title: string;
  status: ActivityStatus;
  kind?: "supervisor" | "worker" | "agent";
  role?: string;
  source: DataSourceInfo;
  updatedAt?: string;
};

type GoalSummary = {
  id: string;
  title: string;
  status: ActivityStatus;
  source: DataSourceInfo;
  updatedAt?: string;
};

type ApprovalSummary = {
  id: string;
  title: string;
  status: "pending" | "resolved" | "expired";
  riskLevel?: "low" | "medium" | "high";
  source: DataSourceInfo;
};

type ArtifactSummary = {
  id: string;
  title: string;
  artifactRef: ResourceRef;
  source: DataSourceInfo;
};

type ToolCallSummary = {
  id: string;
  toolName: string;
  status: "running" | "success" | "failed" | "cancelled" | "unknown";
  source: DataSourceInfo;
};

type SnapshotCounts = {
  runningAgents: number;
  needsAttention: number;
  approvals: number;
  artifacts: number;
  errors: number;
};

type IsotopeSnapshot = {
  schemaVersion: 1;
  snapshotId: string;
  generatedAt: string;
  eventCursor?: string;
  lastEventId?: string;
  source: DataSourceInfo;
  activeActivity?: ActivitySummary;
  activeAgent?: AgentSummary;
  activeGoal?: GoalSummary;
  counts: SnapshotCounts;
  agents: AgentSummary[];
  activities: ActivityNode[];
  approvals: ApprovalSummary[];
  artifacts: ArtifactSummary[];
  runningToolCalls: ToolCallSummary[];
};

type BaseEvent = {
  id: string;
  eventCursor?: string;
  createdAt: string;
  source: DataSourceInfo;
  activityId?: string;
  agentId?: string;
  parentEventId?: string;
  relatedRefs?: ResourceRef[];
  severity?: "info" | "success" | "warning" | "error";
  title: string;
  summary?: string;
  payloadPreview?: unknown; // debug/detail only
};

type IsotopeEvent =
  | (BaseEvent & {
      type: "message_created";
      payload: {
        messageId: string;
        role: "user" | "assistant" | "system" | "tool";
        preview: string;
      };
    })
  | (BaseEvent & {
      type: "worker_started";
      payload: { workerId: string; workerTitle: string };
    })
  | (BaseEvent & {
      type: "worker_finished";
      payload: {
        workerId: string;
        result: "done" | "blocked" | "failed" | "cancelled" | "unknown";
      };
    })
  | (BaseEvent & {
      type: "tool_call_started";
      payload: { toolCallId: string; toolName: string };
    })
  | (BaseEvent & {
      type: "tool_call_finished";
      payload: {
        toolCallId: string;
        toolName: string;
        result: "success" | "failed" | "cancelled" | "unknown";
      };
    })
  | (BaseEvent & {
      type: "approval_required";
      payload: {
        approvalId: string;
        riskLevel?: "low" | "medium" | "high";
        promptPreview: string;
      };
    })
  | (BaseEvent & {
      type: "approval_resolved";
      payload: {
        approvalId: string;
        resolution: "approved" | "denied" | "expired" | "cancelled";
      };
    })
  | (BaseEvent & {
      type: "artifact_created";
      payload: { artifactRef: ResourceRef };
    })
  | (BaseEvent & {
      type: "error_reported";
      payload: { errorCode?: string; message: string };
    })
  | (BaseEvent & {
      type: "snapshot_updated";
      payload: { snapshotId?: string; eventCursor?: string };
    });

type EventReplayResponse = {
  events: IsotopeEvent[];
  nextCursor?: string;
  hasMore: boolean;
};
```

### Data Rules

- `schemaVersion = 1` 第一版固定。
- 破坏性变更必须升级 schema version。
- 不得在同一 schema version 下修改字段语义。
- `snapshotId` 是一次生成出来的 snapshot 的唯一不可变 ID。
- 每次重新生成 snapshot 应产生新的 `snapshotId`。
- `eventCursor` 是 snapshot 与 event stream 对齐的主字段。
- `lastEventId` 只是 SSE/EventSource 兼容字段。
- 如果两者都存在，前端优先使用 `eventCursor`。
- 如果 event id 本身可作为 cursor，可以令 `eventCursor = lastEventId = event.id`。
- `payloadPreview` 只能用于 debug / 展开详情；核心 UI 渲染必须依赖 typed payload。
- Preview / summary data 默认必须低敏。
- `payloadPreview`、`summary`、`promptPreview` 不应默认包含完整 tool args、
  secret、token、私密文件内容或大段上下文。
- 需要查看完整内容时，应通过显式展开、权限检查或后端 `ResourceRef` 读取。
- `derived` 必须能追溯到真实 `backendRef` 或 `sourceRef`。
- 不能用 `derived` 包装纯 mock。
- `replacementCondition` 只给人看，不作为程序逻辑判断。

### Event Replay And SSE

Replay:

- `GET /events?cursor=<cursor>` 返回 cursor 之后的事件。
- 返回结果不包含 cursor 对应事件，语义为 exclusive after cursor。
- 支持 `GET /events?cursor=<cursor>&limit=<n>`。
- 响应使用 `EventReplayResponse`。

SSE:

- 首次连接：`GET /events/stream?cursor=<eventCursor>`。
- 服务端 SSE 每条事件必须发送 `id`。
- SSE `id = event.eventCursor ?? event.id`。
- 如果 `event.id` 可作为恢复游标，`eventCursor` 可省略。
- 如果 `event.id` 只是稳定 UUID，不保证顺序，则必须提供 `eventCursor`。
- 前端保存 cursor 时使用 `event.eventCursor ?? event.id`。
- 浏览器 `EventSource` 断线自动重连时，会复用原 URL，并自动携带
  `Last-Event-ID`。
- Query cursor 和 `Last-Event-ID` 同时存在时，不能无条件 query cursor 优先。
- 如果 cursor 可比较，服务端取更靠后的 cursor。
- 如果 cursor 不可比较，在 `EventSource` 自动重连场景下优先使用
  `Last-Event-ID`。
- Query cursor 主要用于首次连接或前端手动重新建立连接。
- 不假设前端能手动给原生 `EventSource` 设置 `Last-Event-ID` header。
- 第一版默认 local-only / trusted localhost。
- 如果后续需要认证，不要假设原生 `EventSource` 可以任意设置 custom headers。
- 可选策略包括 same-origin cookie、短期 query token、Tauri/Rust proxy、
  或 fetch-based SSE client。

第一版如果没有真实 SSE，可用 `replay_mock`，但不能伪装成实时真实流。

### Activity Ordering

- 同一 parent 下优先按 `order` 排。
- 没有 `order` 按 `createdAt`。
- 再没有按 `title/id` 稳定排序。
- 前端刷新不能让树节点无故跳动。

## 9. Backend Gap Protocol

前端开发中发现后端对不上，不允许静默降级产品形态，也不允许随手 mock。
必须写 Backend Gap。

```text
Backend Gap: <module / feature>

Frontend needs:
- 前端为了完成产品体验需要什么数据、接口、事件或能力。

Current backend mismatch:
- 当前后端缺什么，或现有接口为什么不适配。

Proposed contract:
- 建议后端提供的 endpoint、event、字段、状态或 action。

Blocking level:
- blocking：没有它 MVP 无法验收。
- partial：可以用 typed mock 推进，但必须替换。
- later：不影响 MVP，只记录后续需求。

Temporary mock boundary:
- 是否允许 mock。
- mock 数据源是什么。
- mock 必须标什么 source。
- 替换真实能力的条件是什么。
```

### WindowManager

- Blocking level: `blocking`。
- Frontend needs:
  - Orb、MiniWindow、MainWindow 多窗口创建。
  - 位置记忆、透明度、置顶、全局快捷键、focus 策略。
- Current backend mismatch:
  - Python Supervisor 后端不负责系统窗口。
- Proposed contract:
  - Tauri window commands + persisted window settings。
- Temporary mock boundary:
  - 设置 UI 可 mock。
  - 真实窗口行为必须由 Tauri spike 验证，不能用 mock 替代。

### MiniWindow

- Blocking level: `partial`。
- Frontend needs:
  - 当前 activity / agent / goal 摘要。
  - 最近 reply。
  - needs_attention count。
  - 命令提交路径。
- Current backend mismatch:
  - 现有 dashboard payload 偏 dashboard 分组，不是 mini summary contract。
- Proposed contract:
  - `GET /snapshot` 或 Tauri invoke 返回 `IsotopeSnapshot` 的 mini-safe 子集。
- Temporary mock boundary:
  - 最近 reply 和 quick actions 可 mock。
  - Active Supervisor snapshot 必须真实。
  - MiniWindow 输入提交路径必须标明 `real`、`mock` 或 `disabled`。

### ActivityTree / AgentTree

- Blocking level: `partial`。
- Frontend needs:
  - 通用 activity nodes，支持 supervisor、worker、goal、capability、tool、
    artifact。
- Current backend mismatch:
  - 现有结构偏 Codex session / managed worker，不是通用 activity projection。
- Proposed contract:
  - `ActivityNode[]` projection，支持 `parentId`、`childIds`、`relatedRefs`、
    `sourceRef`。
- Temporary mock boundary:
  - 可从真实 Supervisor snapshot 派生最小 supervisor/worker 或 goal nodes。
  - 缺失 node kind 先 mock 并标 source。

### EventStream

- Blocking level:
  - MVP 阶段：`partial`。
  - Real-time 阶段：`blocking`。
- Frontend needs:
  - 统一事件流和 replay，支持核心事件类型。
- Current backend mismatch:
  - 现有 `/events` 更偏 bell / refresh，不等于通用 agent event stream。
- Proposed contract:
  - `GET /events?cursor=&limit=` replay。
  - SSE `/events/stream?cursor=`。
  - 事件形状为 `IsotopeEvent`。
- Temporary mock boundary:
  - MVP 可用 derived / replay_mock，但必须符合最终 event contract。
  - Replay/mock 不能伪装成实时真实流。

### Approval

- Blocking level:
  - MVP 默认 `later`。
  - 如果现有 Supervisor decision request 可读，则为 `partial`。
- Frontend needs:
  - `approval_required` / `approval_resolved` 事件。
  - Approval summary。
  - 回答入口。
- Current backend mismatch:
  - Supervisor decision request 已有，但通用 approval gate 可能未统一。
- Proposed contract:
  - Approval summary + resolve action。
  - 第一版优先把 decision request 映射为 `approval_required`。
- Temporary mock boundary:
  - Approval card 可占位。
  - 不允许伪造高风险 approval。

### Artifact

- Blocking level:
  - MVP 默认 `later`。
  - 如果现有 artifact summary 可读，则为 `partial`。
- Frontend needs:
  - `artifact_created` 事件。
  - Artifact summary。
  - 低敏 `ResourceRef`。
- Current backend mismatch:
  - 后端已有 artifacts，但 Supervisor dashboard 未必暴露完整前端所需摘要。
- Proposed contract:
  - Artifact summary list + ref read endpoint。
- Temporary mock boundary:
  - Artifact card 可占位。
  - 可展示低敏 `ResourceRef`。
  - 不展示假全文。

### MainWindow

- Blocking level: `partial`。
- Frontend needs:
  - 同时拿 snapshot、activity projection、event list，并能切换节点上下文。
- Current backend mismatch:
  - 当前可能需要多个旧接口拼接。
- Proposed contract:
  - Desktop snapshot endpoint 聚合最小 UI 所需。
- Temporary mock boundary:
  - 布局和空状态可 mock。
  - 真实 supervisor session 信息必须接入。
  - Approval / artifact / worker summary 第一版可以是摘要入口或占位 card。

## 10. MVP Acceptance

MVP 目标：

用户能从 orb 进入 Isotope，用 MiniWindow 查看真实 Supervisor 状态，目标上完成一次
MiniWindow -> Supervisor 的最小真实交互，再打开 MainWindow 看到这次活动背后的
ActivityTree 和 EventStream。

如果后端暂时不支持真实交互，必须明确标为 Backend Gap。Mock 回复不能计入真实交互验收。

### Must Pass

- Windows 10/11 桌面 app 可启动。
- Orb 可显示、拖动、点击打开 MiniWindow。
- MiniWindow 可输入消息/命令。
- MiniWindow 至少展示真实 Supervisor snapshot。
- 如果 MiniWindow 输入提交启用，提交路径必须标明 `real`、`mock` 或 `disabled`。
- MiniWindow 可打开 MainWindow；默认收起到 orb，pin 时保持显示。
- MainWindow 显示 ActivityTree / AgentTree。
- MainWindow 至少展示真实 supervisor session 基本信息。
- Worker session / active goal 至少真实接入其中一类。
- EventStream 按最终 event contract 渲染。
- EventStream 如果为 mock / replay，source 明确标识。
- EventStream 自动滚动策略正确。
- Reduced motion 设置可用。
- Approval / artifact / worker summary 可以是占位或摘要入口，但必须标明 source。
- 所有 mock 都有 `DataSourceInfo.kind` 和替换条件。
- 发现后端缺口必须写 Backend Gap，不能静默改产品形态。

### Event Contract Tests

- 从 `snapshot.eventCursor` 后 replay，不重复 snapshot 已覆盖事件。
- SSE 断线自动重连后，不从初始 query cursor 重放旧事件。
- `event.id` 为 UUID 且 `eventCursor` 单独存在时，前端保存和服务端恢复都使用
  `eventCursor`。

### Window / Motion Tests

- Orb -> MiniWindow 展开不突兀。
- MiniWindow -> orb 收回有连续感。
- MiniWindow 首次从 orb 附近出现。
- 用户拖动 MiniWindow 后记住自身位置。
- MiniWindow 位置失效时回退到 orb 附近。
- MainWindow Right Dock 展开/收起不闪烁。
- `approval_required` 默认不抢焦点，只进入 `needs_attention`。
- Quiet mode 下不 pulse、不放声音、不弹通知。
- 动效不造成明显 CPU/GPU 占用异常。

### Keyboard / Focus Tests

- 全局快捷键唤起 MiniWindow 后，composer 默认聚焦。
- MiniWindow 关闭或收起后，焦点尽量返回原应用，不强行抢焦点。
- 置顶模式菜单、Quick Action Area、`/` command menu 可键盘操作。
- MainWindow 打开后，Tab 顺序不混乱。

### Windows Overlay Spike

Windows overlay spike 独立并行，不阻塞 MVP。

验证项：

- 普通窗口置顶。
- Borderless fullscreen 可见性。
- 多显示器与 DPI 缩放。
- Global shortcut。
- 透明窗口和拖动。
- 不抢焦点 / 可配置抢焦点。
- CPU/GPU 占用。
- 独占全屏记录兼容性结论和 fallback。

## 11. Non-Goals

第一版不做：

- 完整 IDE。
- 完整 artifact viewer。
- 完整 evidence graph。
- 完整 worker 管理控制台。
- 完整多平台体验验收。
- 独占全屏强 overlay 保证。
- 复杂插件系统。
- 重型企业后台风格组件库。

## 12. Next Step

用户 review 本设计文档后，再进入 implementation plan。

计划应拆成小阶段：

1. Desktop scaffold and window manager spike。
2. Snapshot adapter and typed frontend contract。
3. Orb + MiniWindow thin loop。
4. MainWindow ActivityTree + EventStream。
5. Backend Gap report pass。
6. Windows overlay spike report。
