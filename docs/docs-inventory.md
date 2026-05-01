# Docs Inventory

状态：`current`

## 1. Purpose

本文盘点当前 `docs/` 下的 Markdown 文档，说明每份文档的用途、状态和后续整理方向。

本轮不移动、不删除、不合并任何文档。所有迁移建议都只是后续计划，必须另起 docs-only PR / commit 执行，并先维护 redirect / link map，避免 README、AGENTS、current-status、roadmap 或外部读者链接断掉。

盘点基线：

- 盘点前 existing docs Markdown：40 个。
- 加上本文后 docs Markdown：41 个。

## 2. Current entrypoints

这些文件是当前读者或 agent 应优先进入的文档，不建议近期移动：

- `docs/current-status.md`：当前状态入口，开始新任务前先读。
- `docs/v0.2-roadmap.md`：v0.2 track 状态和推荐顺序。
- `docs/v0.2-mid-cycle-review.md`：当前 mid-cycle decision，推荐下一阶段进入 Track E approval pause / resume boundary。
- `docs/v0.2-next-track-selection.md`：Track C selection 的历史决策记录，已执行到 closure。
- `docs/README.md`：kernel current-truth 文档包的阅读顺序入口。

根目录入口也仍然有效，但不计入 `docs/` 文件数量：

- `README.md`：外部 quick start 和短状态。
- `AGENTS.md`：agent workflow / repo boundary contract。

## 3. Active track docs

当前 active planning surface 是 Track E，但 Track E 专门文档尚未创建。

- Planned: `docs/approval-pause-resume-boundary-v0.2.md`
- Supporting current docs:
  - `docs/v0.2-mid-cycle-review.md`
  - `docs/v0.2-roadmap.md`
  - `docs/current-status.md`
  - `docs/deferred-boundary-review-v0.1.md`
  - `docs/kernel-spec-v0.1.md`
  - `docs/kernel-architecture-v0.1.md`
  - `docs/kernel-living-spec.md`

Track E 进入 TDD 前，应先写 boundary docs，再写 red tests。不要直接实现 approval resume。

## 4. Closed track docs

这些文档对应已经收口或冻结的 tracks。它们仍是当前 truth 的一部分，但不应默认继续扩展。

### v0.1 Demo / Demo Docs

- `docs/demo-entrypoint-v0.1.md`：demo entrypoint 设计，已实现。
- `docs/demo-walkthrough-v0.1.md`：demo walkthrough，current。
- `docs/demo-architecture-v0.1.md`：demo architecture diagram，current。
- `docs/v0.1-demo-acceptance.md`：developer demo acceptance，closed。
- `docs/release-draft-v0.1-demo.md`：GitHub Release draft，未发布。

### Track A: HTTP API Minimal Surface

- `docs/http-api-minimal-surface-v0.2.md`：closed for now。当前 HTTP API 是 in-process facade，不是 real listening HTTP server。

### Track C: Artifact Content Read Policy

- `docs/artifact-content-read-policy-v0.2.md`：closed for now。controlled full-content retrieval 只在 retrieval layer；HTTP full-content route 仍 `501 not_enabled`。

### Checkpoint v0.1 Frozen Surface

- `docs/checkpoint-v0.1-scope-freeze.md`
- `docs/checkpoint-ownership-v0.1.md`
- `docs/checkpoint-integrity-v0.1.md`
- `docs/checkpoint-history-fallback-v0.1.md`
- `docs/checkpoint-history-index-retention-v0.1.md`
- `docs/checkpoint-history-save-boundary-v0.1.md`
- `docs/checkpoint-history-save-integration-v0.1.md`
- `docs/checkpoint-migration-versioning-v0.1.md`
- `docs/checkpoint-retention-compaction-v0.1.md`
- `docs/checkpoint-save-trigger-v0.1.md`
- `docs/checkpoint-schema-version-fields-v0.1.md`
- `docs/server-checkpoint-boundary-v0.1.md`

