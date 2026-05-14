# Worker Handoff App Spike Selection

状态：`selection complete; red tests paused after aggressive-dev coverage`

## 1. Purpose

本文把 aggressive-dev 已关闭的 `private_append_worker_handoff` friction 转成下一步主线可执行的 app-level pressure test 选择。目标不是实现 real worker runtime，而是判断是否值得用一个 deterministic in-process app spike 横向压测 worker handoff composition。

## 2. Inputs

- `../reviews/kernel-gap-review-refresh-v0.2.md`
- `../reviews/app-spike-coverage-review.md`
- `../architecture/worker-handoff-helper-boundary-v0.2.md`
- `worker-handoff-helper-closure-review.md`
- aggressive-dev `c7e0b32`
- review mailbox result: `worker-handoff-gap --json` now reports `private_append_required=false` and `app_friction=[]`

## 3. Candidate Slices

| Candidate | Core surface | Fit | Risk | Judgment |
| --- | --- | --- | --- | --- |
| Worker handoff app spike | worker lifecycle, delegation policy, workspace grants, artifact `ResourceRef` handoff, replay/checkpoint | high | can accidentally imply real concurrency | recommended as red-test-only next batch |
| Session / run lifecycle review | multi-run continuity, run finalization, pause/cancel boundaries | medium | may become product workflow design | defer until worker spike exposes run-boundary friction |
| Error taxonomy boundary | helper / HTTP / projector error codes | medium | useful but less application-shaped | defer unless worker spike exposes inconsistent client errors |
| Tool invocation runtime wiring | executor constructs `ToolInvocation` as handler runtime object | medium | could overfit tool protocol before app pressure | defer until worker spike or app layer proves the need |

## 4. Recommendation

Recommend `Worker Handoff App Spike Red Tests` as the next bounded mainline batch.

The spike should stay deterministic and in-process. It should compose existing first-slice capabilities instead of creating a product multi-agent runtime:

- create session / run through existing server path
- submit a delegated worker handoff through `InProcessServer.submit_worker_handoff(...)`
- prove worker result handoff uses artifact / `ResourceRef` / provenance
- prove workspace access is grants-bound and read-model-only
- prove replay and checkpoint-assisted rebuild cover the handoff
- prove app/demo code does not use private `server._append(...)`

## 5. First Red Tests Recommendation

Suggested tests:

- `tests/isotope/test_worker_handoff_app_spike.py`
- `tests/isotope/test_worker_handoff_app_read_model.py`

Initial red-test coverage:

1. CLI/demo scenario exists: `python -m isotope.demo --scenario worker-handoff-app`.
2. JSON output includes scenario, run status, worker id, delegated action id, result artifact ref, workspace id, replay/checkpoint flags, and `worker_runtime_status="in_process_boundary_only"`.
3. Demo/app path uses `submit_worker_handoff(...)`, not private `_append(...)`.
4. Worker result handoff uses artifact / `ResourceRef` / provenance and does not expose full content by default.
5. Workspace access remains grants-bound; no implicit mode upgrade.
6. Replay and checkpoint-assisted rebuild restore worker, workspace, action, and artifact summaries.
7. No real concurrency, process spawn, remote worker, container, git worktree, real HTTP server, real LLM, provider adapter, or public SDK.

## 6. Stop Conditions

Stop if the spike requires:

- real worker process spawn, scheduler, process kill, or concurrency coordination
- remote worker runtime
- real filesystem workspace, container, git worktree, or cleanup scheduler
- real HTTP server, real LLM, provider/webhook, memory query/storage, or external credentials
- product UX decisions about multi-agent handoff
- event-store append-only semantic changes
- executor grants semantic changes

## 7. Decision

`Worker Handoff App Spike` is the right next pressure point because worker handoff app composition remains one of the few open core-level gaps not yet covered by an app-shaped scenario. The next mainline step should be red tests only. If those tests reveal only app-local glue, keep core unchanged; if they reveal bounded helper/read-model/replay/checkpoint friction, open a narrow green slice.

## 8. Follow-Up

Aggressive-dev commit `1993521` covered this pressure point before mainline opened the red-test batch. It exposed `worker.handoff.review` as a Capability Hub default capability and verified the helper-backed flow:

- `status=ok`
- `private_append_required=false`
- `app_friction=[]`
- no real worker runtime / scheduler / process spawn / remote worker / container / git worktree / real HTTP / LLM / provider / public SDK expansion

Current decision: do not start `Worker Handoff App Spike Red Tests` on mainline unless a later app-layer report identifies a new concrete `app_friction`. The selection remains useful as the boundary record for why the worker handoff app pressure point was valid and why it is now paused.
