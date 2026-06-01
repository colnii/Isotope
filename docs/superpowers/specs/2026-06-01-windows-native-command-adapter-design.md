# Windows Native Command Adapter Design

状态：`design review`

日期：2026-06-01

## 1. Purpose

Isotope 后续要成为 Windows-first 的常驻桌面软件，Windows 原生验证必须稳定。
当前痛点不是“AI 不会写 PowerShell”，而是 PowerShell / cmd / WSL / Docker /
Node / Python / Tauri 的执行语义混在一起，导致 AI 很容易写坏引号、换行、路径和
working directory。

本设计先解决两层目标：

1. A 阶段：让 Isotope 自己的 Windows 原生 smoke 稳定运行，尤其是 desktop /
   Tauri / Node / Python 验证链路。
2. B 阶段：把 A 阶段沉淀成可复用的 Windows system terminal runner，接入现有
   terminal backend contract。

核心原则：

- AI 面向结构化任务，不面向自由 PowerShell string。
- PowerShell 只作为 runner 内部实现细节，不作为产品接口。
- 默认复用 `exec_argv`、policy、approval、artifact 和 read model 边界。
- stdout / stderr / transcript 全量内容只进 artifact，不进 event / read model。

## 2. Reuse Audit

必须复用：

- `src/isotope/execution/terminal/backend_types.py`
  - 已定义 `TerminalBackendRequest`、`TerminalBackendResult`、
    `TerminalBackendOutputArtifact` 和 backend status / protocol version。
  - Windows runner 必须返回同一合同，不新增平行结果格式。
- `src/isotope/execution/terminal/backend_adapter.py`
  - 已负责构造 request、校验 backend 结果、写 artifact、生成低敏
    `terminal_backend` summary。
  - B 阶段必须接这里，不绕过 adapter 直接写事件。
- `src/isotope/execution/terminal/linux_runner.py`
  - 已有本机 runner 参考实现：`exec_argv`、`shell=False`、sanitized env、
    timeout、output cap、transcript artifact。
  - Windows runner 应保持同构，平台差异只在 runner 内部。
- `src/isotope/capabilities/tools/terminal.py`
  - 已提供 `validate_argv(...)`、`terminal_grant_from(...)`、
    `cap_terminal_output(...)`。
  - Windows runner 继续复用 argv 校验和输出截断。
- `src/isotope/execution/screen/windows_backend.py`
  - 已有 PowerShell 非交互执行经验：临时 request / result JSON 文件、
    `-NoProfile`、`-ExecutionPolicy Bypass`、timeout、结构化失败。
  - 该模式可用于必须走 PowerShell 的 Windows helper，但不要复制 screen 业务逻辑。

不复用或暂不扩展：

- 不扩大 `ControlledTerminalRunner` 的 allowlist 来解决 Windows 问题。
- 不把 `bash -lc`、PowerShell script string 或 cmd string 暴露给模型。
- 不做 interactive PTY、product terminal UI、remote executor、container 或 git
  worktree executor。
- 不把 Windows screen backend 当作通用命令 runner；只复用它的进程调用模式。

## 3. Proposed Approach

采用两阶段方案：先 smoke harness，再 Windows runner。

```text
A. Windows native smoke harness
   -> solves desktop/Tauri validation reliability
   -> produces structured command result JSON
   -> avoids AI-authored PowerShell commands

B. WindowsSystemTerminalRunner
   -> reuses terminal backend contract
   -> runs approved exec_argv on Windows
   -> returns transcript artifact + low-sensitive summary
```

这样做的好处是先服务当前最痛的 Windows 原生验收，再把稳定路径下沉为系统能力。
如果直接做 B，很容易在还没摸清 Tauri / npm / WSL path friction 前过早抽象。

## 4. Scope

### Must Have For A

