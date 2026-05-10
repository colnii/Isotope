# Restart Write Helper Run Context Boundary v0.2

状态：`green slice complete / pushed`

本文记录从 aggressive-dev `worker.handoff.recovery.review` 回流的 bounded `kernel_friction`：`restart_write_helper_run_context_missing`。

## Accepted Friction

当前 event log / replay / checkpoint-assisted rebuild 已能在新的 `InProcessServer(root, checkpoint_store=...)` 中恢复 existing run read model，但部分 public write helpers 仍依赖 process-local `_runs`。服务器重启后，app shell 能 `get_run_state(run_id)`，却不能继续对同一 run 调用 selected write helpers：

- `create_source_artifact(...)`
- `submit_worker_handoff(...)`

此前失败是 structured `unknown_run`，且没有 partial events。这说明问题不是 app-local convenience，而是 restart 后 helper write path 缺少 event-backed run context recovery。

## Verification

Red-to-green path:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope_kernel/test_restart_write_helper_run_context.py -q
# before implementation: 3 failed
# after implementation: 3 passed
```

Focused regression:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/isotope_kernel/test_restart_write_helper_run_context.py \
  tests/isotope_kernel/test_source_artifact_setup_helper.py \
  tests/isotope_kernel/test_worker_handoff_helper.py \
  tests/isotope_kernel/test_run_lifecycle_boundary.py \
  -q
# 24 passed
```

Full local regression:

```bash
DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH} \
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope_kernel -q
# 1058 passed
```

The tests first prove `restarted.get_run_state(run_id).run_id == run_id`, then expect the selected write helper to recover minimal runtime context from canonical events. A terminal-run regression also verifies post-restart writes fail closed without side effects.

## Implemented Boundary

The green slice lets selected write helpers recover:

- run existence from `run.created`
- active/non-terminal status from projected `RunState`
- default supervisor `agent_id` from `agent.created`
- default `thread_id` from `thread.created`

The recovered context is only for deterministic in-process helper continuity after restart. It does not become a product session workflow, scheduler, process supervisor, or mutable hidden state source.

## Non-Goals

This slice must not introduce:

- real worker runtime
- scheduler / process supervisor
- process spawn
- container / git worktree
- real HTTP server
- provider adapter
- public SDK
- new dependency
- tag or release
- event-store append-only rewrite
- executor grants semantic change
