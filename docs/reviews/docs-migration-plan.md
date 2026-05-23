# Docs Migration Plan

状态：`phase 1 closed / paused`

## 1. Purpose

本文把 `../archive/docs-inventory-pre-reorg.md` 的盘点结果转成可执行迁移计划。

本轮只写计划，不移动、不删除、不合并任何文档，不批量修改链接，不修改 `src/`、`tests/`、`.github/` 或 `pyproject.toml`。

Phase 1 dry-run 已记录在 `docs-migration-phase-1-dry-run.md`。Phase 1a 已执行：release draft 已迁移到 `../archive/release/release-draft-v0.1-demo.md`。Phase 1b 已执行：v0.1 demo explainer docs 已迁移到 `docs/demo/`。Phase 1c 已执行：demo acceptance / readiness / scenario docs 已迁移到 `docs/demo/`。Phase 1d 已执行：低风险旧路径 compatibility stubs 已在链接审计后删除。

Phase 1 当前 closed / paused。不要继续迁移 track docs、checkpoint docs、memory docs、kernel docs、`../current/status.md` 或 `../architecture/v0.2-roadmap.md`，除非用户明确请求下一批迁移。Kernel Gap Review 已在 `kernel-gap-review-v0.2.md` 落地，Agent / Worker lifecycle boundary 已在 `../architecture/agent-worker-lifecycle-boundary-v0.2.md` 落地；默认下一阶段可进入对应 red tests 或 Workspace substrate boundary design。

2026-05-24 旧文档清理补充：用户明确要求先处理旧文档，因此只执行低风险
historical plan（历史计划）归档；仍不移动 track、checkpoint、memory、kernel、
current status 或 roadmap 入口。

## 2. Target Directory Structure

建议未来目录结构：

```text
docs/
  status/
  tracks/
  kernel/
  checkpoint/
  memory/
  demo/
  release/
  archive/
```

目录用途：

- `docs/status/`：current status、roadmap、cycle reviews、tag delta、docs inventory / migration plan。
- `docs/tracks/`：Track A / C / E / F boundary docs and deferred-track review docs。
- `docs/kernel/`：kernel spec、architecture、event envelope、action registry、decision log、commitment levels。
- `docs/checkpoint/`：checkpoint ownership / integrity / history / schema / server boundary docs。
- `docs/memory/`：memory write/query/persistence/scope docs。
- `docs/demo/`：demo walkthrough、architecture、entrypoint、acceptance、readiness、scenario。
- `docs/release/`：release draft docs。
- `docs/archive/`：historical implementation/coding plans after links are stable.

## 3. Safety Rules

- Do not move files without a dedicated migration commit.
- Do not combine directory migration with implementation work.
- Keep `../current/status.md` and `../architecture/v0.2-roadmap.md` at their current paths through the first migration wave.
- Leave compatibility stub files at old paths for high-risk entrypoints and externally shared docs.
- Update links in the same commit as any move.
- Run the full verification suite after each migration wave.
- If link checks fail or tests fail, revert the migration commit rather than patching around broken paths blindly.

## 4. Migration Waves

Recommended order:

1. Phase 1a completed: `../archive/release/release-draft-v0.1-demo.md` now holds the full release draft.
2. Phase 1b completed: v0.1 demo explainer docs moved to `docs/demo/`.
3. Phase 1c completed: demo acceptance / readiness / scenario docs moved to `docs/demo/`.
4. Phase 1d completed: low-risk old-path compatibility stubs for demo, release draft, and event schema compatibility were removed after link audit.
5. Low-risk historical v0.1 implementation / coding plans moved to `../archive/plans/` after explicit user request for old-doc cleanup.
6. Pause migration after the low-risk old-doc cleanup; do not move track / checkpoint / memory / kernel / status entrypoint docs by default.
7. If migration is explicitly reopened later, move closed Track A / C / E docs to `docs/tracks/` with stubs and same-commit link updates.
8. Move checkpoint docs only as a separate later batch.
9. Move memory docs only as a separate later batch.
10. Move remaining track docs only after recent Track F links settle.
11. Move kernel docs only as a separate later batch.
12. Move status entrypoints only after README / AGENTS / current-status / roadmap link checks are stable.

Do not combine the next track-doc migration with later checkpoint / memory / kernel migrations unless there is a specific review reason to take the extra link risk.

## 4.1 Phase 1 Closure Decision

Phase 1 is closed / paused at the current state:

