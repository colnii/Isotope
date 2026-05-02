# Docs Migration Phase 1 Dry Run

状态：`dry-run completed; Phase 1 closed / paused`

## 1. Purpose

本文基于 `docs/docs-migration-plan.md` 对第一阶段 docs directory migration 做 dry-run。目标是先识别低风险迁移候选、现有引用风险、stub 需求、执行命令和 rollback 规则。

Dry-run 本身没有移动、不重命名、不删除、不合并任何文件，不批量改链接，不修改 `src/`、`tests/`、`.github/` 或 `pyproject.toml`。

Follow-up status: Phase 1a release draft migration 已执行。Full release draft now lives at `docs/release/release-draft-v0.1-demo.md`; old path `docs/release-draft-v0.1-demo.md` remains as a compatibility stub.

Follow-up status: Phase 1b v0.1 demo explainer migration 已执行。Full explainer docs now live at `docs/demo/demo-entrypoint-v0.1.md`, `docs/demo/demo-walkthrough-v0.1.md`, and `docs/demo/demo-architecture-v0.1.md`; old paths remain as compatibility stubs.

Follow-up status: Phase 1c demo acceptance / readiness / scenario migration 已执行。Full docs now live at `docs/demo/v0.1-demo-acceptance.md`, `docs/demo/v0.2-demo-readiness.md`, `docs/demo/v0.2-demo-scenario.md`, and `docs/demo/v0.2-demo-acceptance.md`; old paths remain as compatibility stubs.

Closure status: Phase 1 is now closed / paused. Do not continue into track, checkpoint, memory, kernel, current-status, or roadmap migrations unless explicitly requested. The next default workstream can be Kernel Gap Review.

## 2. Phase 1 Scope

Phase 1 应只迁移低风险或已关闭的文档。不要在第一批移动稳定入口或近期仍被频繁引用的 active status docs。

暂不移动：

- `docs/current-status.md`
- `docs/v0.2-roadmap.md`
- `docs/docs-inventory.md`
- `docs/docs-migration-plan.md`
- `docs/v0.2-cycle-closure-review.md`
- `docs/post-v0.2-tag-delta.md`
- README / AGENTS 直接引用最多的入口文档

推荐第一批实际迁移候选：

- Release draft: `docs/release-draft-v0.1-demo.md` -> `docs/release/` completed in Phase 1a
- Demo docs: walkthrough / architecture / entrypoint -> `docs/demo/` completed in Phase 1b; acceptance / readiness / scenario -> `docs/demo/` completed in Phase 1c.
- Closed track docs: Track A / C / E -> `docs/tracks/` remains deferred after Phase 1 closure.

Track F 文档暂不列入实际第一批迁移。它刚完成 closure，且 `main` ahead of `v0.2-demo` 的增量说明仍依赖该路径。

## 3. Candidate Reference Map

| Candidate file | Proposed path | Current references | Link risk | Stub needed? |
| --- | --- | --- | --- | --- |
| `docs/release-draft-v0.1-demo.md` | `docs/release/release-draft-v0.1-demo.md` | `docs/current-status.md`, `docs/demo/v0.1-demo-acceptance.md`, `docs/v0.2-roadmap.md`, `docs/deferred-boundary-review-v0.1.md`, `docs/docs-inventory.md` | Low after Phase 1a | Stub exists. |
| `docs/demo-entrypoint-v0.1.md` | `docs/demo/demo-entrypoint-v0.1.md` | `docs/current-status.md`, `docs/memory-v0.1-scope-freeze.md`, `docs/deferred-boundary-review-v0.1.md`, `docs/docs-inventory.md` | Low after Phase 1b | Stub exists. |
| `docs/demo-walkthrough-v0.1.md` | `docs/demo/demo-walkthrough-v0.1.md` | `README.md`, `AGENTS.md`, `docs/current-status.md`, `docs/demo/v0.1-demo-acceptance.md`, `docs/v0.2-roadmap.md`, `docs/docs-inventory.md` | Low after Phase 1b | Stub exists. |
| `docs/demo-architecture-v0.1.md` | `docs/demo/demo-architecture-v0.1.md` | `README.md`, `AGENTS.md`, `docs/current-status.md`, `docs/demo/v0.1-demo-acceptance.md`, `docs/demo/demo-walkthrough-v0.1.md`, `docs/v0.2-roadmap.md`, `docs/docs-inventory.md` | Low after Phase 1b | Stub exists. |
| `docs/v0.1-demo-acceptance.md` | `docs/demo/v0.1-demo-acceptance.md` | `README.md`, `AGENTS.md`, `docs/current-status.md`, `docs/demo/demo-entrypoint-v0.1.md`, `docs/v0.2-roadmap.md`, `docs/docs-inventory.md` | Low after Phase 1c | Stub exists. |
| `docs/v0.2-demo-acceptance.md` | `docs/demo/v0.2-demo-acceptance.md` | `README.md`, `AGENTS.md`, `docs/current-status.md`, `docs/v0.2-roadmap.md`, `docs/demo/v0.2-demo-readiness.md`, `docs/docs-inventory.md` | Low after Phase 1c | Stub exists. |
| `docs/v0.2-demo-readiness.md` | `docs/demo/v0.2-demo-readiness.md` | `README.md`, `AGENTS.md`, `docs/current-status.md`, `docs/v0.2-roadmap.md`, `docs/demo/v0.2-demo-scenario.md`, `docs/docs-inventory.md` | Low after Phase 1c | Stub exists. |
| `docs/v0.2-demo-scenario.md` | `docs/demo/v0.2-demo-scenario.md` | `README.md`, `AGENTS.md`, `docs/current-status.md`, `docs/v0.2-roadmap.md`, `docs/demo/v0.2-demo-readiness.md`, `docs/docs-inventory.md` | Low after Phase 1c | Stub exists. |
| `docs/http-api-minimal-surface-v0.2.md` | `docs/tracks/http-api-minimal-surface-v0.2.md` | `README.md`, `AGENTS.md`, `docs/current-status.md`, `docs/v0.2-roadmap.md`, `docs/docs-inventory.md` | High | Yes. |
| `docs/artifact-content-read-policy-v0.2.md` | `docs/tracks/artifact-content-read-policy-v0.2.md` | `README.md`, `AGENTS.md`, `docs/current-status.md`, `docs/v0.2-roadmap.md`, `docs/deferred-boundary-review-v0.1.md`, `docs/docs-inventory.md` | High | Yes. |
| `docs/approval-pause-resume-boundary-v0.2.md` | `docs/tracks/approval-pause-resume-boundary-v0.2.md` | `README.md`, `AGENTS.md`, `docs/current-status.md`, `docs/v0.2-roadmap.md`, `docs/deferred-boundary-review-v0.1.md`, `docs/docs-inventory.md` | High | Yes. |

