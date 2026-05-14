# VCS / Git Optional Boundary v0.2

状态：`docs-only boundary / no implementation opened`

## 1. Purpose

本文记录一个 narrow decision：Isotope 是否需要为了“没有 Git 的电脑也能正常使用”而搭建 Git 集成模块。

结论是：

- Isotope kernel 不应把 Git 作为基础依赖。
- Git / VCS 能力应被设计成 optional capability（可选能力）和 future adapter（未来适配器），不是当前 kernel mainline 的必需模块。
- 没有 Git 的电脑应进入 `no_vcs` / `snapshot_only` 运行模式，而不是让 Isotope 整体不可用。

本文只固定边界和后续 reopened 条件，不新增 `src/` / `tests/` 行为，不打开真实 filesystem、git worktree、branch、commit、rollback 或 remote executor。

## 2. Branch Evidence

本判断参考了 2026-05-13 的当前分支形态：

- `origin/feature/controlled-terminal-exec` at `c780e60bab8a945b5d7b96a6ead3e380570ad7d4`
- `origin/codex/spike-aggressive-dev` at `cd764e74f47e771abc10be311537f6cbaffb5f46`
- `origin/main` at `4917a085a24ec0860ce1c2c44a35852ad7601f97`

观察结果：

- Controlled terminal branch 已进入 terminal backend / Codex-as-tool / product-chat 方向，但仍明确把 `git worktree executor` 排除在当前范围外。
- `CodexCliBackend` 只做 repo workspace check，并允许临时 smoke workspace 使用 `skip_git_repo_check`；这说明 Git repo 检测是 runtime preflight，不是 kernel 必需能力。
- Aggressive branch 的 `terminal.task.facade` 仍是 dry-run app-shell capability，并显式报告 `git_worktree_status=not_enabled`。
- 当前 app-layer pressure 需要的是可解释的 capability diagnosis（能力诊断）和 no-Git fallback，而不是完整 Git 操作层。

## 3. Decision

当前 decision：

```text
Isotope kernel
  -> must run without Git
  -> may expose VCS capability status
  -> must not require git worktree / branch / commit to preserve canonical state

Application / backend layer
  -> may use Git when available
  -> must degrade to no_vcs / snapshot_only when Git is absent
  -> must report disabled Git actions as structured capability status
```

换成外行话：

- Git 像“版本管理工具箱”。
- Isotope kernel 像“账本和审批规则”。
- 账本不应该因为电脑没有这个工具箱就打不开。
- 如果未来 code-agent 需要 Git，那它应该先检查工具箱在不在；不在就少做 branch / commit / worktree 这些动作，而不是停止整个系统。

## 4. Minimum Runtime Modes

未来如果实现 VCS boundary，应至少区分三种模式：

| Mode | Meaning | Allowed behavior |
| --- | --- | --- |
| `no_vcs` | 未检测到 Git，或当前 workspace 不是 Git repo | kernel / demos / artifact / approval / checkpoint 正常运行；Git 动作 disabled |
| `snapshot_only` | 可读取文件快照，但不声明版本控制能力 | 可生成 artifact / summary / diff-like report；不能 branch / commit / merge |
| `git_available` | Git binary 和 repo context 均可用 | 可以在后续 adapter 中打开受 policy 约束的 branch / commit / worktree 能力 |

这些模式应进入 capability / diagnosis 层，而不是改变 canonical event log 的基本可用性。

## 5. Hard Boundaries

必须遵守：

- Git absence must not break kernel startup, demos, replay, checkpoint, approvals, or artifact summary paths.
- Git state is not canonical kernel state.
- Branch names, commit hashes, worktree paths, and diffs can be artifact / summary metadata only after policy and output-sensitivity checks.
- Git operations must be explicit capabilities, not implicit side effects of terminal / worker / workspace helpers.
- `git_available` must be detected, not assumed.
- `git worktree` must remain separate from generic workspace lifecycle until a real substrate boundary is reopened.
- No model output may directly become a raw Git command without action / policy / approval / grants mediation.
- Missing Git should be reported as structured status such as `capability_missing` / `not_configured` / `no_vcs`, not as an opaque subprocess failure.

## 6. Suggested Future Shape

If a later branch produces concrete friction, the smallest useful first slice should be diagnosis-only:

```text
detect_vcs_capability(workspace)
  -> vcs_status: no_vcs | snapshot_only | git_available
  -> repo_detected: bool
  -> git_binary_detected: bool
  -> supported_actions: []
  -> disabled_actions: [branch, commit, worktree, merge]
  -> low_sensitive_summary
```

This should be an app/backend capability surface first. Only after a real code-agent workflow needs it should kernel mainline consider a bounded VCS read model or helper.

## 7. Reopen Conditions

Reopen this boundary only if at least one concrete pressure point appears:

- A terminal / Codex backend flow cannot explain why Git actions are disabled on a no-Git machine.
- A code-agent app flow needs branch / commit / worktree status but currently must run raw `git` commands outside Isotope policy.
- A backend produces changed-files / diff / commit metadata and there is no safe artifact / `ResourceRef` handoff.
- External review identifies Git availability as a blocker for adopting Isotope on ordinary user machines.
- Application-layer work proves `no_vcs` fallback is insufficient for a specific workflow.

The first reopened batch should be docs / red tests around detection and structured status, not a full Git module.

## 8. Non-Goals

This boundary does not implement or authorize:

- Git binary installation or bundled Git distribution.
- Branch / commit / merge / rebase automation.
- `git worktree` substrate.
- Filesystem mutation, write-mode workspace, rollback engine, or diff engine.
- Remote Git provider integration.
- GitHub API integration.
- Product UI for source control.
- Requiring Git for Isotope demos or kernel use.

## 9. Current Recommendation

Short term:

- Keep Isotope Git-free at the kernel level.
- Add documentation that Git is optional, not required.
- If future implementation starts, begin with `git_available` / `repo_detected` / `no_vcs_mode` diagnosis.

Medium term:

- Define a `VCS adapter` only after terminal / Codex backend or app-layer code-agent work proves a concrete need.
- Treat Git as one backend behind that adapter.

Long term:

- Implement branch / commit / worktree only when real workspace substrate, path safety, artifact policy, and approval boundaries are ready.

一句话：为了“没有 Git 的电脑也能正常使用”，Isotope 需要的是 Git optional boundary 和 no-Git fallback，不是现在把 Git 集成模块做进 kernel。