### Memory v0.1 Frozen Surface

- `docs/memory-v0.1-scope-freeze.md`
- `docs/memory-write-query-boundary-v0.1.md`
- `docs/memory-record-persistence-boundary-v0.1.md`

Memory 当前只展示 boundary / read-model / checkpoint，不代表 durable memory storage 或 query engine 已实现。

## 5. Kernel Design Notes

这些是长期 design / architecture / implementation notes。部分是 current-truth 包，部分是 historical-but-still-useful notes。

- `docs/README.md`
- `docs/kernel-one-pager.md`
- `docs/commitment-levels.md`
- `docs/kernel-spec-v0.1.md`
- `docs/kernel-architecture-v0.1.md`
- `docs/kernel-decision-log.md`
- `docs/kernel-living-spec.md`
- `docs/implementation-plan-v0.1.md`
- `docs/coding-plan-v0.1.md`
- `docs/action-type-registry-v0.1.md`
- `docs/event-envelope-versioning-v0.1.md`
- `docs/event-envelope-schema-registry-v0.1.md`
- `docs/event-prefix-digest-v0.1.md`
- `docs/deferred-boundary-review-v0.1.md`

## 6. Inventory By File

| File | Primary use | Current status |
| --- | --- | --- |
| `docs/README.md` | Kernel current-truth reading order | current entrypoint |
| `docs/action-type-registry-v0.1.md` | Action registry design/status | closed / reference |
| `docs/artifact-content-read-policy-v0.2.md` | Track C boundary | closed for now |
| `docs/checkpoint-history-fallback-v0.1.md` | Checkpoint fallback boundary | closed / frozen |
| `docs/checkpoint-history-index-retention-v0.1.md` | Checkpoint history index / retention boundary | closed / frozen |
| `docs/checkpoint-history-save-boundary-v0.1.md` | Checkpoint history save boundary | closed / frozen |
| `docs/checkpoint-history-save-integration-v0.1.md` | Checkpoint history save integration boundary | closed / frozen |
| `docs/checkpoint-integrity-v0.1.md` | Checkpoint integrity boundary | closed / frozen |
| `docs/checkpoint-migration-versioning-v0.1.md` | Checkpoint migration/versioning boundary | closed / frozen |
| `docs/checkpoint-ownership-v0.1.md` | Checkpoint ownership boundary | closed / frozen |
| `docs/checkpoint-retention-compaction-v0.1.md` | Checkpoint retention/compaction boundary | closed / frozen |
| `docs/checkpoint-save-trigger-v0.1.md` | Checkpoint save trigger boundary | closed / frozen |
| `docs/checkpoint-schema-version-fields-v0.1.md` | Checkpoint schema/version fields | closed / frozen |
| `docs/checkpoint-v0.1-scope-freeze.md` | Checkpoint scope freeze | closed / frozen |
| `docs/coding-plan-v0.1.md` | Initial coding plan | historical / reference |
| `docs/commitment-levels.md` | Contract commitment levels | current reference |
| `docs/current-status.md` | Current repo status | current entrypoint |
| `docs/deferred-boundary-review-v0.1.md` | Deferred surface review | current reference |
| `docs/demo-architecture-v0.1.md` | Demo architecture diagram | current demo doc |
| `docs/demo-entrypoint-v0.1.md` | Demo entrypoint design | closed / implemented |
| `docs/demo-walkthrough-v0.1.md` | Demo walkthrough | current demo doc |
| `docs/event-envelope-schema-registry-v0.1.md` | Event schema registry boundary | closed / reference |
| `docs/event-envelope-versioning-v0.1.md` | Event envelope versioning boundary | closed / reference |
| `docs/event-prefix-digest-v0.1.md` | Event prefix digest boundary | closed / reference |
| `docs/http-api-minimal-surface-v0.2.md` | Track A HTTP API boundary | closed for now |
| `docs/implementation-plan-v0.1.md` | Initial implementation plan | historical / reference |
| `docs/kernel-architecture-v0.1.md` | Kernel architecture draft | current reference |
| `docs/kernel-decision-log.md` | Decision log | current reference |
| `docs/kernel-living-spec.md` | Living spec draft | current reference |
| `docs/kernel-one-pager.md` | Kernel one-pager | current reference |
| `docs/kernel-spec-v0.1.md` | Kernel spec draft | current reference |
| `docs/memory-record-persistence-boundary-v0.1.md` | Memory persistence boundary | closed / frozen |
| `docs/memory-v0.1-scope-freeze.md` | Memory scope freeze | closed / frozen |
| `docs/memory-write-query-boundary-v0.1.md` | Memory write/query boundary | closed / frozen |
| `docs/release-draft-v0.1-demo.md` | Release draft text | draft / not published |
| `docs/server-checkpoint-boundary-v0.1.md` | Server checkpoint boundary | closed / frozen |
| `docs/v0.1-demo-acceptance.md` | Demo acceptance record | closed |
| `docs/v0.2-mid-cycle-review.md` | v0.2 next-track review | current decision |
| `docs/v0.2-next-track-selection.md` | Track C selection record | historical decision |
| `docs/v0.2-roadmap.md` | v0.2 roadmap | current entrypoint |

