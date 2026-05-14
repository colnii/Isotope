# Source Artifact Setup Helper Boundary v0.2

状态：`closed / complete`

## 1. Purpose

`artifact-review` spike 暴露了一个具体 developer ergonomics（开发者易用性）问题：为了准备 source artifact（源 artifact），demo 需要直接调用 private `server._append(...)` 手工拼 `action.proposed -> action.decided -> action.started -> artifact.created -> action.completed`。

本文定义一个窄 helper boundary（辅助接口边界）：让 deterministic in-process app spike 可以通过受控路径创建 source artifact，同时不把它升级成 product artifact upload API。

## 2. Current Friction

当前 source setup 的问题不是 kernel contract 错了，而是 caller 需要知道太多 event plumbing：

- hard-coded proposal / decision / execution ids。
- direct private `server._append(...)` calls。
- direct `artifact_store.create_artifact(...)` call。
- manual `artifact.created` payload assembly。
- manual action completion event assembly。

这些步骤仍然产生 canonical events，但不适合作为 demo / app helper 的 public path。

## 3. Helper Scope

推荐 helper 名称：`InProcessServer.create_source_artifact(...)`。

最小输入：

- `run_id`
- `summary`
- `content`
- optional `artifact_type`, default `text`

最小输出：

- `status`
- `proposal_id`
- `decision_id`
- `execution_id`
- `artifact_ref`
- `artifact_summary`
- `artifact_type`
- `provenance`
- `run_state`

输出必须是 summary / ref / provenance oriented，不返回 artifact full content。

## 4. Required Semantics

Helper must:

- validate request before appending events or writing artifacts。
- append canonical action / policy / execution / artifact events, or a clearly controlled setup path using the same canonical event names。
- create artifact through `ArtifactStore` so metadata / content persistence remains under the existing artifact boundary。
- return structured `ResourceRef`。
- return provenance that includes execution id。
- allow event replay to recover source artifact summary / ref / provenance。
- allow checkpoint-assisted rebuild to recover the source artifact summary / ref / provenance。
- keep HTTP full-content route `not_enabled`。

## 5. Hard Boundaries

Helper must not:

- expose full artifact content in its returned summary。
- let projector read artifact content to advance native state。
- mutate `RunState` directly。
- bypass append-only event log semantics。
- change executor grants semantics。
- implement real file upload。
- mutate real filesystem outside the existing artifact store path。
- implement binary streaming。
- implement real HTTP server。
- implement provider adapter。
- implement memory query engine。
- become an artifact review product facade。

## 6. Acceptable v0 Shape

It is acceptable for the first slice to be setup-helper scoped rather than a general upload API.

The helper can internally own the canonical source setup sequence. The important boundary is that external callers no longer need to hand-write private `_append(...)` calls, and projected state still comes only from canonical events.

## 7. First Green Slice

Implemented:

- `InProcessServer.create_source_artifact(...)`
- tests in `tests/isotope_kernel/test_source_artifact_setup_helper.py`
- closure review in `../features/source-artifact-helper-closure-review.md`

Current behavior:

- creates a source artifact with summary / structured `ResourceRef` / provenance。
- returns no full content。
- appends canonical `action.proposed`, `action.decided`, `action.started`, `artifact.created`, and `action.completed` events。
- does not append `run.completed` during source setup。
- is replayable into `RunState.artifacts`。
- is checkpoint-assisted rebuildable。
- rejects malformed summary / content before appending events or writing artifacts。
- rejects binary content input。
- leaves HTTP full-content route `not_enabled`。
- is used by `artifact-review` demo instead of private `server._append(...)` source setup glue。

Still deferred:

- product artifact upload API。
- real filesystem upload。
- binary streaming。
- real HTTP server。
- provider adapter。
- memory query engine。

## 8. First Red Tests

Suggested file:

- `tests/isotope_kernel/test_source_artifact_setup_helper.py`

Test coverage:

- helper creates source artifact with summary / structured ref / provenance。
- helper return does not include full content。
- helper appends canonical events, not direct state mutation。
- replay restores source artifact read model。
- checkpoint-assisted rebuild restores source artifact read model。
- malformed setup request fails fast without partial artifact state。
- `artifact-review` demo uses helper instead of private `server._append(...)` source setup glue。
- HTTP full-content route remains `not_enabled`。
- no real filesystem upload / binary streaming / provider / network surface。

## 9. Non-Goals

This slice does not implement:

- product artifact upload API。
- file picker / multipart upload。
- binary artifact streaming。
- filesystem watcher。
- semantic retrieval or ranking。
- memory query。
- real HTTP server。
- real LLM / provider adapter。
- full artifact review facade。