## 4. Dry-Run Decision

Phase 1a / 1b / 1c 已执行。Phase 1 当前 closed / paused，不再默认继续迁移剩余候选。已执行顺序：

1. Phase 1a: completed; release draft 已迁移到 `docs/release/`，旧路径留 stub。
2. Phase 1b: completed; v0.1 demo explainer docs 已迁移到 `docs/demo/`，旧路径留 stub。
3. Phase 1c: completed; demo acceptance / readiness / scenario docs 已迁移到 `docs/demo/`，旧路径留 stub。
4. Stop here for Phase 1 closure. Track / checkpoint / memory / kernel / status-entrypoint migrations stay deferred unless explicitly requested.

原因：

- Release draft 不是当前 quick-start 入口，单独迁移风险最低。
- Demo docs 被 README / AGENTS 直接引用，应该单独做一批，便于 review。
- Closed track docs 链接密度高；虽然语义已经 stable，但 Phase 1 closure 选择暂不继续迁移，避免 cleanup 阶段继续扩大链接 churn。

## 5. Execution Checklist For Future Migration

Phase 1a / 1b / 1c 已执行。以下命令保留为后续迁移批次的 checklist 模板；不要重复执行已经完成的 `git mv`，除非是在回放迁移步骤。

```bash
mkdir -p docs/release docs/demo docs/tracks

git mv docs/release-draft-v0.1-demo.md docs/release/release-draft-v0.1-demo.md

# If using stubs, recreate the old path with a short pointer.
# Example:
# docs/release-draft-v0.1-demo.md -> "Moved to docs/release/release-draft-v0.1-demo.md"

rg -n '\[[^]]+\]\([^)]+\.md[^)]*\)' README.md AGENTS.md docs
rg -n 'release-draft-v0.1-demo|demo-walkthrough|demo-architecture|v0.2-demo-scenario|http-api-minimal|artifact-content|approval-pause' README.md AGENTS.md docs

PYTHONPATH=src .venv/bin/python -m pytest tests/isotope_kernel -q
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --json
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario v0.2
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario v0.2 --json

rg -n '(^|\s)(from|import) x_agent\b' src/isotope_kernel tests/isotope_kernel || true
git -C /home/lumber/Github/x-agent status --short \
  src/x_agent src/isotope_kernel tests/isotope_kernel docs/isotope
git diff -- src tests .github pyproject.toml
git status --short
```

## 6. Link Update Rules

Any actual migration commit must update links in the same commit:

- `README.md`
- `AGENTS.md`
- `docs/current-status.md`
- `docs/v0.2-roadmap.md`
- `docs/docs-inventory.md`
- `docs/docs-migration-plan.md`
- moved docs that link to sibling docs
- compatibility stubs at old paths

Do not move files first and leave link cleanup for a later commit.

## 7. Stub Rules

Use stubs for any moved file that is linked from README, AGENTS, current-status, roadmap, or external review docs.

Stub format:

```md
# Moved

This document moved to `docs/<target>/<file>.md`.
```

Stubs should be short and should not duplicate the moved document content. Remove stubs only after one stable cycle and a dedicated link audit.

## 8. Rollback Plan

If a migration batch is committed and then breaks links, tests, demo commands, or repo boundaries:

1. Stop further migration.
2. Revert the migration commit with `git revert <commit>`.
3. Re-run the full verification commands.
4. Split the migration into a smaller batch.

If the migration is not committed yet, prefer restoring the specific moved files and edited links. Do not use broad destructive cleanup without inspecting `git status --short`.

## 9. Recommendation

Phase 1 closure 后，下一步默认不继续 migration；可以转入 Kernel Gap Review。

如果用户明确要求继续 migration，建议迁移 closed Track A / C / E docs 到 `docs/tracks/` 并为每个旧路径保留 stub。不要和 checkpoint / memory / kernel docs 迁移合并。

Dry-run 本身没有移动、删除、重命名或合并任何文档；Phase 1a 后续单独迁移了 release draft，并保留旧路径 stub；Phase 1b 后续单独迁移了 v0.1 demo explainer docs，并保留旧路径 stubs。