## 7. Candidates For Future Subdirectories

未来可以考虑这些目录，但本轮不移动文件：

- `docs/tracks/`
  - `http-api-minimal-surface-v0.2.md`
  - `artifact-content-read-policy-v0.2.md`
  - future `approval-pause-resume-boundary-v0.2.md`
  - `v0.2-roadmap.md`
  - `v0.2-mid-cycle-review.md`
  - `v0.2-next-track-selection.md`
- `docs/kernel/`
  - `kernel-*.md`
  - `commitment-levels.md`
  - `action-type-registry-v0.1.md`
  - `event-envelope-*.md`
  - `event-prefix-digest-v0.1.md`
- `docs/checkpoint/`
  - all `checkpoint-*.md`
  - `server-checkpoint-boundary-v0.1.md`
- `docs/memory/`
  - all `memory-*.md`
- `docs/demo/`
  - `demo-*.md`
  - `v0.1-demo-acceptance.md`
- `docs/release/`
  - `release-draft-v0.1-demo.md`
- `docs/archive/` or `docs/history/`
  - `implementation-plan-v0.1.md`
  - `coding-plan-v0.1.md`
  - old selection / review docs only after current-status and roadmap no longer link them directly

## 8. Do-not-move-yet list

Do not move these files until a dedicated migration pass updates links and validates them:

- `docs/current-status.md`
- `docs/v0.2-roadmap.md`
- `docs/v0.2-mid-cycle-review.md`
- `docs/v0.2-next-track-selection.md`
- `docs/http-api-minimal-surface-v0.2.md`
- `docs/artifact-content-read-policy-v0.2.md`
- `docs/demo-walkthrough-v0.1.md`
- `docs/demo-architecture-v0.1.md`
- `docs/v0.1-demo-acceptance.md`
- `docs/kernel-spec-v0.1.md`
- `docs/kernel-architecture-v0.1.md`
- `docs/kernel-living-spec.md`

Reasons:

- README / AGENTS / current-status / roadmap link to these paths directly.
- Several files were recently shared or used as active task entrypoints.
- Moving them without redirects would break current onboarding and agent workflow.

## 9. Safe Migration Plan

Recommended future migration sequence:

1. Create `docs/docs-migration-plan.md` with exact old path -> new path mapping.
2. Add target subdirectories without moving files yet.
3. Update README / AGENTS / current-status / roadmap links in the same patch as any move.
4. Leave short stub files at old paths for at least one cycle, or add a compatibility index if stubs are not desired.
5. Run link checks with `rg` for every old basename and ensure no stale references remain.
6. Run the normal verification suite.
7. Commit moves separately from content rewrites to keep review clean.

Do not combine directory migration with implementation work.