- migrated: `docs/release/`
- migrated: `docs/demo/`
- low-risk old-path compatibility stubs removed after link audit
- Markdown links were audited after Phase 1c and resolved cleanly
- no code, tests, `.github`, or `pyproject.toml` changes are part of this migration phase

Do not continue with track, checkpoint, memory, kernel, current-status, or roadmap migrations as an implied follow-up. Kernel Gap Review and Agent / Worker lifecycle boundary have landed; the next default workstream is the corresponding red tests or Workspace substrate boundary design unless the user explicitly asks for another docs migration batch.

## 5. Do Not Move In First Wave

Keep these in place until at least one dedicated migration pass proves links are stable:

- `../current/status.md`
- `../architecture/v0.2-roadmap.md`
- `../archive/docs-inventory-pre-reorg.md`
- `docs-migration-plan.md`
- `docs-migration-phase-1-dry-run.md`
- `v0.2-cycle-closure-review.md`
- `post-v0.2-tag-delta.md`
- `../architecture/external-ingestion-boundary-v0.2.md`
- `../architecture/approval-pause-resume-boundary-v0.2.md`
- `../architecture/artifact-content-read-policy-v0.2.md`
- `../architecture/http-api-minimal-surface-v0.2.md`

Reason: README, AGENTS, current-status, roadmap, and recent task instructions link to these paths directly. Phase 1 closure keeps these paths stable for external review and the post-review Agent / worker lifecycle follow-up.

## 6. Migration Table

