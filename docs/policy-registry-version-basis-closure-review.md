# Policy Registry Version Basis Closure Review

状态：`first slice complete / closed for now`

## 1. Purpose

本文审查 Policy Profile / Action Registry Versioning first slice 是否可以关闭。审查范围只包括 registry / policy basis metadata、canonical event payload、projector read model、replay / checkpoint-assisted rebuild 和 deferred boundary。

本轮不扩大到 plugin marketplace、remote registry loading、policy DSL、product policy UI、schema migration framework 或 dynamic action execution。

## 2. Closure Judgment

结论：可以标为 `first slice complete / closed for now`。

理由：

- `ActionTypeRegistry.default()` exposes stable `registry_id="default"` / `registry_version="v0.2"`。
- custom `ActionTypeRegistry(...)` 可以显式传入 registry metadata，malformed metadata fail fast。
- `ActionCompiler(registry=...)` 会把 registry id / version 写入 `ActionProposal`。
- `ActionProposal.registry_basis` 提供 structured basis dict，并进入 canonical `action.proposed` event payload。
- `PolicyEngine(...)` exposes `policy_profile_id="default"` / `policy_version="v0.2"`，也支持 explicit profile/version metadata，malformed metadata fail fast。
- `PolicyDecision.policy_basis` 提供 structured basis dict，并进入 canonical `action.decided` event payload。
- `RunProjector` 对 `action.proposed` / `action.decided` basis metadata 做 strict validation。
- `RunState.actions` summaries 可展示 registry / policy basis metadata 和 `reason_codes`。
- replay / checkpoint-assisted rebuild 使用 event payload / projected action summaries，不依赖当前 mutable default registry / policy profile。

实现没有引入 plugin marketplace、remote registry loading、policy DSL、product policy UI、schema migration framework、新依赖、real HTTP server、real LLM、provider adapter、memory query engine 或 filesystem substrate。

## 3. Evidence Checklist

| Check | Result | Evidence |
| --- | --- | --- |
| Registry id / version | pass | `ActionTypeRegistry.registry_id` / `registry_version` default to `default` / `v0.2` and support explicit metadata |
| Registry basis | pass | `ActionProposal.registry_basis` and `action.proposed.registry_basis` carry the structured registry basis derived from compiler registry metadata |
| Action proposal event basis | pass | `InProcessServer` writes `registry_id`, `registry_version`, and `registry_basis` into `action.proposed` |
| Policy profile / version | pass | `PolicyEngine.policy_profile_id` / `policy_version` default to `default` / `v0.2` and support explicit metadata |
| Policy basis | pass | `PolicyDecision.policy_basis` and `action.decided.policy_basis` carry the structured policy basis |
| Action decided event basis | pass | `InProcessServer` writes `policy_profile_id`, `policy_version`, and `policy_basis` into `action.decided` |
| Action read model basis | pass | `RunProjector` projects registry / policy basis into `RunState.actions` |
| Replay independence | pass | targeted tests monkeypatch current defaults and verify projector uses event payload basis |
| Checkpoint rebuild | pass | action summaries preserve basis metadata through checkpoint state |
| Grants snapshot | pass | executor still executes `PolicyDecision.grants`, not requested capabilities or current policy |
| Unknown action type | pass | compiler / policy boundary still fail closed |
| Stable reason codes | pass | modified / denied decisions use stable identifier strings such as `capabilities_reduced` and `tool_not_requested` |

## 4. Non-Goals Kept Deferred

Still deferred:

- plugin marketplace
- dynamic plugin loading
- remote registry loading
- signed registry bundles
- policy DSL
- product policy UI
- multi-tenant policy profile management
- backward-compatible schema migration framework
- content-addressed registry bundle store
- event schema compatibility engine
- real LLM tool-calling integration

## 5. Remaining Friction

Remaining friction is not blocker-level:

- `ActionTypeRegistry` and `PolicyEngine` expose id / version directly, while structured basis dicts are materialized on `ActionProposal` / `PolicyDecision` and event payloads. This is acceptable for the first slice because the replay boundary is canonical event payload, not mutable registry / policy objects.
- `reason_codes` are stable identifiers, but the repo still lacks a fuller reason-code taxonomy / compatibility document.
- event schema registry and migration remain separate kernel gaps.

## 6. Recommended Next Path

Recommended next path: `Retry / Cancel / Supersede Runtime Integration Boundary`.

Reason:

- registry / policy basis is now closed enough for future action lifecycle work.
- retry / cancel / supersede projector/read-model slices exist, but runtime request acceptance / rejection / effective-state semantics are still thin.
- this should stay docs-only first and must not introduce scheduler, process kill, real concurrency, plugin loading, policy DSL, or migration framework.

Alternatives:

- `Worker Handoff App Spike Selection` if the goal is app-level usability pressure.
- `External Review Package Refresh` if the near-term goal is reviewer handoff instead of more kernel design.

## 7. Verification

Closure verification should include:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope_kernel -q
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario artifact-review --trace
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario external-snapshot-review --trace
rg -n '(^|\s)(from|import) x_agent\b' src/isotope_kernel tests/isotope_kernel
git diff -- src tests .github pyproject.toml
```