- 提供一个 Windows-native smoke harness，先服务 desktop / Tauri 验证。
- 识别当前 repo 路径是否适合 Windows 原生工具直接运行。
- 当 Windows 工具无法在 WSL UNC cwd 运行时，复制目标子树到 Windows local temp。
- 用结构化步骤运行命令，不让 AI 拼 PowerShell 多行命令。
- 每个步骤记录：
  - logical name
  - argv
  - cwd
  - started / finished time
  - exit code
  - capped stdout / stderr
  - artifact paths
  - copied workspace path if used
- 输出统一 JSON summary，便于 Supervisor / desktop 后续展示。
- 对 npm / Node / Python / Tauri smoke 支持可测试的 command profile。

### Must Have For B

- 新增 `WindowsSystemTerminalRunner`，与 `LinuxSystemTerminalRunner` 同层。
- 只接受 `TerminalBackendRequest.command_request.kind == "exec_argv"`。
- 继续要求 `terminal.shell == False` 和 argv allowlist grants。
- 默认使用 `subprocess.run(..., shell=False)`。
- 仅在必要时使用内部 PowerShell helper，并保持 `-NoProfile` /
  `-NonInteractive` / timeout / JSON request-result 边界。
- 返回 `TerminalBackendResult`，至少包含 transcript artifact。
- transcript content 包含 argv、cwd、exit code、stdout、stderr、truncated、
  timeout、shell=false、platform=windows。
- event / read model 只包含 backend summary，不包含完整命令输出、本机 secret、
  temp path 中的敏感片段或环境变量。

### Later

- richer command profiles for package managers.
- persistent Windows local workspace cache.
- direct Tauri packaged-app smoke.
- screenshot attachment plumbing for smoke artifacts.
- cancellation beyond subprocess timeout.
- interactive PTY.
- product terminal UI.

## 5. Architecture

### A: Smoke Harness

新增一个窄模块，例如：

```text
src/isotope/execution/terminal/windows_smoke.py
```

候选公开函数：

```python
run_windows_native_smoke_plan(plan: WindowsSmokePlan) -> WindowsSmokeReport
```

核心对象：

- `WindowsSmokePlan`
  - `source_root`
  - `workspace_strategy`: `direct` / `copy_to_temp` / `auto`
  - `steps`
  - `timeout_seconds`
  - `max_output_bytes`
- `WindowsSmokeStep`
  - `name`
  - `argv`
  - `cwd`
  - `env`
  - `required_artifacts`
- `WindowsSmokeReport`
  - `status`
  - `workspace`
  - `steps`
  - `artifacts`
  - `diagnostics`

第一批调用方可以是手动 CLI 或测试 helper，不必立刻接 Supervisor web UI。

### B: Windows Runner

新增：

```text
src/isotope/execution/terminal/windows_runner.py
tests/unit/execution/terminal/test_windows_runner.py
```

`WindowsSystemTerminalRunner` 与 `LinuxSystemTerminalRunner` 对齐：

```text
TerminalBackendRequest
  -> validate argv and grants
  -> resolve Windows cwd
  -> subprocess.run(shell=False)
  -> cap stdout/stderr
  -> TerminalBackendResult(transcript artifact)
  -> TerminalBackendAdapter writes artifact and low-sensitive summary
```

后续如需让 runtime 选择 runner，再扩展 backend selector config；本 spec 不要求自动
切换平台。

## 6. Data Flow

A 阶段：

```text
desktop smoke request
  -> WindowsSmokePlan
  -> workspace resolver
     -> direct Windows cwd OR copy to local temp
  -> structured steps
  -> subprocess execution
  -> WindowsSmokeReport JSON
```

B 阶段：

```text
approved terminal_exec action
  -> TerminalBackendAdapter.prepare_and_run(...)
  -> TerminalBackendRequest(exec_argv)
  -> WindowsSystemTerminalRunner.run(...)
  -> TerminalBackendResult
  -> artifact store + ResourceRef
  -> action.completed low-sensitive terminal_backend summary
```

## 7. PowerShell Policy

PowerShell 使用规则：