| Current path | Proposed path | Category | Move now? | Link risk | Notes |
| --- | --- | --- | --- | --- | --- |
| `../current/README.md` | `docs/kernel/README.md` | kernel entrypoint | No | High | Current-truth reading order; old path needs stub. |
| `../architecture/action-type-registry-v0.1.md` | `docs/kernel/action-type-registry-v0.1.md` | kernel | No | Medium | Move with kernel docs. |
| `../architecture/approval-pause-resume-boundary-v0.2.md` | `docs/tracks/approval-pause-resume-boundary-v0.2.md` | track | No | High | Recently active Track E doc; keep until track links are stable. |
| `../architecture/artifact-content-read-policy-v0.2.md` | `docs/tracks/artifact-content-read-policy-v0.2.md` | track | No | High | Recently active Track C doc; keep until track links are stable. |
| `../architecture/checkpoint-history-fallback-v0.1.md` | `docs/checkpoint/checkpoint-history-fallback-v0.1.md` | checkpoint | No | Medium | Move with checkpoint batch. |
| `../architecture/checkpoint-history-index-retention-v0.1.md` | `docs/checkpoint/checkpoint-history-index-retention-v0.1.md` | checkpoint | No | Medium | Move with checkpoint batch. |
| `../architecture/checkpoint-history-save-boundary-v0.1.md` | `docs/checkpoint/checkpoint-history-save-boundary-v0.1.md` | checkpoint | No | Medium | Move with checkpoint batch. |
| `checkpoint-history-save-integration-v0.1.md` | `docs/checkpoint/checkpoint-history-save-integration-v0.1.md` | checkpoint | No | Medium | Move with checkpoint batch. |
| `../architecture/checkpoint-integrity-v0.1.md` | `docs/checkpoint/checkpoint-integrity-v0.1.md` | checkpoint | No | Medium | Move with checkpoint batch. |
| `../architecture/checkpoint-migration-versioning-v0.1.md` | `docs/checkpoint/checkpoint-migration-versioning-v0.1.md` | checkpoint | No | Medium | Move with checkpoint batch. |
| `../architecture/checkpoint-ownership-v0.1.md` | `docs/checkpoint/checkpoint-ownership-v0.1.md` | checkpoint | No | High | Referenced by current checkpoint/status docs; needs stub. |
| `../architecture/checkpoint-retention-compaction-v0.1.md` | `docs/checkpoint/checkpoint-retention-compaction-v0.1.md` | checkpoint | No | Medium | Move with checkpoint batch. |
| `../architecture/checkpoint-save-trigger-v0.1.md` | `docs/checkpoint/checkpoint-save-trigger-v0.1.md` | checkpoint | No | Medium | Move with checkpoint batch. |
| `../architecture/checkpoint-schema-version-fields-v0.1.md` | `docs/checkpoint/checkpoint-schema-version-fields-v0.1.md` | checkpoint | No | Medium | Move with checkpoint batch. |
| `../architecture/checkpoint-v0.1-scope-freeze.md` | `docs/checkpoint/checkpoint-v0.1-scope-freeze.md` | checkpoint | No | Medium | Move with checkpoint batch. |
| `../architecture/coding-plan-v0.1.md` | `../archive/plans/coding-plan-v0.1.md` | archive | Done | Low | Historical plan; moved to archived plans after active links checked. |
| `../architecture/commitment-levels.md` | `docs/kernel/commitment-levels.md` | kernel | No | Medium | Current reference; move with kernel batch. |
| `../current/status.md` | `../current/status.md` first; later `docs/status/current-status.md` | status entrypoint | No | High | Placement reviewed in `status-docs-placement-review.md`; keep as current-truth entrypoint. |
| `deferred-boundary-review-v0.1.md` | `docs/tracks/deferred-boundary-review-v0.1.md` | track/status | No | High | Current deferred-surface reference; move with track docs. |
| `../architecture/demo-architecture-v0.1.md` | `../features/demo/demo-architecture-v0.1.md` | demo | Done | Low | Phase 1b completed; old path stub removed in Phase 1d. |
| `../features/demo-entrypoint-v0.1.md` | `../features/demo/demo-entrypoint-v0.1.md` | demo | Done | Low | Phase 1b completed; old path stub removed in Phase 1d. |
| `../features/demo-walkthrough-v0.1.md` | `../features/demo/demo-walkthrough-v0.1.md` | demo | Done | Low | Phase 1b completed; old path stub removed in Phase 1d. |
| `../archive/docs-inventory-pre-reorg.md` | `../archive/docs-inventory-pre-reorg.md` first; later `docs/status/docs-inventory.md` | status entrypoint | No | High | Placement reviewed in `status-docs-placement-review.md`; keep as archive migration baseline. |
| `docs-migration-phase-1-dry-run.md` | `docs/status/docs-migration-phase-1-dry-run.md` later | status entrypoint | No | Medium | Placement reviewed in `status-docs-placement-review.md`; keep beside migration plan. |
| `docs-migration-plan.md` | `docs-migration-plan.md` first; later `docs/status/docs-migration-plan.md` | status entrypoint | No | High | Placement reviewed in `status-docs-placement-review.md`; keep as migration control doc. |
| `../architecture/event-envelope-schema-registry-v0.1.md` | `docs/kernel/event-envelope-schema-registry-v0.1.md` | kernel | No | Medium | Move with event docs. |
| `../architecture/event-envelope-versioning-v0.1.md` | `docs/kernel/event-envelope-versioning-v0.1.md` | kernel | No | Medium | Move with event docs. |
| `../architecture/event-prefix-digest-v0.1.md` | `docs/kernel/event-prefix-digest-v0.1.md` | kernel/checkpoint | No | Medium | Could go under kernel; referenced by checkpoint docs. |
| `../architecture/external-ingestion-boundary-v0.2.md` | `docs/tracks/external-ingestion-boundary-v0.2.md` | track | No | High | Recently active Track F doc; keep until external review links settle. |
| `../architecture/http-api-minimal-surface-v0.2.md` | `docs/tracks/http-api-minimal-surface-v0.2.md` | track | No | High | README / AGENTS link directly. |
| `../architecture/implementation-plan-v0.1.md` | `../archive/plans/implementation-plan-v0.1.md` | archive | Done | Low | Historical plan; moved to archived plans after active links checked. |
| `../architecture/kernel-architecture-v0.1.md` | `docs/kernel/kernel-architecture-v0.1.md` | kernel | No | High | Current reference; many docs mention it. |
| `../archive/kernel-decision-log.md` | `docs/kernel/kernel-decision-log.md` | kernel | No | Medium | Placement reviewed in `kernel-archive-placement-review.md`; keep in archive until full kernel batch. |
| `../architecture/kernel-living-spec.md` | `docs/kernel/kernel-living-spec.md` | kernel | No | High | Current reference; keep stubs if moved. |
| `../archive/kernel-one-pager.md` | `docs/kernel/kernel-one-pager.md` | kernel | No | Medium | Placement reviewed in `kernel-archive-placement-review.md`; keep in archive until full kernel batch. |
| `../architecture/kernel-spec-v0.1.md` | `docs/kernel/kernel-spec-v0.1.md` | kernel | No | High | Current reference; many docs mention it. |
| `../architecture/memory-record-persistence-boundary-v0.1.md` | `docs/memory/memory-record-persistence-boundary-v0.1.md` | memory | No | Medium | Move with memory batch. |
| `../architecture/memory-v0.1-scope-freeze.md` | `docs/memory/memory-v0.1-scope-freeze.md` | memory | No | High | Current memory scope reference. |
| `../architecture/memory-write-query-boundary-v0.1.md` | `docs/memory/memory-write-query-boundary-v0.1.md` | memory | No | Medium | Move with memory batch. |
| `post-v0.2-tag-delta.md` | `docs/status/post-v0.2-tag-delta.md` | status | No | High | Placement reviewed in `status-docs-placement-review.md`; keep in reviews until full status batch. |
| `../features/release-draft-v0.1-demo.md` | `../archive/release/release-draft-v0.1-demo.md` | release | Done | Low | Phase 1a completed; old path stub removed in Phase 1d. |
| `../architecture/server-checkpoint-boundary-v0.1.md` | `docs/checkpoint/server-checkpoint-boundary-v0.1.md` | checkpoint | No | Medium | Move with checkpoint batch. |
| `../features/v0.1-demo-acceptance.md` | `../features/demo/v0.1-demo-acceptance.md` | demo | Done | Low | Phase 1c completed; old path stub removed in Phase 1d. |
| `v0.2-cycle-closure-review.md` | `docs/status/v0.2-cycle-closure-review.md` | status | No | High | Placement reviewed in `status-docs-placement-review.md`; keep in reviews until full status batch. |
| `../features/v0.2-demo-acceptance.md` | `../features/demo/v0.2-demo-acceptance.md` | demo/status | Done | Low | Phase 1c completed; old path stub removed in Phase 1d. |
| `../features/v0.2-demo-readiness.md` | `../features/demo/v0.2-demo-readiness.md` | demo/status | Done | Low | Phase 1c completed; old path stub removed in Phase 1d. |
| `../features/v0.2-demo-scenario.md` | `../features/demo/v0.2-demo-scenario.md` | demo | Done | Low | Phase 1c completed; old path stub removed in Phase 1d. |
| `v0.2-mid-cycle-review.md` | `docs/status/v0.2-mid-cycle-review.md` | status | No | Medium | Placement reviewed in `status-docs-placement-review.md`; keep in reviews until full status batch. |
| `v0.2-next-track-selection.md` | `docs/status/v0.2-next-track-selection.md` | status | No | Medium | Placement reviewed in `status-docs-placement-review.md`; keep in reviews until full status batch. |
| `../architecture/v0.2-roadmap.md` | `../architecture/v0.2-roadmap.md` first; later `docs/status/v0.2-roadmap.md` | status entrypoint | No | High | Placement reviewed in `status-docs-placement-review.md`; keep stable roadmap entrypoint. |

