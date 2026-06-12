# Desktop Suprematist Redesign Design

Date: 2026-06-13

## Goal

统一改版 `apps/desktop` 的视觉系统和主要桌面界面，让 Isotope Desktop
从当前的白底线框原型感，升级成信息效率更高、视觉记忆更明确的本地 AI
工程工作台。

本次设计采用「对话优先的现代工作台 + 明确至上主义引用」：

- 对话仍是主轴，用户首先看到自己问了什么、Isotope 做了什么、结果是什么。
- 状态、审批、成员、能力结果要更容易一眼扫出。
- 视觉引用至上主义的米白纸面、黑线、红黄蓝几何块和非对称构图。
- 装饰不能抢走内容，不做海报化全屏背景、大面积渐变或纯艺术化界面。

成功标准排序：

1. 信息效率最高：状态、成员、审批、能力结果更容易快速判断。
2. 日常舒服耐看：长时间使用不累。
3. 有明确品牌记忆点：不是通用 AI 紫蓝渐变风。

## Scope

本次改版覆盖整套 desktop 前端视觉，而不是只给聊天页换皮。

主路径：

- `主管聊天`：`MainWindowShell`、`ConversationWorkspace`、
  `CapacityCallCard`、`CapacityCallDetails`、`CommandComposer`。
- `智能体群聊` 当前入口：`AgentWorkspaceShell` 及其 sidebar、pane、
  composer、inspector、session picker。

旁路但需要统一：

- `MiniWindow`。
- `AgentGroupWorkspace` 及其 member strip、stream、private chat、
  transcript panel。
- `DevDiagnosticShell`、`MainWindowSnapshotShell`、`EventStream`、
  `ActivityRail`、`InspectorDock`。

共享基础：

- `tailwind.config.ts` 的 `isotope` 色票。
- `app.css` 的全局字体、背景、基础控件规则。
- 共享按钮、输入、卡片、状态 badge、对话气泡和详情卡视觉规则。

## Non-Goals

- 不改后端 contract、SSE 事件、能力调用、审批、artifact、workspace 数据流。
- 不把 Desktop chat 变成固定工作流、意图分类器或规则路由器。
- 不为了视觉统一删除现有能力卡的折叠、滚动、全屏和关闭入口。
- 不把复杂 transcript、raw event 或长文本常驻摊开在主对话流里。
- 不新增大依赖或图标库，除非实现阶段确认它能明显降低维护成本。
- 不在这一轮重写所有交互模型。旁路界面优先统一视觉和层级，避免扩大成多套产品重构。

## Reuse Audit

复用：

- 现有 Svelte 5 + Tailwind 架构。
- `tailwind.config.ts` 里的 `isotope` token 入口。
- 现有组件边界：主聊天、Agent workspace、mini、agent group、dev shell
  继续各自负责自己的数据和交互。
- `ConversationWorkspace` 里的对话流和审批入口。
- `CapacityCallCard` 的能力结果展示、默认折叠、详情全屏和截图 artifact 操作。
- `CommandComposer` / `AgentConversationComposer` 的提交行为。
- `AgentWorkspaceShell` 现有三块职责：导航、对话、成员/会话 inspector。
- `windowSurface.ts` 的 surface class 入口。

不复用为最终形态：

- 当前纯白底、浅灰边框、蓝色主按钮的临时视觉。
- `AgentWorkspaceShell` 的三栏常驻压迫感。新视觉应让中间对话更主导，
  上下文层按状态收敛或展开。
- 旁路组件里散落的 `bg-white`、`border-isotope-line`、硬编码
  `#f6f7f9`、`#eef2f6` 等局部样式。它们应逐步回到统一 token。

## Product Shape

桌面端统一成「对话主轴 + 状态上下文层」。

`主管聊天`：

- 保持单列对话主轴。
- 顶部只显示模式、标题和必要状态。
- 用户消息、AI 消息、能力卡、审批卡、错误卡都在同一条叙事流里。
- 能力卡默认折叠，只露出标题、状态、摘要和关键产物；详情可展开、
  滚动、全屏、关闭。
- 审批卡必须有明确批准/拒绝入口，不能只显示等待状态。

`智能体群聊 / AgentWorkspaceShell`：

- 中间对话主轴最明显。
- 左侧 workspace/channel 导航和右侧成员/Transcript/设置是上下文层。
- 空闲时上下文层收敛：窄、低对比，只显示对象、计数和关键状态。
- 运行中上下文层展开或强调：成员状态、运行状态、queue/interrupt/stop
  动作更清楚。
- 有审批、错误、成员异常时，用红/黄/蓝几何状态块把风险拉出来。
- 长 transcript 和 raw 内容进入详情卡、抽屉或 bounded scroll 区域，不常驻压满页面。

`MiniWindow`：

- 是浓缩对话入口，不承载复杂管理。
- 显示最近问答、当前状态和打开主窗口动作。
- 使用同一套纸面、黑线、几何状态块，但密度更低。

`AgentGroupWorkspace` 与 dev/snapshot 旁路界面：