- 不把 PowerShell command string 暴露给 AI。
- 不接受自由 script text 作为 public API。
- 必须使用 `-NoProfile`。
- 必须使用 `-NonInteractive`，能用时加上。
- 需要绕过本机 execution policy 时，只限临时 helper script，并使用
  `-ExecutionPolicy Bypass`。
- Python 侧用临时 JSON request / result 文件交换结构化数据。
- helper script 失败时返回 reason code、diagnostic artifact 和 retryable flag。

常见禁用形态：

- `powershell -Command "<AI generated multiline script>"`
- `cmd /c "<AI generated shell line>"`
- `bash -lc "<AI generated shell line>"`
- 直接在 WSL UNC path 上调用 Windows npm / cmd / PowerShell 并假设可用。

## 8. Error Handling

A 阶段 reason codes：

- `windows_smoke_platform_unavailable`
- `windows_smoke_workspace_copy_failed`
- `windows_smoke_command_start_failed`
- `windows_smoke_command_timeout`
- `windows_smoke_command_exit_nonzero`
- `windows_smoke_required_artifact_missing`
- `windows_smoke_protocol_error`

B 阶段 reason codes：

- `terminal_windows_runner_completed`
- `terminal_windows_runner_exit_nonzero`
- `terminal_windows_runner_timeout`
- `terminal_windows_runner_start_failed`
- `terminal_windows_runner_workspace_unavailable`
- `terminal_windows_runner_protocol_error`

失败输出同样走 artifact / diagnostic，不把完整 stderr 塞进 event。

## 9. Testing

A 阶段测试：

- workspace resolver 在 Windows local path 下选择 direct。
- workspace resolver 对 WSL UNC / unsupported cwd 选择 copy_to_temp。
- smoke plan 按顺序运行步骤，任一步失败后停止或按配置继续。
- required artifact 缺失时报 `windows_smoke_required_artifact_missing`。
- stdout / stderr 超出限制时标记 truncated。
- PowerShell helper invocation 不包含 profile、不使用自由 command string。

B 阶段测试：

- `WindowsSystemTerminalRunner` 拒绝非 `exec_argv`。
- 缺 terminal grants / shell grant 为 true / command 不在 allowlist 时失败。
- completed result 生成 transcript artifact。
- nonzero exit、timeout、start failure 返回结构化 status / reason code。
- result summary 不泄漏 stdout / stderr full content。
- adapter 接收 Windows runner result 后只在 artifact 中保留 full content。

验证命令：

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/execution/terminal -q
```

Windows 原生 smoke 还需要后续在 Windows 机器上补一条手动验收命令，不能用 WSL
结果当最终验收。

## 10. Implementation Order

1. 写 A 阶段 tests：workspace strategy、step execution、report shape、output cap。
2. 实现 `windows_smoke.py` 的纯 Python plan / report / runner。
3. 为 desktop smoke 定义第一份 plan：install/check/build/smoke 可逐步打开。
4. 在 Windows 原生环境跑 smoke，记录真实失败并收敛。
5. 写 B 阶段 tests：runner contract、grant validation、artifact-safe result。
6. 实现 `windows_runner.py`。
7. 接入 backend selector 或提供显式构造入口。
8. 更新相关 docs / runbook。

## 11. Success Criteria

A 阶段完成时：

- Windows 原生 desktop smoke 不再需要手写 PowerShell 命令。
- WSL UNC path 下的 Windows npm / cmd cwd 问题有明确自动规避路径。
- 每次 smoke 都能留下结构化 report。

B 阶段完成时：

- Isotope 能通过现有 terminal backend contract 在 Windows 上执行已批准
  `exec_argv`。
- full output 只进 artifact；event / read model 只展示低敏 backend summary。
- Linux runner 与 Windows runner 行为同构，平台差异被限制在 runner 内部。

## 12. Non-Goals

- 不实现交互式 PowerShell。
- 不实现终端 UI。
- 不开放任意 shell string。
- 不把 PowerShell 作为模型可直接调用的 tool。
- 不引入 remote execution。
- 不把 desktop smoke 和 terminal backend 一次性塞进 Supervisor UI。
