# Docs Migration Phase 1 Dry Run

状态：`dry-run completed; Phase 1 closed / paused`

## 1. Purpose

本文基于 `docs-migration-plan.md` 对第一阶段 docs directory migration 做 dry-run。目标是先识别低风险迁移候选、现有引用风险、stub 需求、执行命令和 rollback 规则。

Dry-run 本身没有移动、不重命名、不删除、不合并任何文件，不批量改链接，不修改 `src/`、`tests/`、`.github/` 或 `pyproject.toml`。

Follow-up status: Phase 1a release draft migration 已执行。Full release draft now lives at `../archive/release/release-draft-v0.1-demo.md`; old path `../features/release-draft-v0.1-demo.md` was later removed in Phase 1d.

Follow-up status: Phase 1b v0.1 demo explainer migration 已执行。Full explainer docs now live at `../features/demo/demo-entrypoint-v0.1.md`, `../features/demo/demo-walkthrough-v0.1.md`, and `../features/demo/demo-architecture-v0.1.md`; old paths were later removed in Phase 1d.

Follow-up status: Phase 1c demo acceptance / readiness / scenario migration 已执行。Full docs now live at `../features/demo/v0.1-demo-acceptance.md`, `../features/demo/v0.2-demo-readiness.md`, `../features/demo/v0.2-demo-scenario.md`, and `../features/demo/v0.2-demo-acceptance.md`; old paths were later removed in Phase 1d.

Follow-up status: Phase 1d low-risk stub cleanup 已执行。Demo、release draft 和 event schema compatibility 的旧路径 stubs 已删除，当前链接应直接指向真实文档路径。

Closure status: Phase 1 is now closed / paused. Do not continue into track, checkpoint, memory, kernel, current-status, or roadmap migrations unless explicitly requested. Kernel Gap Review has landed in `kernel-gap-review-v0.2.md`; Agent / Worker lifecycle boundary has landed in `../architecture/agent-worker-lifecycle-boundary-v0.2.md`; the next default workstream is the corresponding red tests or Workspace substrate boundary design.

## 2. Phase 1 Scope

Phase 1 应只迁移低风险或已关闭的文档。不要在第一批移动稳定入口或近期仍被频繁引用的 active status docs。

暂不移动：

- `../current/status.md`
- `../architecture/v0.2-roadmap.md`
- `../archive/docs-inventory-pre-reorg.md`
- `docs-migration-plan.md`
- `v0.2-cycle-closure-review.md`
- `post-v0.2-tag-delta.md`
- README / AGENTS 直接引用最多的入口文档

推荐第一批实际迁移候选：

- Release draft: `../features/release-draft-v0.1-demo.md` -> `docs/release/` completed in Phase 1a
- Demo docs: walkthrough / architecture / entrypoint -> `docs/demo/` completed in Phase 1b; acceptance / readiness / scenario -> `docs/demo/` completed in Phase 1c.
- Closed track docs: Track A / C / E -> `docs/tracks/` remains deferred after Phase 1 closure.

Track F 文档暂不列入实际第一批迁移。它刚完成 closure，且 `main` ahead of `v0.2-demo` 的增量说明仍依赖该路径。

## 3. Candidate Reference Map

| Candidate file | Proposed path | Current references | Link risk | Stub needed? |
| --- | --- | --- | --- | --- |
| `../features/release-draft-v0.1-demo.md` | `../archive/release/release-draft-v0.1-demo.md` | `../current/status.md`, `../features/demo/v0.1-demo-acceptance.md`, `../architecture/v0.2-roadmap.md`, `deferred-boundary-review-v0.1.md`, `../archive/docs-inventory-pre-reorg.md` | Low after Phase 1a | Stub removed in Phase 1d. |
| `../features/demo-entrypoint-v0.1.md` | `../features/demo/demo-entrypoint-v0.1.md` | `../current/status.md`, `../architecture/memory-v0.1-scope-freeze.md`, `deferred-boundary-review-v0.1.md`, `../archive/docs-inventory-pre-reorg.md` | Low after Phase 1b | Stub removed in Phase 1d. |
| `../features/demo-walkthrough-v0.1.md` | `../features/demo/demo-walkthrough-v0.1.md` | `README.md`, `AGENTS.md`, `../current/status.md`, `../features/demo/v0.1-demo-acceptance.md`, `../architecture/v0.2-roadmap.md`, `../archive/docs-inventory-pre-reorg.md` | Low after Phase 1b | Stub removed in Phase 1d. |
| `../architecture/demo-architecture-v0.1.md` | `../features/demo/demo-architecture-v0.1.md` | `README.md`, `AGENTS.md`, `../current/status.md`, `../features/demo/v0.1-demo-acceptance.md`, `../features/demo/demo-walkthrough-v0.1.md`, `../architecture/v0.2-roadmap.md`, `../archive/docs-inventory-pre-reorg.md` | Low after Phase 1b | Stub removed in Phase 1d. |
| `../features/v0.1-demo-acceptance.md` | `../features/demo/v0.1-demo-acceptance.md` | `README.md`, `AGENTS.md`, `../current/status.md`, `../features/demo/demo-entrypoint-v0.1.md`, `../architecture/v0.2-roadmap.md`, `../archive/docs-inventory-pre-reorg.md` | Low after Phase 1c | Stub removed in Phase 1d. |
| `../features/v0.2-demo-acceptance.md` | `../features/demo/v0.2-demo-acceptance.md` | `README.md`, `AGENTS.md`, `../current/status.md`, `../architecture/v0.2-roadmap.md`, `../features/demo/v0.2-demo-readiness.md`, `../archive/docs-inventory-pre-reorg.md` | Low after Phase 1c | Stub removed in Phase 1d. |
| `../features/v0.2-demo-readiness.md` | `../features/demo/v0.2-demo-readiness.md` | `README.md`, `AGENTS.md`, `../current/status.md`, `../architecture/v0.2-roadmap.md`, `../features/demo/v0.2-demo-scenario.md`, `../archive/docs-inventory-pre-reorg.md` | Low after Phase 1c | Stub removed in Phase 1d. |
| `../features/v0.2-demo-scenario.md` | `../features/demo/v0.2-demo-scenario.md` | `README.md`, `AGENTS.md`, `../current/status.md`, `../architecture/v0.2-roadmap.md`, `../features/demo/v0.2-demo-readiness.md`, `../archive/docs-inventory-pre-reorg.md` | Low after Phase 1c | Stub removed in Phase 1d. |
| `../architecture/http-api-minimal-surface-v0.2.md` | `docs/tracks/http-api-minimal-surface-v0.2.md` | `README.md`, `AGENTS.md`, `../current/status.md`, `../architecture/v0.2-roadmap.md`, `../archive/docs-inventory-pre-reorg.md` | High | Yes. |
| `../architecture/artifact-content-read-policy-v0.2.md` | `docs/tracks/artifact-content-read-policy-v0.2.md` | `README.md`, `AGENTS.md`, `../current/status.md`, `../architecture/v0.2-roadmap.md`, `deferred-boundary-review-v0.1.md`, `../archive/docs-inventory-pre-reorg.md` | High | Yes. |
| `../architecture/approval-pause-resume-boundary-v0.2.md` | `docs/tracks/approval-pause-resume-boundary-v0.2.md` | `README.md`, `AGENTS.md`, `../current/status.md`, `../architecture/v0.2-roadmap.md`, `deferred-boundary-review-v0.1.md`, `../archive/docs-inventory-pre-reorg.md` | High | Yes. |

