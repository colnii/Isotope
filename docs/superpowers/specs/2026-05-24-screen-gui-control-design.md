# Screen GUI Control Design

状态：`draft for user review`

日期：2026-05-24

## 1. Purpose

第一版目标是让 Isotope 拥有泛用 GUI agent 能力：能观察桌面/窗口，理解当前屏幕状态，并在人类授权下执行鼠标键盘操作。

这个能力面向开发工具、浏览器、普通桌面软件、游戏窗口等 GUI 应用。它不是某个单一应用的专用脚本，也不是通过读取进程内存、注入客户端或绕过平台检测来获得隐藏状态。

第一版采用跨平台 contract（契约），Windows backend（后端适配器）先实现。macOS / Linux 后续通过同一 contract 增加 backend。

## 2. Reuse Audit

复用现有边界：

- `src/isotope/platform/registry/actions.py`
  - 继续作为 model-facing tool metadata（面向模型的工具元数据）和 required capabilities（所需能力）的来源。
  - 新增 `screen_observe` / `screen_control` 工具条目，不另建第二套 registry。
- `src/isotope/policy/__init__.py`
  - 继续由 `PolicyEngine` 根据 proposal 和 registry 发放 `PolicyDecision.grants`。
  - GUI 能力必须通过 allow list、approval_required 和 budget 约束，LLM 判断不能绕过。
- `src/isotope/execution/executor.py`
  - 继续作为授权动作的唯一执行入口。
  - GUI 执行结果必须走 artifact 和 canonical event log。
- `src/isotope/execution/terminal_backend_adapter.py`
  - 复用其 adapter 模式：backend 返回结构化结果，adapter 负责验证 grants、创建 artifact、压低 read model 暴露面。
- `src/isotope/workspace/artifacts.py`
  - 复用 artifact store 存截图、metadata、动作结果和错误诊断。
- `tests/isotope/test_controlled_terminal_execution.py`
  - 复用测试风格：先测 registry / policy / executor / artifact / approval 端到端边界。

不复用或不直接扩展的部分：

- 不把 GUI 能力塞进 `CapabilityRunner` 真实执行路径。`CapabilityRunner` 当前是 deterministic capability runner（确定性能力运行器），适合能力发现和低敏 demo，不适合高权限屏幕控制。
- 不把 GUI backend 写成零散脚本。真实 observe/control 必须通过 `submit_action -> PolicyDecision.grants -> Executor -> artifact/event`。
- 不直接依赖 UI Automation 或 app-specific API 作为第一能力面。它们可作为后续非侵入模式增强，但不能覆盖游戏/高频渲染窗口的通用场景。

## 3. Product Shape

第一版包含两个工具：

### 3.1 `screen_observe`

观察窗口或屏幕目标，尽量不干扰人类当前操作。

输入：

- `target_selector`: 目标选择器，例如进程名、窗口标题包含文本、窗口 id。
- `mode`: `non_intrusive` 或 `interactive`。
- `capture`: 希望采集的内容，例如 `screenshot`、`metadata`。

输出：

- `status`: `captured`、`metadata_only`、`not_observable`、`failed`。
- `target`: 实际匹配的窗口摘要。
- `artifact_refs`: 截图、metadata 或诊断 artifact。
- `diagnostics`: 低敏失败原因，例如窗口最小化、截图后端不可用。

最小化窗口规则：

- 如果窗口最小化且截图不可用，不伪造成成功截图。
- 降级读取 metadata。
- 返回可恢复建议，例如 `restore_window_requires_approval`。

### 3.2 `screen_control`

对 GUI 目标执行真实输入或 dry-run（空跑）计划。

输入：

- `target_selector`: 目标选择器。
- `mode`: `non_intrusive` 或 `interactive`。
- `execution_mode`: `dry_run` 或 `execute`。
- `actions`: 鼠标键盘事件序列。

动作类型第一版支持：

- `move`
- `button_down`
- `button_up`
- `click`
- `wheel`
- `key_down`
- `key_up`
- `key_press`

后续可扩展：

- long press（长按）
- drag gesture（拖动手势）
- horizontal wheel（横向滚轮）
- side buttons（鼠标前后侧键）

这些后续动作风险更高，默认必须审批或命中更窄 allow list。

## 4. Permission Model

人类权限永远高于 LLM 判断。

优先级：

1. 人类手动接管。
2. 人类暂停 / 停止。
3. 明确 allow list。
4. LLM action proposal。

模式：

- `manual`: 人类手动操作，LLM 只能观察和建议。
- `assist`: LLM 生成动作计划，人类确认后执行。
- `auto`: LLM 只能在 allow list 范围内自动执行。

`screen_control` 默认不能静默执行真实输入。真实执行必须满足以下条件之一：

- `requires_approval=True` 并被人类批准。
- 命中 narrow allow list（窄白名单），且目标、动作类型、坐标范围、按键集合、频率限制都匹配。

