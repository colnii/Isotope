# Windows Native Command Adapter Implementation Plan

Date: 2026-06-02

Source spec: `docs/superpowers/specs/2026-06-01-windows-native-command-adapter-design.md`

Required sub-skill: `test-driven-development`

## Goal

Implement the approved Windows native command adapter in two stages:

1. A stage: a structured Windows smoke harness for desktop / Node / Python / Tauri checks.
2. B stage: a `WindowsSystemTerminalRunner` that reuses the existing terminal backend contract.

Non-negotiable constraints:

- No model-authored PowerShell, cmd, bash, or shell string.
- Resolve host mode before resolving workspace strategy.
- Treat `.cmd` / `.bat` as shell-risky; B general runner allows `.exe` by default only.
- Keep full stdout / stderr / local paths in diagnostic artifacts, not public summaries.
- Use a fixed workspace copy policy and reject symlinks that escape `source_root`.
- On timeout, record full process-tree cleanup status.

## Architecture

New A-stage module:

- `src/isotope/execution/terminal/windows_smoke.py`

New B-stage module:

- `src/isotope/execution/terminal/windows_runner.py`

Tests:

- `tests/unit/execution/terminal/test_windows_smoke.py`
- `tests/unit/execution/terminal/test_windows_runner.py`
- `tests/fixtures/windows_smoke_report.golden.json`

Existing contracts to reuse:

- `TerminalBackendRequest`, `TerminalBackendResult`, and `TerminalBackendOutputArtifact`
- `validate_argv`, `terminal_grant_from`, and `cap_terminal_output`
- `LinuxSystemTerminalRunner` transcript and artifact shape as the closest runner reference

## Task 0: Worktree and Baseline

- [x] Work in isolated branch `feature/windows-native-command-adapter`.
- [x] Work in isolated worktree `.worktrees/windows-native-command-adapter`.
- [x] Baseline command: `/home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/execution/terminal -q`
- [x] Baseline result observed before implementation: `47 passed`.

## Task 1: Smoke Schema and Golden Report

Write failing tests first for:

- [ ] `WindowsSmokeStep`, `WindowsSmokePlan`, and `WindowsSmokeReport` structured serialization.
- [ ] `WindowsSmokeReport` includes schema version, runner version, profile id/version, host mode, platform info, tool versions, workspace decision, repo revision, timestamps, diagnostic report, and public summary.
- [ ] Public summary redacts user home/temp paths and excludes full stdout/stderr.
- [ ] Golden JSON fixture remains stable.

Implementation:

- [ ] Add dataclasses and `to_dict()` / `to_json()` helpers in `windows_smoke.py`.
- [ ] Add `redact_public_summary(...)` helper.
- [ ] Keep diagnostic report full enough for local debugging.

Verification:

- [ ] `PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/execution/terminal/test_windows_smoke.py -q`

Commit:

- [ ] `feat(terminal): add windows smoke report schema`

## Task 2: Host Mode and Workspace Resolver

Write failing tests first for:

- [ ] `resolve_windows_host_mode(...)` returns `windows_python`, `wsl_to_windows_helper`, or `unsupported`.
- [ ] Workspace resolver chooses direct for safe Windows local paths.
- [ ] Workspace resolver chooses short temp copy root for WSL/UNC or long-path risk.
- [ ] Copy policy includes known project files and excludes `.git`, `.venv`, `node_modules`, `target`, `dist`, `build`, `.svelte-kit`, caches.
- [ ] Symlinks escaping `source_root` are rejected.
- [ ] Mutation policy keeps install/build/smoke off the source workspace unless explicitly allowed.

Implementation:

- [ ] Add `WindowsWorkspaceDecision`.
- [ ] Add deterministic copy include/exclude walker.
- [ ] Add cleanup policy fields: `cleanup_on_success` and `keep_on_failure`.

Verification:

- [ ] `PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/execution/terminal/test_windows_smoke.py -q`

Commit:

- [ ] `feat(terminal): resolve windows smoke workspace`

## Task 3: Smoke Step Runner and Fixed Profiles

Write failing tests first for:

- [ ] Fixed profiles: `desktop_tools_versions`, `desktop_frontend_check`, `desktop_frontend_build`.
- [ ] `env_overlay` is profile-owned data, not arbitrary model input.
- [ ] Step runner uses structured `argv`, `cwd`, timeout, output cap, and ordered execution.
- [ ] Nonzero exit and missing required artifact produce structured reason codes.
- [ ] Timeout records process-tree cleanup attempt and success/failure.
- [ ] PowerShell helper invocation, when needed, uses only:
  `powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File <fixed_helper.ps1> <json paths>`.

Implementation:

- [ ] Add `WindowsCommandProfile` and built-in profile registry.
- [ ] Add injectable process runner for unit tests.
- [ ] Add process tree cleanup abstraction with Windows `taskkill` fallback metadata.
- [ ] Add `run_windows_native_smoke_plan(...)`.

Verification:

- [ ] `PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/execution/terminal/test_windows_smoke.py -q`

Commit:

- [ ] `feat(terminal): run fixed windows smoke profiles`

## Task 4: Windows System Terminal Runner

Write failing tests first for:

- [ ] Reject non-`exec_argv` command requests.
- [ ] Require terminal grants and reject `terminal.shell == True`.
- [ ] Resolve `argv[0]` with `shutil.which` and record `resolved_executable`.
- [ ] Reject `.cmd` and `.bat` for general runner.
- [ ] Reject npm / pnpm / yarn / npx as arbitrary `exec_argv`.
- [ ] Completed, nonzero, timeout, and start-failure results all return structured `TerminalBackendResult`.
- [ ] Transcript artifact includes argv, cwd, exit code, capped output, timeout, truncation, `shell=false`, `platform=windows`, `resolved_executable`, and process-tree cleanup status.
- [ ] Summary does not expose full stdout/stderr.

Implementation:

- [ ] Add `src/isotope/execution/terminal/windows_runner.py`.
- [ ] Export `WindowsSystemTerminalRunner` from `runner.py`.
- [ ] Mirror Linux runner shape while keeping Windows-specific checks inside the new runner.

Verification:

- [ ] `PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/execution/terminal/test_windows_runner.py -q`
- [ ] `PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/execution/terminal -q`

Commit:

- [ ] `feat(terminal): add windows system terminal runner`

## Task 5: Integration Verification and Handoff

- [ ] Run full terminal unit suite.
- [ ] Run `git diff --check`.
- [ ] Re-read the spec success criteria and record any deferred items.
- [ ] Commit final docs/test cleanup if needed.
- [ ] Push branch.

Manual Windows validation remains required after this Linux/WSL implementation pass:

```bash
PYTHONPATH=src .venv\\Scripts\\python.exe -m pytest tests/unit/execution/terminal -q
```
