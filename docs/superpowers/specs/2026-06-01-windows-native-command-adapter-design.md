# Windows Native Command Adapter Design

状态：`design review — approved with P0 clarifications`

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

## 2. Host Execution Mode

Windows smoke harness 必须先判断 host mode，再判断 workspace。不能在 WSL
Python 里直接假设 Windows npm / Tauri / PowerShell 可以安全使用当前 cwd。

支持的 host modes：

- `windows_python`
  - 当前 Python 进程运行在 Windows 原生环境，`sys.platform == "win32"`。
  - 可以直接创建 Windows local temp、调用 Windows 工具和读取 Windows 路径。
- `wsl_to_windows_helper`
  - 当前 Python 进程运行在 WSL，但可调用固定 Windows helper。
  - WSL 侧只负责生成结构化 request、准备或复制 workspace、调用固定 helper。
  - Windows helper 必须通过 PowerShell `-File` 固定脚本入口运行，不接受模型生成的
    command string。
- `unsupported`
  - 非 Windows host，且没有可验证的 Windows interop。
  - A 阶段必须 fail closed，返回 `windows_smoke_platform_unavailable`。

A 阶段顺序固定为：

```text
resolve host mode
  -> resolve source path kind
  -> resolve workspace strategy
  -> run fixed profile steps
  -> write diagnostic report artifact + public summary
```

## 3. Reuse Audit

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
- Python `subprocess` 官方文档
  - Windows 上 `.bat` / `.cmd` 可能经系统 shell 启动，参数会按 shell 规则解析，
    不应把 `shell=False` 理解成完全没有 shell 语义。
- Microsoft PowerShell CLI 文档
  - PowerShell helper 只能使用固定 `-File` 入口，配合 `-NoProfile` 和
    `-NonInteractive`。
- Microsoft Windows path length 文档
  - Windows 仍存在 `MAX_PATH` / long-path opt-in 差异，workspace resolver 必须能把
    深路径迁移到短 temp root。

不复用或暂不扩展：

- 不扩大 `ControlledTerminalRunner` 的 allowlist 来解决 Windows 问题。
- 不把 `bash -lc`、PowerShell script string 或 cmd string 暴露给模型。
- 不做 interactive PTY、product terminal UI、remote executor、container 或 git
  worktree executor。
- 不把 Windows screen backend 当作通用命令 runner；只复用它的进程调用模式。

## 4. Proposed Approach

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

边界：

- `windows_smoke.py` 不是 product terminal backend。
- `windows_smoke.py` 不直接写 terminal backend events。
- A 阶段 report 后续可以作为 terminal backend diagnostic artifact 的来源，但不跳过
  `TerminalBackendAdapter`。

## 5. Scope

### Must Have For A

- 提供一个 Windows-native smoke harness，先服务 desktop / Tauri 验证。
- 先 resolve host mode：`windows_python` / `wsl_to_windows_helper` /
  `unsupported`。
- 识别当前 repo 路径是否适合 Windows 原生工具直接运行。
- 当 Windows 工具无法在 WSL UNC cwd 运行时，复制目标子树到 Windows local temp。
- 当路径可能触发 Windows path length 风险时，复制到短 temp root，例如
  `C:\isotope-smoke\<run_id>`。
- copy policy 必须固定 include / exclude，不允许默认复制整个 repo。
- symlink 指向 `source_root` 外部时必须拒绝。
- direct workspace 默认只允许 read/check steps；install/build/smoke 默认使用
  `copy_to_temp`，除非 profile 显式允许修改源 workspace。
- copied workspace cleanup policy 必须可配置：
  - `cleanup_on_success`
  - `keep_on_failure`
- 用结构化步骤运行命令，不让 AI 拼 PowerShell 多行命令。
- timeout 后必须清理完整 process tree；Windows 实现可用 Job Object 或固定
  `taskkill` fallback，并记录 cleanup 是否成功。
- 每个步骤记录：
  - logical name
  - argv
  - cwd
  - started / finished time
  - exit code
  - capped stdout / stderr
  - artifact paths
  - copied workspace path if used
- 输出统一 JSON report，但必须分两层：
  - `diagnostic_report`：artifact 内容，可含完整本机路径和 capped output。
  - `public_summary`：给 Supervisor / desktop 展示，必须 redacts user home、
    temp path、env values 和 full stdout / stderr。
- 对 npm / Node / Python / Tauri smoke 支持可测试的 command profile。

### Must Have For B

- 新增 `WindowsSystemTerminalRunner`，与 `LinuxSystemTerminalRunner` 同层。
- 只接受 `TerminalBackendRequest.command_request.kind == "exec_argv"`。
- 继续要求 `terminal.shell == False` 和 argv allowlist grants。
- 默认使用 `subprocess.run(..., shell=False)`。
- 必须用 `shutil.which` 解析 `argv[0]` 并记录 `resolved_executable`。
- general terminal runner 默认只允许 `.exe` executable。
- `.cmd` / `.bat` 必须拒绝，除非命令来自固定 internal command profile。
- Windows 上 npm / pnpm / yarn / npx 归为 profile-backed commands，不作为任意
  `exec_argv` 开放。