- 统一色票、线条、按钮、卡片和状态层级。
- 保留现有结构，先不追求和主入口完全同构。
- 重点是让它们不再像另一套产品。

## Visual System

色彩：

- `paper`: 米白/纸白主背景，替代刺眼纯白。
- `panel`: 内容纸面，略高于背景。
- `ink`: 近黑主文本和结构线。
- `muted`: 灰褐辅助文字。
- `line`: 浅线，用于卡片内部边界。
- `red`: 风险、错误、拒绝、需要用户拍板。
- `yellow`: 等待、注意、运行中但未失败。
- `blue`: 用户消息、主要动作、正在执行的能力。
- `green`: 仅少量用于完成状态，不成为主视觉家族。

形态：

- 控件以 4-6px 小圆角或直角为主，沿用现有 `borderRadius.panel = 6px`。
- 黑线负责工作台骨架，浅线负责内容分组。
- 状态强调用小几何块、侧边色条、角标、斜切/错位小块，而不是整卡染色。
- 允许少量非对称块作为标题区或状态区记忆点，但不使用离散装饰圆球、
  bokeh、紫蓝 AI 渐变或玻璃拟态。

文字：

- 保持界面文字紧凑、可扫。
- 标题不做过大的 hero 字号，工作台内标题应服务信息结构。
- 英文实现名只在必要处出现；用户可见主要文案继续中文优先。

## Component Rules

按钮：

- 主动作使用蓝色或黑线强调。
- 危险/拒绝使用红色。
- 等待/运行提示使用黄色或蓝色状态块，不让按钮语义混乱。
- 禁用态保持可读，不只靠透明度。

输入：

- 输入区固定高度和边界，focus 状态明确但克制。
- Composer 是对话主轴的底部锚点，不应被侧栏视觉抢走。

卡片：

- 卡片边界清晰，背景以 paper/panel 为主。
- 重要卡片可使用左侧色条或几何角标。
- 不使用卡套卡的装饰层级；嵌套内容用边线、间距和标题区区分。

消息：

- 用户消息蓝色，AI 消息纸白。
- AI 消息里的能力卡、审批卡和错误卡要能被快速区分。
- Provider/model 元信息保持低优先级。

能力卡：

- 默认折叠。
- 第一屏展示：状态、能力标题、摘要、关键产物入口。
- 详情区 bounded scroll，可全屏，可关闭。
- `screen.observe` 等 artifact 操作保留原图、文件夹、下载入口。

状态层：

- `running`、`needs approval`、`error`、`done` 不能只靠文案区分。
- 状态色块必须和文字同时存在，满足快速扫视和可访问性。

## Implementation Strategy

实现应分阶段完成，避免一次性搅动所有 Svelte 组件。

1. 创建独立 branch/worktree。
2. 建立视觉基础：
   - 更新 `tailwind.config.ts` 的 `isotope` token。
   - 更新 `app.css` 的全局字体、背景、基础控件。
   - 如有必要，新增少量共享 CSS utility，避免每个组件重复写复杂 class。
3. 改主聊天路径：
   - `ConversationWorkspace`。
   - `CapacityCallCard` / `CapacityCallDetails`。
   - `CommandComposer`。
4. 改智能体群聊当前入口：
   - `AgentWorkspaceShell`。
   - `AgentWorkspaceSidebar`。
   - `AgentConversationPane`。
   - `AgentConversationComposer`。
   - `AgentChannelInspector`。
   - `CodexSessionPicker`。
5. 扫旁路界面：
   - `MiniWindow`。
   - `AgentGroupWorkspace` 相关组件。
   - `DevDiagnosticShell`。
   - snapshot、event、activity、inspector 小组件。
6. 观察截图并修正重叠、溢出、文字层级和状态对比。

如果实现阶段需要给 `AgentWorkspaceShell.svelte` 添加非样式逻辑，而文件继续
超过 500 行，应先按职责拆分。纯样式替换可以暂不拆，但不能继续追加无关逻辑。

## Testing And Validation

自动验证：

- `npm run check`
- `npm run test`
- `npm run build`

桌面观察：

- 先运行 `npm run observe:desktop -- --plan` 确认本机可用观察路径。
- 能跑真实 desktop 时，用现有 observe/CDP/screenshot 路径检查主窗口。
- Windows/Tauri 原生 smoke 如果受环境限制，记录阻塞命令和输出。

视觉验收场景：

- 主管聊天空态。
- 主管聊天有用户消息和 AI 消息。
- 能力卡 running / done / error。
- 审批卡待批准、批准中、错误。
- 智能体群聊空闲态：上下文层收敛。
- 智能体群聊运行中：成员/状态/queue/interrupt/stop 明显。
- 智能体群聊错误或成员异常。
- MiniWindow。
- AgentGroupWorkspace。
- DevDiagnosticShell 或 snapshot shell。

质量要求：

- 没有明显文字溢出、按钮挤压、卡片重叠。
- 状态不能只靠颜色传达。
- 对话主轴不被装饰抢走。
- 旁路界面和主界面属于同一套产品。