## 7. Link Update Checklist

When a future migration actually moves files, update links in:

- `README.md`
- `AGENTS.md`
- `../current/status.md`
- `../architecture/v0.2-roadmap.md`
- `../archive/docs-inventory-pre-reorg.md`
- `docs-migration-plan.md`
- all moved files that link to sibling docs
- compatibility stub files left at old paths, if any remain for that migration wave

Minimum link checks:

```bash
rg -n "docs/(current-status|v0.2-roadmap|http-api|minimal|artifact-content|approval|external-ingestion|checkpoint|memory|demo|release)" README.md AGENTS.md docs
rg -n "\]\(docs/" README.md AGENTS.md docs
rg -n "\]\((?!https?://)[^)]+\.md\)" README.md AGENTS.md docs
```

## 8. Verification Commands

Run after each migration wave:

```bash
find docs -maxdepth 3 -type f -name "*.md" | sort

PYTHONPATH=src .venv/bin/python -m pytest tests/isotope -q

PYTHONPATH=src .venv/bin/python -m isotope.demo
PYTHONPATH=src .venv/bin/python -m isotope.demo --json
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario v0.2
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario v0.2 --json

rg -n '(^|\s)(from|import) x_agent\b' src/isotope tests/isotope || true

git -C /home/lumber/Github/x-agent status --short \
  src/x_agent src/isotope tests/isotope docs/isotope

git diff -- src tests .github pyproject.toml

git status --short
```

## 9. Rollback Plan

If any migration wave breaks links, tests, demo commands, or repo boundaries:

1. Stop immediately.
2. Do not continue moving more files.
3. Revert the migration commit with a normal revert.
4. Re-run the full verification commands.
5. Reopen the migration plan and reduce the next wave size.

Do not repair a broken migration by moving more files in the same patch unless the fix is a direct link/stub correction for files already moved in that patch.
