# Public / Internal Docs Boundary

状态：`classification boundary`

## 1. Purpose

本文定义 Isotope 文档的 public / internal / concept / archive 边界，为未来 open source（开源）或外部展示准备一个 public docs profile（公开文档配置）判断框架。

本轮不移动、不删除、不合并任何文档，也不决定现在开源。当前目标只是让读者和后续 agent 知道哪些文档可以外部阅读，哪些只是开发过程、AI 协作、早期概念或历史记录。

## 2. Current Docs Classification

| Class | Meaning | Current examples | Public release stance |
| --- | --- | --- | --- |
| `public-ready` | 可以直接给外部读者看，语气和内容接近公开项目说明。 | `README.md`, `docs/demo/`, `docs/release/`, `../reviews/external-review-package-v0.2.md`, `../reviews/post-external-review-checkpoint.md` | 可默认包含，但 release 前仍要检查 stale status / tag wording。 |
| `reviewer-facing` | 适合给技术 reviewer 看，包含实现边界、已证明能力、deferred surfaces。 | `../current/status.md`, `../archive/kernel-mainline-maintenance-mode.md`, `../reviews/app-spike-coverage-review.md`, `../reviews/kernel-gap-review-refresh-v0.2.md`, closure reviews | 可公开，但需要说明它们是 design / review records，不是 product docs。 |
| `internal/dev-process` | 服务于开发流程、AI 协作、队列和批次推进。 | `AGENTS.md`, `../current/agent-task-queue.md`, detailed red/green/closure docs | 可留在 repo，但不应被包装成 public product narrative。 |
| `concept/application-pressure` | 长期概念、应用层设想、参考项目对照、study companion pressure。 | `docs/concepts/`, selected `kernel-living-spec.md` sections | 当前可留在主线，但未来公开前需要逐篇 audit。 |
| `historical/archive` | 记录当时决策和迁移过程，主要用于追溯。 | `docs/docs-migration-*`, older selection / roadmap / v0.1 plan docs, compatibility stubs | 可保留，但 public profile 可选择隐藏或放入 archive。 |

这些分类不是访问控制，也不是 license / legal policy。它们只是未来公开文档整理时的工程边界。

## 3. `docs/concepts/` Positioning

`docs/concepts/` 保存从早期 Isotope 讨论迁入的长期概念和应用层压力测试材料。

当前定位：

- 用于长期概念整理、reference-project comparison（参考项目对照）和 application-layer pressure（应用层压力）。
- 可以反过来产生 kernel requirements（内核需求），但不能直接覆盖 current implementation truth（当前实现事实）。
- 当前实现事实仍以 `../current/status.md`、`v0.2-roadmap.md`、`../current/agent-task-queue.md`、closure reviews 和 actual code / tests 为准。
- 不一定适合未来原样公开，因为其中可能包含早期试探性判断、AI collaboration process（AI 协作过程）和 private application orientation（私人应用方向）。

因此：不要删除 `docs/concepts/`，但也不要把它当作 public product docs 或 kernel contract。

## 4. Future Open Source Options

Option A: keep all docs in the public repo, with clear warnings.

- Pros: preserves full project history and design transparency.
- Cons: internal/dev-process and concept docs may confuse external readers.
- Good fit when the goal is research / prototype transparency.

Option B: create a public branch / export branch with only public docs.

- Pros: cleanest reader experience for open source.
- Cons: requires ongoing sync discipline between mainline and export profile.
- Good fit when the project needs a polished external repo view.

Option C: move internal docs to `docs/internal/` or a private repo.

- Pros: makes boundary visible in filesystem layout.
- Cons: requires link migration and may break historical reading paths if rushed.
- Good fit only after a dedicated docs migration pass.

Option D: release packaging exports only `README.md` plus selected public docs.

- Pros: lowest risk for public releases.
- Cons: less transparent; reviewers may lose context unless given a private bundle.
- Good fit for packaged demo / distribution artifacts.

## 5. Recommendation

Recommended current approach:

1. Do not delete, move, or rewrite existing docs now.
2. Keep the current mainline complete and reviewable.
3. Maintain this classification and entrypoint wording.
4. Before a real open source / public release decision, run a dedicated public-docs audit.
5. If a public profile is needed, prefer Option B or Option D over rewriting history.

This keeps the repo useful for current development while avoiding premature public-facing cleanup.

## 6. Do Not Do Now

- Do not rewrite git history to hide docs.
- Do not delete `docs/concepts/`.
- Do not move internal docs without a dedicated link-audited migration.
- Do not treat `../current/agent-task-queue.md` as public product documentation.
- Do not treat private application orientation as kernel contract.
- Do not decide that Isotope is open source / public-release ready solely from this classification.
- Do not create tags or GitHub Releases as part of docs classification.
