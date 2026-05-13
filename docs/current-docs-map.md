# Current Docs Map

状态：`current / docs-only rollup`

## 1. Purpose

本文是当前 `docs/` 的归纳入口。它不替代 `docs/current-status.md`，也不改变任何 kernel contract；它只回答三个问题：

- 现在先读哪几份文档。
- 115+ 份 Markdown 大致分成哪些层。
- 哪些文档是 current truth，哪些只是 concept / archive / compatibility stub。

本轮整理不移动、不删除、不合并文档，不修改 `src/`、`tests/`、`.github/` 或 `pyproject.toml`。如果以后要继续目录迁移，仍以 [Docs Migration Plan](./docs-migration-plan.md) 为准。

## 2. Fast Reading Paths

### 2.1 只想知道项目当前状态

1. [README](../README.md) 看 quick start 和短状态。
2. [Current Status](./current-status.md) 看 authoritative current truth。
3. [Mainline Idle Checkpoint](./mainline-idle-checkpoint.md) 看为什么主线现在停在 maintenance / friction intake。
4. [Kernel Mainline Maintenance Mode](./kernel-mainline-maintenance-mode.md) 看哪些事情默认不再主动打开。

### 2.2 后续 agent 开始主线任务

1. [Current Status](./current-status.md)
2. [v0.2 Roadmap](./v0.2-roadmap.md)
3. [Agent Task Queue](./agent-task-queue.md)
4. [Docs Migration Plan](./docs-migration-plan.md)，仅当任务涉及文档移动 / 目录重排时读取。

如果任务是 docs-only，仍不得修改 `src/`、`tests/`、`.github/` 或 `pyproject.toml`。如果任务可能重开 kernel implementation，先确认是否有 app-layer friction 或 external review feedback。

### 2.3 给外部 reviewer

1. [External Review Package v0.2](./external-review-package-v0.2.md)
2. [Post External Review Checkpoint](./post-external-review-checkpoint.md)
3. [App Spike Coverage Review](./app-spike-coverage-review.md)
4. [Kernel Gap Review Refresh](./kernel-gap-review-refresh-v0.2.md)
5. Closure reviews for the slices being reviewed, such as [Tool Protocol Closure Review](./tool-protocol-closure-review.md), [Error Taxonomy Closure Review](./error-taxonomy-closure-review.md), and [Workspace Resource Lifecycle Closure Review](./workspace-resource-lifecycle-closure-review.md).

### 2.4 想跑 demo / trace

1. [Demo Walkthrough](./demo/demo-walkthrough-v0.1.md)
2. [Demo Architecture](./demo/demo-architecture-v0.1.md)
3. [v0.2 Demo Scenario](./demo/v0.2-demo-scenario.md)
4. [Agent Loop Friction Review](./agent-loop-friction-review.md)
5. [Agent Loop Planner Adapter Friction Review](./agent-loop-planner-adapter-friction-review.md)
6. [Agent Loop Planner Matrix Friction Review](./agent-loop-planner-matrix-friction-review.md)
7. [Planner Runner API Boundary Review](./planner-runner-api-boundary-review.md)
8. [v0.2 Demo Acceptance](./demo/v0.2-demo-acceptance.md)

`--trace` 是 human-readable runtime trace；`--json` 是 machine-readable summary。两者都不应暴露 artifact full content。

## 3. Docs Layers

### 3.1 Control Plane / Status

这些是当前操作入口和状态控制面：

- [Current Status](./current-status.md)
- [v0.2 Roadmap](./v0.2-roadmap.md)
- [Agent Task Queue](./agent-task-queue.md)
- [Post v0.2 Tag Delta](./post-v0.2-tag-delta.md)
- [v0.2 Cycle Closure Review](./v0.2-cycle-closure-review.md)
- [External Review Package v0.2](./external-review-package-v0.2.md)
- [Post External Review Checkpoint](./post-external-review-checkpoint.md)
- [Kernel Mainline Maintenance Mode](./kernel-mainline-maintenance-mode.md)
- [Mainline Idle Checkpoint](./mainline-idle-checkpoint.md)
- [Public / Internal Docs Boundary](./public-internal-docs-boundary.md)

