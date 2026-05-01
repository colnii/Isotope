# Artifact Content Read Policy v0.2

状态：`draft boundary`

## 1. Purpose

Track C 的目标是定义 artifact full content（artifact 完整内容）什么时候可以被受控读取，而不是把 artifact content 默认暴露给所有 read path。

当前 v0.1 / v0.2 demo 已证明 artifact summary / ref / provenance 可以通过 canonical event 和 HTTP facade 被安全展示。但如果 v0.2 要更像可用 runtime，只展示 summary 还不够：调用方最终需要在明确授权下读取 artifact content。这个读取路径必须保持 ref-first、grant-gated、summary-by-default，不能绕过 kernel hard contracts。

本文件只定义 boundary。它不实现 retrieval engine、HTTP content endpoint、ranking、semantic search、binary streaming 或 real server。

## 2. Current Surface

当前已有能力：

- `ArtifactStore` 可以持久化 artifact metadata 和 content。
- `ArtifactStore.get_metadata(...)` 可以读取 artifact metadata / summary。
- `ArtifactStore.get_content(...)` 是 lower-level store primitive，但不是 public read policy。
- `RetrievalService.get_artifact_summary(...)` 已要求 structured `ResourceRef` 和 explicit grants。
- summary retrieval 已有 no-full-content-read 防回归测试。
- artifact created event 只携带 summary / ref / provenance，不携带 content。
- projector 只从 canonical events 投影 `RunState`，不读取 artifact content。
- checkpoint state 不夹带 artifact content。
- HTTP summary route `GET /artifacts/{artifact_id}/summary` 只返回 summary / ref / provenance。
- HTTP full content route `GET /artifacts/{artifact_id}/content` 当前仍是 deferred `501 not_enabled`。

## 3. Hard Boundaries

Track C 必须继续守住这些边界：

- 默认 read path 仍是 summary-only。
- artifact full content 不能默认出现在 projector read model、checkpoint state、event payload、HTTP summary response 或 demo JSON output 中。
- projector 不能读取 artifact content 推进 native state。
- checkpoint 不能读取或保存 artifact content。
- HTTP response 不能意外泄漏 artifact full content / raw content。
- URI-like string 不能绕过 structured `ResourceRef`。
- `ArtifactStore.get_content(...)` 不能被当作 authorization boundary；它只是 store primitive。
- content read 不能产生 native state event，不能修改 `RunState`，不能 append `artifact.read` success event as a side effect unless a later audit-event slice explicitly designs it。
- denied / downgraded retrieval 不能读取 full content 后再丢弃；必须在 content read 前 fail closed / downgrade。

## 4. v0.2 Minimal Goal

v0.2 最小目标是新增一个 controlled full-content retrieval boundary：

- full content 必须显式请求，例如 requested view / mode 是 `full`。
- request 必须携带 structured `ResourceRef`。
- request 必须携带 caller context，例如 caller / run / purpose / runtime context 的最小信息。
- request 必须携带 grants，例如 `{"artifact": {"read": "full"}}` 或等价 v0 shape。
- summary-only grant 只能返回 summary / ref / provenance。
- missing / malformed grants 必须受控拒绝。
- missing / malformed caller context 必须受控拒绝。
- URI string ref 必须拒绝。
- denied retrieval 应返回 denial 或抛受控 authorization error。
- downgraded retrieval 可以返回 summary view，但必须显式标记为 downgraded / limited，不能假装 full content 已返回。
- success response 只能在 full-content grant 明确允许时包含 content。

这仍是 in-process retrieval boundary，不是 hosted content API。

## 5. Candidate API Shape

字段名是 v0 candidate，不是永久 protocol。

可能的 service shape：

```python
RetrievalService.get_artifact_content(
    ref: ResourceRef,
    *,
    grants: dict,
    caller_context: dict,
    purpose: str,
) -> dict
```

可能的 success response：

```python
{
    "status": "ok",
    "view": "full",
    "ref": {...},
    "artifact_type": "text",
    "summary": "...",
    "content": "...",
    "provenance": {...},
}
```

可能的 downgraded response：

```python
{
    "status": "limited",
    "view": "summary",
    "reason": "full_content_not_granted",
    "ref": {...},
    "artifact_type": "text",
    "summary": "...",
}
```

可能的 denial response / exception：

```python
{
    "status": "denied",
    "reason": "artifact_full_content_not_granted",
}
```

v0 green slice 可以选择 exception-based denial 或 dict-based denial；测试应先锁定一种行为，避免混合语义。

## 6. HTTP Boundary

HTTP Track A 当前 closed。Track C 默认不重新打开 real HTTP server。

`GET /artifacts/{artifact_id}/content` 当前保持 deferred `501 not_enabled`，直到单独 red tests 明确要求打开 in-process facade content endpoint。

如果后续打开该 route，必须满足：

- 仍是 in-process `HttpApiApp` facade，不监听端口。
- 不引入 FastAPI / Flask / 新依赖。
- 不能复用 summary endpoint 返回 content。
- 必须使用同一套 `ResourceRef` / grants / caller context policy。
- missing grants / caller context 返回受控 error。
- response 不包含 internal store object、path、Python repr 或 unvalidated raw blob metadata。

## 7. Non-Goals

本阶段不进入：

- ranking
- semantic retrieval
- memory controlled expand
- memory query engine
- external ingestion
- binary streaming
- large artifact pagination
- partial range reads
- real HTTP server
- auth / multi-user policy
- audit-event design for artifact read
- public hosted content API

## 8. First Red Tests

下一轮建议新增：

```text
tests/isotope_kernel/test_artifact_content_read_policy.py
tests/isotope_kernel/test_http_api_artifact_content_boundary.py
```

第一批 red tests 应覆盖：

- retrieval summary 不返回 full content。
- full content request 必须带 structured `ResourceRef`。
- URI string request 被拒绝。
- missing grants 被拒绝。
- malformed grants 被拒绝。
- missing caller context 被拒绝。
- malformed caller context 被拒绝。
- grants 不允许 full content 时返回 downgraded summary 或 denied。
- grants 允许 full content 时才返回 content。
- full content read 不产生 canonical event。
- full content read 不修改 `RunState`。
- projector 不读取 artifact content。
- checkpoint 不夹带 artifact content。
- HTTP full content route 仍 `501 not_enabled`，直到对应 green slice 明确打开。
- HTTP summary route 继续不返回 content / raw content。

## 9. Acceptance For This Boundary

Track C 的第一段可以被认为完成，当：

- artifact summary path 仍 summary-only。
- controlled full-content read 的 authorization shape 已由 tests 固定。
- unauthorized read 在 content load 前 fail closed 或 downgraded。
- structured `ResourceRef` 是唯一 accepted reference shape。
- caller context / grants 是必填。
- projector / checkpoint / HTTP summary route 仍不暴露 full content。
- real HTTP server、external ingestion、memory controlled expand、ranking 和 semantic retrieval 仍 deferred。
