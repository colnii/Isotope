# Artifact Review Provenance Helper Boundary v0.2

状态：`boundary defined`

## 1. Why This Helper Exists

`artifact-review` spike 已经通过 `InProcessServer.create_source_artifact(...)` 移除了 source artifact setup 的 private append glue。

剩余 friction 更窄：demo / client 为了给 review provenance 填入 source artifact 的 `artifact.created` basis event，仍需要扫描 raw event log。

这个 helper 的目标是把该 read concern 收进 in-process server/helper 层，让 app spike 可以读取 artifact summary / ref / provenance / basis event metadata，而不是直接遍历 raw canonical events。

## 2. Minimal Boundary

推荐 helper shape：

- `InProcessServer.get_artifact_record(ref)`
- 或等价的 `get_artifact_provenance(ref)` / `get_artifact_created_event(...)`

本 slice 默认使用 `get_artifact_record(ref)`，因为 artifact review 需要的不只是 event id，还需要 summary / structured ref / provenance。

Helper 只能返回：

- structured `ResourceRef`
- artifact id / type
- artifact summary
- artifact provenance
- source `artifact.created` event metadata:
  - `basis_event_id`
  - `basis_event_type`
  - `basis_created_at`

Helper 不能返回：

- full artifact content
- raw artifact content
- file path content
- artifact store internal object repr
- raw event object

## 3. Hard Boundaries

- Helper must accept structured `ResourceRef` only.
- URI string / raw artifact id must be rejected.
- Unknown artifact must return controlled error / not found.
- Helper must not append events.
- Helper must not mutate `RunState` / `SessionState`.
- Helper must not read full artifact content.
- Helper must not open HTTP full-content route.
- Helper must not become product-level artifact review facade.
- Helper must not change event store append-only semantics.

## 4. Intended Use In `artifact-review`

`artifact-review` should call the helper after source artifact setup:

```python
source_record = app.server.get_artifact_record(source_ref)
```

Review provenance can then use:

- `source_record["ref"]`
- `source_record["summary"]`
- `source_record["provenance"]`
- `source_record["basis_event_id"]`

The demo may still read event types for compact status / trace output, but it should not scan raw events to find the source `artifact.created` event.

## 5. First Red Tests

Add `tests/isotope_kernel/test_artifact_provenance_helper.py` covering:

- helper exists.
- helper accepts structured `ResourceRef` only.
- URI string / raw artifact id is rejected.
- unknown artifact returns controlled error / not found.
- helper returns provenance metadata sufficient for review flow.
- helper does not return full content.
- helper does not append events.
- HTTP full-content route remains `not_enabled`.

Extend `tests/isotope_kernel/test_artifact_review_flow_spike.py` to cover:

- `artifact-review` uses the helper.
- `artifact-review` no longer scans raw events for source `artifact.created` basis event.

## 6. Deferred

Still deferred:

- product artifact review API.
- artifact review facade.
- real HTTP full-content route.
- real HTTP server.
- semantic retrieval / ranking.
- file upload / binary streaming.
- provider adapter / real LLM.
- filesystem mutation outside existing artifact store persistence.