- 仅在必要时使用内部 PowerShell helper，并保持 `-NoProfile` /
  `-NonInteractive` / timeout / JSON request-result 边界。
- timeout 后必须清理完整 process tree，并在 result 中记录 cleanup status。
- 返回 `TerminalBackendResult`，至少包含 transcript artifact。
- transcript content 包含 argv、cwd、exit code、stdout、stderr、truncated、
  timeout、shell=false、platform=windows、resolved_executable、
  process_tree_cleanup。
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

## 6. Workspace Copy And Mutation Policy

A 阶段 copy policy 必须显式。第一版 profile 支持的默认复制范围：

include:

- `package.json`
- `package-lock.json`
- `npm-shrinkwrap.json`
- `pnpm-lock.yaml`
- `yarn.lock`
- `apps/desktop/`
- `src/`
- `pyproject.toml`
- `Cargo.toml` and `Cargo.lock` if present
- `apps/desktop/src-tauri/`

exclude:

- `.git/`
- `.venv/`
- `node_modules/`
- `target/`
- `dist/`
- `build/`
- `.svelte-kit/`
- `__pycache__/`
- `.pytest_cache/`
- `.mypy_cache/`
- `.ruff_cache/`
- generated smoke artifacts unless profile explicitly imports them

Mutation policy:

- `direct` workspace is allowed only for read/check steps by default.
- install/build/smoke steps default to `copy_to_temp`.
- a profile may opt into direct mutation only with a named `mutation_policy`.
- copied workspace cleanup defaults to `cleanup_on_success` and `keep_on_failure`.
- cleanup never deletes source workspace paths.

## 7. Command Profile Schema

A 阶段不接受模型自由传任意命令。命令来自固定 profile。

```text
WindowsCommandProfile
  id
  description
  profile_version
  steps
  required_tools
  cwd_policy
  env_policy
  timeout_seconds
  allowed_executable_extensions
  required_artifacts
  mutation_policy
```

`WindowsSmokeStep.env` 命名为 `env_overlay`，并且只能由 profile 定义。模型或用户输入
不能直接传任意 env 覆盖。

第一批 profile：

- `desktop_tools_versions`: `node --version`、`npm --version`、
  `python --version`。
- `desktop_frontend_check`: `npm ci`、`npm run check`。
- `desktop_frontend_build`: `npm ci`、`npm run build`。

`npm` 相关 profile 是 A 阶段固定 profile，不代表 B 阶段 general runner 开放
任意 npm 参数。

## 8. Report Schema

`WindowsSmokeReport` 必须带版本和环境信息：

- `schema_version`
- `runner_version`
- `profile_id`
- `profile_version`
- `host_mode`
- `platform_info`
- `tool_versions`
- `source_root_kind`
- `workspace_strategy_decision`
- `repo_revision_if_available`
- `started_at`
- `finished_at`
- `diagnostic_report`
- `public_summary`

`diagnostic_report` 可以进入 artifact，保留 capped stdout / stderr、完整 workspace
路径和 copy path。`public_summary` 才能进入 Supervisor / desktop read model。

## 9. Architecture

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
  - `env_overlay`
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

## 10. Data Flow

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

## 11. PowerShell Policy

PowerShell 使用规则：

- 不把 PowerShell command string 暴露给 AI。
- 不接受自由 script text 作为 public API。
- 只允许固定 invocation shape：

```text
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File <fixed_helper.ps1> <json paths>
```

- `-File` script 必须来自 repo 内固定 helper 或运行时生成的固定模板。
- helper content 不能由模型生成。
- Python 侧用临时 JSON request / result 文件交换结构化数据。
- helper script 失败时返回 reason code、diagnostic artifact 和 retryable flag。

常见禁用形态：

- `powershell -Command "<AI generated multiline script>"`
- `powershell -EncodedCommand "<...>"`
- stdin script
- `cmd /c "<AI generated shell line>"`
- `bash -lc "<AI generated shell line>"`
- 直接在 WSL UNC path 上调用 Windows npm / cmd / PowerShell 并假设可用。

## 12. Error Handling

A 阶段 reason codes：

- `windows_smoke_platform_unavailable`
- `windows_smoke_workspace_copy_failed`
- `windows_smoke_command_start_failed`
- `windows_smoke_command_timeout`
- `windows_smoke_process_tree_cleanup_failed`
- `windows_smoke_command_exit_nonzero`
- `windows_smoke_required_artifact_missing`
- `windows_smoke_protocol_error`

B 阶段 reason codes：

- `terminal_windows_runner_completed`
- `terminal_windows_runner_exit_nonzero`
- `terminal_windows_runner_timeout`
- `terminal_windows_runner_process_tree_cleanup_failed`
- `terminal_windows_runner_start_failed`
- `terminal_windows_runner_workspace_unavailable`
- `terminal_windows_runner_protocol_error`

失败输出同样走 artifact / diagnostic，不把完整 stderr 塞进 event。