### 3.2 Kernel Current-Truth Package

这些是 kernel design / architecture / contract 的主要说明：

- [Docs README](./README.md)
- [Kernel One-Pager](./kernel-one-pager.md)
- [Commitment Levels](./commitment-levels.md)
- [Kernel Spec v0.1](./kernel-spec-v0.1.md)
- [Kernel Architecture v0.1](./kernel-architecture-v0.1.md)
- [Kernel Living Spec](./kernel-living-spec.md)
- [Kernel Decision Log](./kernel-decision-log.md)
- [Action Type Registry](./action-type-registry-v0.1.md)
- Event envelope / event schema docs: [Event Envelope Versioning](./event-envelope-versioning-v0.1.md), [Event Envelope Schema Registry](./event-envelope-schema-registry-v0.1.md), [Event Schema Registry / Compatibility Boundary](./event-schema-registry-compatibility-boundary-v0.2.md), and [Event Schema Registry Closure Review](./event-schema-registry-closure-review.md).

### 3.3 Closed v0.2 Track / Boundary Docs

这些文档记录已经 closed for now 的 kernel slices。它们仍是 current truth，但不代表下一步要继续扩展：

- Track A: [HTTP API Minimal Surface](./http-api-minimal-surface-v0.2.md)
- Track C: [Artifact Content Read Policy](./artifact-content-read-policy-v0.2.md)
- Track E: [Approval Pause / Resume Boundary](./approval-pause-resume-boundary-v0.2.md)
- Track F: [External Ingestion Boundary](./external-ingestion-boundary-v0.2.md)
- [Agent / Worker Lifecycle Boundary](./agent-worker-lifecycle-boundary-v0.2.md)
- [Workspace Substrate Boundary](./workspace-substrate-boundary-v0.2.md)
- [Workspace Resource Lifecycle Boundary](./workspace-resource-lifecycle-boundary-v0.2.md)
- [VCS / Git Optional Boundary](./vcs-git-optional-boundary-v0.2.md)
- [Retry / Cancel / Supersede Boundary](./retry-cancel-supersede-boundary-v0.2.md)
- [Retry / Cancel / Supersede Runtime Integration Boundary](./retry-cancel-supersede-runtime-integration-boundary-v0.2.md)
- [Policy Profile / Action Registry Versioning Boundary](./policy-profile-action-registry-versioning-boundary-v0.2.md)
- [Tool Protocol Boundary](./tool-protocol-boundary-v0.2.md)
- [Tool Invocation Runtime Wiring Boundary](./tool-invocation-runtime-wiring-boundary-v0.2.md)
- [Restart Write Helper Run Context Boundary](./restart-write-helper-run-context-boundary-v0.2.md)
- [Session / Run Lifecycle Boundary](./session-run-lifecycle-boundary-v0.2.md)
- [Error Taxonomy Boundary](./error-taxonomy-boundary-v0.2.md)
- [Worker Handoff Helper Boundary](./worker-handoff-helper-boundary-v0.2.md)

### 3.4 App Spike / Friction / Helper Reviews

这些文档说明 application-layer spike 如何 pressure-test kernel boundary，以及哪些 helper 已经收口：