`screen_observe` 可以支持长期 allow list，但仍必须绑定目标范围，不能默认观察全部桌面。

## 5. Target Selector Contract

第一版 target selector 是跨平台 shape，Windows backend 先实现其中一部分。

```json
{
  "kind": "window",
  "selector": {
    "app": "example.exe",
    "title_contains": "optional title fragment",
    "window_id": "optional backend-specific id"
  }
}
```

规则：

- selector 必须至少包含一个可匹配字段。
- 如果匹配多个窗口，返回 `ambiguous_target`，不执行 control。
- 如果目标窗口变化，control 前必须重新校验。
- read model 只暴露低敏 target 摘要，不直接暴露截图内容。

## 6. Backend Boundary

新增 `ScreenBackendAdapter`，形态参考 terminal backend adapter。

职责：

- 构造 backend request。
- 传入 grants snapshot。
- 调用平台 backend。
- 验证 backend 不扩大 grants。
- 接收截图/metadata/action-result artifact。
- 创建 artifact refs。
- 返回低敏 summary。

Windows first backend：

- observe：窗口枚举、窗口 metadata、可见窗口截图。
- control：真实鼠标键盘输入。
- 最小化窗口：metadata 降级，截图不可靠时返回状态。

暂不做：

- 读进程内存。
- 注入客户端。
- 驱动级输入。
- 后台窗口消息伪装成可靠通用控制。
- 平台检测规避。

这些不是第一版的技术路线。

## 7. Artifact and Event Policy

截图和动作结果属于高敏 artifact。

artifact 类型候选：

- `screen_screenshot`
- `screen_metadata`
- `screen_control_plan`
- `screen_control_result`
- `screen_diagnostic`

事件顺序沿用现有动作链：

```text
action.proposed
action.decided
approval.requested?
approval.resolved?
action.started
artifact.created
action.completed
```

失败时：

```text
action.proposed
action.decided
action.started?
action.failed
```

read model 只能显示：

- tool name
- target summary
- action count
- status
- artifact refs
- stable reason code

不能显示：

- screenshot binary / base64
- raw OCR text
- full window content
- secret-containing input text

## 8. Testing Strategy

测试样本必须不唯一，不能把一个样本通过当成泛用能力通过。

### 8.1 Unit Tests

覆盖：

- target selector validation。
- ambiguous target 拒绝执行。
- allow list 匹配。
- approval_required 行为。
- action schema validation。
- requested capabilities 不能超过 grants。

### 8.2 Fake Backend Tests

用 fake backend 模拟：

- screenshot captured。
- metadata only。
- minimized window。
- ambiguous target。
- backend failure。
- backend reported widened grants。
- execute action success。
- execute action denied before backend call。

### 8.3 Integration Tests

走完整链路：

```text
submit_action
  -> ActionCompiler
  -> PolicyEngine
  -> Executor
  -> ScreenBackendAdapter
  -> ArtifactStore
  -> RunProjector
```

验证：

- observe 成功产生 artifact。
- control dry-run 产生 plan artifact。
- control execute 未审批时停在 pending 或 denied。
- 审批后才调用 backend。
- read model 不泄露截图内容。

### 8.4 Smoke Matrix

smoke matrix 必须覆盖多个 GUI 类型。

建议维度：

- 原生简单窗口。
- 浏览器 / 网页窗口。
- 跨平台桌面框架窗口。
- 游戏 / 高频渲染窗口。

smoke 测试第一版可以手动触发，不纳入默认 CI。每个样本只验证最小 observe / control 行为，并记录环境限制。

## 9. First Implementation Slice

第一版可交付：

1. Registry 增加 `screen_observe` / `screen_control`。
2. Policy 增加 screen grants：
   - `screen.observe`
   - `screen.control`
   - `target_selector_policy`
   - `action_policy`
   - `approval_required_actions`
3. ActionCompiler 编译 screen intent。
4. Executor 接入 `ScreenBackendAdapter`。
5. Fake backend 测试完整链路。
6. Windows backend 实现基础 observe / control。
7. Smoke runner 支持手动指定 target selector。

验收标准：

- fake backend 覆盖主路径和拒绝路径。
- integration 测试证明 artifact/event/read model 边界成立。
- Windows 本机至少完成一个 `screen_observe` smoke 和一个受审批的 `screen_control` smoke。
- 测试样本要求写成矩阵，不把单一样本作为泛用通过证明。

## 10. Open Questions

- Windows screenshot backend 选择：优先标准库 + PowerShell/.NET，还是引入轻量依赖。
- screenshot artifact 是否需要压缩或尺寸上限。
- 是否需要 OCR，若需要，OCR 应作为单独后续能力。
- macOS backend 何时补：接口预留，第一版不阻塞 Windows 实现。
- GUI control 是否需要独立 emergency stop API，还是先复用 cancel / pause 语义。