## 4. Dry-Run Decision

Phase 1a / 1b / 1c 已执行。Phase 1 当前 closed / paused，不再默认继续迁移剩余候选。已执行顺序：

1. Phase 1a: completed; release draft 已迁移到 `docs/release/`。
2. Phase 1b: completed; v0.1 demo explainer docs 已迁移到 `docs/demo/`。
3. Phase 1c: completed; demo acceptance / readiness / scenario docs 已迁移到 `docs/demo/`。
4. Phase 1d: completed; 低风险旧路径 stubs 已删除。
5. Stop here for Phase 1 closure. Track / checkpoint / memory / kernel / status-entrypoint migrations stay deferred unless explicitly requested.

原因：

- Release draft 不是当前 quick-start 入口，单独迁移风险最低。
- Demo docs 被 README / AGENTS 直接引用，应该单独做一批，便于 review。
- Closed track docs 链接密度高；虽然语义已经 stable，但 Phase 1 closure 选择暂不继续迁移，避免 cleanup 阶段继续扩大链接 churn。

## 5. Execution Checklist For Future Migration

Phase 1a / 1b / 1c 已执行。以下命令保留为后续迁移批次的 checklist 模板；不要重复执行已经完成的 `git mv`，除非是在回放迁移步骤。

```bash
mkdir -p docs/release docs/demo docs/tracks

git mv ../features/release-draft-v0.1-demo.md ../archive/release/release-draft-v0.1-demo.md

# If using stubs, recreate the old path with a short pointer.
# Example:
# ../features/release-draft-v0.1-demo.md -> "Moved to ../archive/release/release-draft-v0.1-demo.md"

rg -n '\[[^]]+\]\([^)]+\.md[^)]*\)' README.md AGENTS.md docs
rg -n 'release-draft-v0.1-demo|demo-walkthrough|demo-architecture|v0.2-demo-scenario|http-api-minimal|artifact-content|approval-pause' README.md AGENTS.md docs

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

## 6. Link Update Rules

Any actual migration commit must update links in the same commit:

- `README.md`
- `AGENTS.md`
- `../current/status.md`
- `../architecture/v0.2-roadmap.md`
- `../archive/docs-inventory-pre-reorg.md`
- `docs-migration-plan.md`
- moved docs that link to sibling docs
- compatibility stubs at old paths, if the migration wave still needs them

Do not move files first and leave link cleanup for a later commit.

## 7. Stub Rules

Use stubs for any moved file that is linked from README, AGENTS, current-status, roadmap, or external review docs.

Stub format:

```md
# Moved

This document moved to `docs/<target>/<file>.md`.
```

Stubs should be short and should not duplicate the moved document content. The first low-risk stub deletion batch has now run after a dedicated link audit.

## 8. Rollback Plan

If a migration batch is committed and then breaks links, tests, demo commands, or repo boundaries:

1. Stop further migration.
2. Revert the migration commit with `git revert <commit>`.
3. Re-run the full verification commands.
4. Split the migration into a smaller batch.

If the migration is not committed yet, prefer restoring the specific moved files and edited links. Do not use broad destructive cleanup without inspecting `git status --short`.

## 9. Recommendation

Phase 1 closure 后，下一步默认不继续 migration；Kernel Gap Review 和 Agent / Worker lifecycle boundary 已落地，后续默认转入对应 red tests 或 Workspace substrate boundary design。

如果用户明确要求继续 migration，建议迁移 closed Track A / C / E docs 到 `docs/tracks/` 并为每个旧路径保留 stub。不要和 checkpoint / memory / kernel docs 迁移合并。

Dry-run 本身没有移动、删除、重命名或合并任何文档；Phase 1a 后续单独迁移了 release draft，Phase 1b 后续单独迁移了 v0.1 demo explainer docs，Phase 1d 后续删除了低风险旧路径 stubs。