- [Usability Pressure Test Plan](./usability-pressure-test-plan-v0.2.md)
- [Approval Tool Runner Friction Review](./approval-tool-runner-friction-review.md)
- [Workspace Binding Helper Friction Review](./workspace-binding-helper-friction-review.md)
- [Workspace Binding Helper Boundary](./workspace-binding-helper-boundary-v0.2.md)
- [Submit Tool Request Friction Review](./submit-tool-request-friction-review.md)
- [Submit Action Helper Boundary](./submit-action-helper-boundary-v0.2.md)
- [Artifact Review Flow Friction Review](./artifact-review-flow-friction-review.md)
- [Artifact Review Flow Closure Review](./artifact-review-flow-closure-review.md)
- [Source Artifact Setup Helper Boundary](./source-artifact-setup-helper-boundary-v0.2.md)
- [Source Artifact Helper Closure Review](./source-artifact-helper-closure-review.md)
- [Artifact Review Provenance Helper Boundary](./artifact-review-provenance-helper-boundary-v0.2.md)
- [External Snapshot Review Closure Review](./external-snapshot-review-closure-review.md)
- [Agent Loop Friction Review](./agent-loop-friction-review.md)
- [Agent Loop Planner Adapter Friction Review](./agent-loop-planner-adapter-friction-review.md)
- [Agent Loop Planner Matrix Friction Review](./agent-loop-planner-matrix-friction-review.md)
- [Planner Runner API Boundary Review](./planner-runner-api-boundary-review.md)
- [App Spike Coverage Review](./app-spike-coverage-review.md)

### 3.5 Frozen v0.1 Surfaces

这些是 v0.1 frozen / historical-but-still-useful surfaces：

- Checkpoint docs: `checkpoint-*.md` plus [Server Checkpoint Boundary](./server-checkpoint-boundary-v0.1.md)
- Memory docs: [Memory v0.1 Scope Freeze](./memory-v0.1-scope-freeze.md), [Memory Write / Query Boundary](./memory-write-query-boundary-v0.1.md), and [Memory Record Persistence Boundary](./memory-record-persistence-boundary-v0.1.md)
- Initial plan docs: [Implementation Plan v0.1](./implementation-plan-v0.1.md) and [Coding Plan v0.1](./coding-plan-v0.1.md)

Memory 当前只声明 boundary / read-model / checkpoint 能力，不声明 durable storage 或 query engine 已完成。

### 3.6 Concepts / Application Pressure

[Concept Docs](./concepts/README.md) 保存早期 Isotope 概念、study companion 设想和 reference-project comparisons。它们可以产生 kernel requirements，但不是 current implementation truth，也不应原样当成 public product docs。

### 3.7 Compatibility Stubs

旧路径 stub 用来保护已有链接，例如：

- `docs/demo-*.md` old paths point to `docs/demo/`
- `docs/v0.1-demo-acceptance.md`
- `docs/v0.2-demo-*.md`
- `docs/release-draft-v0.1-demo.md`
- `docs/event-schema-compatibility-boundary-v0.2.md`

这些 stub 不应被当成完整文档。未来删除 stub 需要单独 link audit。

## 4. What Counts As Current Truth

优先级从高到低：

1. Actual code and tests under `src/isotope_kernel/` and `tests/isotope_kernel/`.
2. [Current Status](./current-status.md), [README](../README.md), and [AGENTS](../AGENTS.md).
3. Closure reviews and boundary docs for the specific slice.
4. [Docs Inventory](./docs-inventory.md) and this map for navigation.
5. Concept docs and historical plans as background only.

如果这些文档冲突，先检查 actual code / tests，再同步 `current-status`、`README`、`AGENTS` 和相关 boundary / closure doc。

## 5. Current Organization Decision

本轮只做归纳，不做目录迁移。

原因：

- `docs-migration-plan.md` 已明确 Phase 1 closed / paused。
- `README.md`、`AGENTS.md`、`current-status.md` 和 `v0.2-roadmap.md` 直接链接大量根层 docs。
- 大量 boundary / closure docs 仍用于 external review 和 future friction intake。
- 直接移动 track / checkpoint / memory / kernel docs 会带来高链接风险。

后续如果明确要继续迁移，建议顺序仍是：closed Track A / C / E docs first；checkpoint、memory、kernel、status entrypoints 分开做；每次迁移都保留 stub、同 commit 更新链接、跑 link audit 和 verification。