## 13. Testing

A 阶段测试：

- host mode resolver 识别 `windows_python`、`wsl_to_windows_helper`、
  `unsupported`。
- workspace resolver 在 Windows local path 下选择 direct。
- workspace resolver 对 WSL UNC / unsupported cwd 选择 copy_to_temp。
- workspace resolver 对长路径风险选择短 temp root。
- copy policy 包含必要源码和锁文件，排除 `.git`、`.venv`、`node_modules`、
  `target`、`build`、`.svelte-kit` 等生成物。
- symlink escaping source root 被拒绝。
- mutation policy 阻止 install/build/smoke 污染 source workspace。
- report 生成 golden JSON fixture，包含 schema version、profile version、
  host mode、tool versions、public summary 和 diagnostic report。
- smoke plan 按顺序运行步骤，任一步失败后停止或按配置继续。
- required artifact 缺失时报 `windows_smoke_required_artifact_missing`。
- stdout / stderr 超出限制时标记 truncated。
- PowerShell helper invocation 使用固定 `-File`，包含 `-NoProfile` /
  `-NonInteractive`，不使用 `-Command`、`-EncodedCommand` 或 stdin script。
- timeout 后调用 process-tree cleanup，并记录 cleanup status。

B 阶段测试：

- `WindowsSystemTerminalRunner` 拒绝非 `exec_argv`。
- 缺 terminal grants / shell grant 为 true / command 不在 allowlist 时失败。
- `argv[0]` 通过 `shutil.which` 解析，result 记录 `resolved_executable`。
- general runner 拒绝 `.cmd` / `.bat`。
- npm / pnpm / yarn / npx 只能通过 fixed profile，不作为任意 `exec_argv` 开放。
- completed result 生成 transcript artifact。
- nonzero exit、timeout、start failure 返回结构化 status / reason code。
- timeout 后清理 process tree，并在 transcript 中记录 cleanup result。
- result summary 不泄漏 stdout / stderr full content。
- adapter 接收 Windows runner result 后只在 artifact 中保留 full content。

验证命令：

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/execution/terminal -q
```

Windows 原生 smoke 还需要后续在 Windows 机器上补一条手动验收命令，不能用 WSL
结果当最终验收。

## 14. Implementation Order

1. 写 `WindowsSmokePlan` / `WindowsSmokeReport` schema 和 golden JSON fixture。
2. 写 host mode resolver：`windows_python` / `wsl_to_windows_helper` /
   `unsupported`。
3. 写 workspace resolver：direct / copy、path kind、copy exclude、mutation policy、
   short temp root。
4. 写 step runner：fixed profile、output cap、encoding、timeout、process-tree
   cleanup。
5. 跑第一批只读 smoke：`node --version`、`npm --version`、`python --version`。
6. 再打开 `npm ci` / `npm run check` / `npm run build`。
7. A 阶段真实 Windows 通过后，再写 B 阶段 tests：runner contract、grant
   validation、artifact-safe result。
8. 实现 `windows_runner.py`。
9. 接入 backend selector 或提供显式构造入口。
10. 更新相关 docs / runbook。

## 15. Success Criteria

A 阶段完成时：

- Windows 原生 desktop smoke 不再需要手写 PowerShell 命令。
- WSL UNC path 下的 Windows npm / cmd cwd 问题有明确自动规避路径。
- 每次 smoke 都能留下结构化 report。
- install/build/smoke 默认不污染 source workspace。
- timeout 不遗留 node / npm / cargo / rustc / tauri 子进程。
- public summary 不泄露 user home、temp path、env values 或完整 stdout / stderr。

B 阶段完成时：

- Isotope 能通过现有 terminal backend contract 在 Windows 上执行已批准
  `exec_argv`。
- full output 只进 artifact；event / read model 只展示低敏 backend summary。
- Linux runner 与 Windows runner 行为同构，平台差异被限制在 runner 内部。
- `.cmd` / `.bat` 不会通过 general runner 形成隐式 shell 通道。

## 16. Non-Goals

- 不实现交互式 PowerShell。
- 不实现终端 UI。
- 不开放任意 shell string。
- 不把 PowerShell 作为模型可直接调用的 tool。
- 不引入 remote execution。
- 不把 desktop smoke 和 terminal backend 一次性塞进 Supervisor UI。

## 17. Reference Basis

- [Python `subprocess` 文档](https://docs.python.org/3/library/subprocess.html)：
  Windows `.bat` / `.cmd` 可能经系统 shell 启动，不能把 `shell=False` 视为完全
  消除 shell 语义。
- [Microsoft PowerShell CLI 文档](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_powershell_exe?view=powershell-5.1)：
  `-File`、`-NoProfile`、`-NonInteractive` 和 `-ExecutionPolicy` 是正式 CLI 参数；
  本设计只允许固定 `-File` helper。
- [Microsoft Windows path length 文档](https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation)：
  传统 `MAX_PATH` 为 260 characters，long path 行为依赖系统和应用 opt-in；smoke
  workspace 应优先短路径。
