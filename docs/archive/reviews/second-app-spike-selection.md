# Second App Spike Selection

状态：`complete; recommendation selected`

## 1. Purpose

本文选择第二个 app-shaped usability pressure test（可用性压力测试）候选。

第一个 app spike `artifact-review` 已 closed for now。它主要覆盖 artifact summary / `ResourceRef` / controlled content retrieval / provenance / replay / checkpoint。第二个 spike 应该故意压力测试不同 kernel surface，而不是继续扩展 artifact review。

本轮只做 docs-only selection review，不新增测试、不写实现、不新增 scenario。

## 2. Selection Criteria

候选按以下标准评估：

- 能否暴露 developer ergonomics friction。
- 是否覆盖 `artifact-review` 没覆盖的 kernel 面。
- 是否保持 deterministic / in-process。
- 是否不需要 real LLM、real HTTP server、provider adapter、filesystem mutation 或 memory query engine。
- 是否能在 1-2 个小 TDD package 内完成。
- 是否低风险，不诱导 product-level API 过早膨胀。

## 3. Candidate Comparison

| Candidate | Kernel surfaces pressured | Usability friction likely exposed | Risk | Fit |
| --- | --- | --- | --- | --- |
| `approval-gated workspace task` | approval + workspace binding + worker/delegation + retry/cancel/supersede | approval-gated submission, workspace binding, cancellation/retry surface composition | medium-high: overlaps `approval-tool-runner` and touches too many surfaces at once | not second |
| `external snapshot review` | `ImportedSnapshot`, `RunState.external_observations`, conflict diagnostics, native state priority, replay/checkpoint | snapshot setup helper, conflict read-model shape, external observation summary access, no-provider ingestion boundary | low-medium: can stay deterministic and in-process without provider adapter | recommended |
| `worker handoff task` | Agent / Worker lifecycle, delegation policy, worker result handoff, workspace grants | delegation proposal helper, worker read helper, result handoff ergonomics | medium: valuable but may look like multi-agent runtime before real concurrency exists | good later |
| `memory boundary review` | memory record read model, supersession, checkpoint | memory record setup/read ergonomics, supersession read model | medium-high: easy to drift into memory query/storage/promotion | defer |

## 4. Recommendation

推荐第二个 app spike：`external snapshot review`。

原因：

- It covers Track F surfaces not exercised by `approval-tool-runner` or `artifact-review`。
- It can be deterministic and in-process: use fixed imported snapshot payloads, not provider callbacks。
- It pressure tests external observations as lower-priority diagnostic state, including conflict marking and native state priority。
- It should reveal whether creating / accepting `ImportedSnapshot` and reading conflict diagnostics is ergonomic enough for app-shaped flows。
- It can stay within 1-2 small TDD packages: red tests first, then a minimal scenario/helper slice if red is clean。
- It avoids product overclaim because HTTP `/external-ingestion` remains `not_enabled` and no provider adapter is opened。

This choice does not require product judgment because it is a technical coverage decision: it targets an already closed kernel boundary that has not yet been exercised by an app-shaped flow.

## 5. Why Not The Others Now

`approval-gated workspace task` is not selected now because it overlaps with the already closed `approval-tool-runner` spike and would combine approval, workspace, worker/delegation, and retry/cancel/supersede in one package. That is likely too broad for the next narrow pressure test.

`worker handoff task` is a strong later candidate. It covers Agent / Worker lifecycle gaps better than `external snapshot review`, but it is more likely to create pressure for real concurrency, process spawn, or product-like multi-agent semantics. It should come after one more low-risk non-artifact app spike or after a worker-helper friction review.

`memory boundary review` is deferred because the current memory line is intentionally boundary-only. A spike here would too easily be mistaken for memory query/storage/promotion, which remains deferred.

## 6. First Red Tests Recommendation

Next suggested batch: `External Snapshot Review Red Tests`, red phase only.

Suggested files:

- `tests/isotope/test_external_snapshot_review_spike.py`
- `tests/isotope/test_external_snapshot_review_read_model.py`

Suggested test goals:

- `external-snapshot-review` scenario is deterministic / in-process。
- no real LLM, real HTTP server, provider adapter, webhook, filesystem mutation, or memory query engine。
- scenario starts from accepted `ImportedSnapshot` / canonical `snapshot.imported` events, not raw provider callbacks。
- external observations appear in `RunState.external_observations` with quality, provenance, freshness, and basis refs。
- conflicting snapshots are exposed as conflict diagnostics, not merged into native fact。
- imported observation never overrides native `RunState.status` or action status。
- review / diagnostic action, if present, goes through canonical action chain and policy grants。
- review result handoff uses artifact / `ResourceRef` / canonical event if it produces an artifact。
- replay and checkpoint-assisted rebuild restore the same external observation / conflict read model。
- HTTP `/external-ingestion` remains `501 not_enabled`。
- projector does not read raw artifact content or provider payload content to advance native state。
- demo / JSON output does not contain raw provider body or artifact full content。

## 7. Stop Conditions For Next Batch

Stop before green or implementation if:

- red tests require real provider adapter, webhook, network listener, or real HTTP server。
- red tests require imported observations to override native state。
- red tests require projector to read raw artifact content or provider body content。
- red tests require memory query/storage/promotion。
- red tests require filesystem mutation, container, git worktree, or process spawn。
- red tests expose a source-of-truth conflict between Track F docs and implementation。
- full regression has non-batch failures。
- the next scenario semantics require product / user judgment。

## 8. Queue Outcome

Queue should move to `External Snapshot Review Red Tests` as the next suggested batch with `ready_red_only` status.

Do not implement the scenario until a later batch explicitly allows green phase.
