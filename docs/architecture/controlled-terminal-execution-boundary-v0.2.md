# Controlled Terminal Execution Boundary v0.2

状态：`first slice implemented on feature/controlled-terminal-exec`

本文定义 Isotope 的 first controlled terminal execution slice。目标不是给模型开放裸 shell，也不是把 Isotope 扩成自研终端，而是把一个极窄的 `terminal_exec` tool 接入现有 kernel path：

`submit_action(...) -> ActionProposal -> PolicyDecision.grants -> Executor -> ControlledTerminalRunner -> artifact + ResourceRef -> canonical events`

## Architecture Correction

后续方向见 [Real Terminal Backend Boundary v0.2](real-terminal-backend-boundary-v0.2.md)。

当前 `terminal_exec` 是 deterministic boundary sample，用来证明 terminal-like action 可以被 Isotope 的 policy / approval / artifact / event / replay 边界约束。它不是最终 terminal backend。

下一阶段如果继续做终端能力，应优先接入真实 terminal / sandbox / process runtime backend，并在外层套 Isotope 的 action、policy、approval、workspace grants、artifact handoff 和 audit / replay contract。不要继续沿着给 `ControlledTerminalRunner` 扩 shell、PTY、streaming output、宽命令 allowlist 或 git worktree executor 的方向自然生长。

## Current Slice

当前实现包含：

- `ActionTypeRegistry.default()` 增加 metadata-only `terminal_exec` entry。
- `ActionCompiler` 要求 `terminal_exec` 使用 structured `argv: list[str]`，不接受 shell string。
- `PolicyEngine` 根据 registry 的 terminal command profile 决定是否 grant；command 必须在 `allowed_commands` 或 `approval_required_commands` 之一，否则直接 denied，且不会进入 `action.started`。
- registry 可声明 `approval_required_commands` command profile；这类 command 不带 `requires_approval=True` 时 denied，带 approval 时先进入 existing approval pause / resume boundary，批准后才执行；如果 command 同时出现在 allowlist 和 approval-required profile，approval-required 优先。
- `Executor` 仍只使用 `PolicyDecision.grants`，不会使用 requested capabilities 扩权。
- `ControlledTerminalRunner` 使用 `subprocess.run(..., shell=False)`，固定 sanitized env，执行 cwd 为 server root。
- terminal budget 来自 `PolicyDecision.grants["budget"]["seconds"]`，timeout 变成 structured `action.failed`。
- stdout / stderr / exit code 只进入 `terminal_output` artifact content；`artifact.created` event 只暴露 summary / `ResourceRef` / provenance，不暴露完整输出。
- `RunState.actions` 只投影 safe requested action summary：`terminal_command` / `argv_count` / `artifact_refs`，不投影完整 argv、stdout 或 stderr。
- output 有固定 cap；超出 cap 时 artifact content 记录 `truncated: true`。
- nonzero exit / timeout / start failure 使用 stable `error_reason_code` 和 `structured_error`。
- developer demo scenario `--scenario terminal-exec` 通过 canonical action chain 演示 `terminal_exec`，plain / trace / JSON 都只暴露 summary / `ResourceRef` / verification booleans，不暴露 stdout / stderr full content。

默认 allowlist 当前只包含 first-slice demo-safe command names：

- `echo`
- `printf`
- `pwd`
- `true`
- `false`
- `sleep`

`argv[0]` 必须是 command name，不能是 path；shell commands such as `bash -lc ...` are denied by policy.

默认 `approval_required_commands` 为空。该 profile 是 capability hook，不是默认开放高风险命令。测试用 custom registry 证明该路径可用：approval-required command 会先产生 `approval.requested`，批准后才进入 `action.started`；overlap 情况也会先要求 approval，不会被 `allowed_commands` 直接放行。

## Event Behavior

成功路径：

1. `action.proposed`
2. `action.decided`
3. `action.started`
4. `artifact.created`
5. `action.completed`
6. existing server path may append `run.completed`

失败路径：

- policy-denied command: stops after `action.decided` with denied decision; no `action.started` / `action.failed` / artifact.
- approval-required command without approval: stops after `action.decided` with reason `terminal_approval_required`; no `action.started` / `action.failed` / artifact.
- approval-required command with approval: appends `approval.requested`, waits for `approval.resolved`, then uses original `PolicyDecision.grants` to execute.
- timeout / nonzero exit / start failure: appends `action.started`, then structured `action.failed`; no `artifact.created`, no `action.completed`, no `run.completed`.

Stable terminal reason codes in this slice:

- `terminal_command_not_allowed`
- `terminal_approval_required`
- `terminal_timeout`
- `terminal_exit_nonzero`
- `terminal_start_failed`
- `terminal_shell_not_granted`
- `terminal_policy_unsupported`
- `terminal_grant_missing`
- `terminal_grant_malformed`

## Boundaries

This is a controlled terminal tool handler, not an open terminal product.

明确不包含：

- interactive terminal / PTY
- arbitrary shell string
- `shell=True`
- streaming output
- real sandbox / container / chroot
- git worktree executor
- remote executor
- product HTTP terminal route
- network command allowlist
- write-capable dev command allowlist
- user-specific auth / multi-user policy
- public tool SDK

当前 `terminal_exec` 仍是 local subprocess first slice。它降低了 action path 的 terminal pressure test 成本，但不应被描述为完整 sandbox security boundary，也不应被当成最终受控终端架构。

真实终端能力的正确下一步不是扩大这个 runner，而是先定义 `TerminalBackend` adapter：由成熟后端负责 terminal / PTY / sandbox / process lifecycle，由 Isotope 负责审批、授权快照、workspace/resource grants、artifact / `ResourceRef`、event log、read model、checkpoint 和 replay。

## Verification

Implemented tests:

- `tests/isotope/test_controlled_terminal_execution.py`
- `tests/isotope/test_terminal_exec_demo_scenario.py`
- updated default-registry expectations in `tests/isotope/test_action_type_registry.py`

Focused verification:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_controlled_terminal_execution.py -q
# 15 passed

PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_terminal_exec_demo_scenario.py tests/isotope/test_demo_trace_mode.py -q
# 12 passed

PYTHONPATH=src .venv/bin/python -m pytest tests/isotope -q
# 1066 passed
```
