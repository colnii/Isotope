# Isotope Kernel Current Truth（当前真相）

这个目录用来临时冻结当前 `Isotope v0` 内核（kernel）方向，避免设计继续推进后，口头版本和书面版本再一次漂移。

如果目标是快速找到文档、判断哪些是 current truth、哪些只是 concept / archive / stub，先读 [Current Docs Map（当前文档地图）](./current-docs-map.md)。

如果目标是理解 kernel current truth，建议按这个顺序阅读：

1. [Kernel One-Pager（一页说明）](./kernel-one-pager.md)
2. [Commitment Levels（承诺强度分层）](./commitment-levels.md)
3. [Kernel Spec v0.1（规格草案）](./kernel-spec-v0.1.md)
4. [Kernel Architecture v0.1（架构草案）](./kernel-architecture-v0.1.md)
5. [Implementation Plan v0.1（实现计划草案）](./implementation-plan-v0.1.md)
6. [Coding Plan v0.1（编码计划草案）](./coding-plan-v0.1.md)
7. [Kernel Decision Log（决策日志）](./kernel-decision-log.md)
8. [Kernel Living Spec（动态规格草案）](./kernel-living-spec.md)
9. [Concept Docs（长线概念与应用方向）](./concepts/README.md)
10. [Public / Internal Docs Boundary（公开 / 内部文档边界）](./public-internal-docs-boundary.md)

这组文档的目的不是追求完美，而是先把下面三件事固定下来：

- 保留一份轻量但明确的当前事实来源
- 把标准说法、关键决策、演进中的 contract 分开
- 明确这一轮 fork 已经和旧的 `x-agent` recipe-oriented（配方式）讨论分叉到哪里

当前状态：

- `kernel-one-pager.md` 是最适合先读的入口
- `commitment-levels.md` 用来区分 hard contract、v0 candidate、example/schema sketch 和 open question
- `kernel-spec-v0.1.md` 是当前主线收口后的连续规格草案
- `kernel-architecture-v0.1.md` 说明 spec contracts 当前由哪些 runtime modules 承担
- `implementation-plan-v0.1.md` 定义第一条最小 vertical slice 和验收标准
- `coding-plan-v0.1.md` 把第一条 slice 拆成目录、接口、测试和实现任务
- `kernel-decision-log.md` 记录已经做出的关键选择，以及为什么这样选
- `kernel-living-spec.md` 不是最终 spec，但它是当前最接近设计真相的 contract 草案

当前已经同步进主线的新增进展：

- `Session` 是 continuity boundary，`Run` 是 execution boundary，执行状态归 run
- `HTTP JSON + SSE` 是 v0 server API candidate，run 可以脱离在线 client 继续或恢复
- `RunState` / `SessionState` 只能由 canonical event log 投影出来
- 外部 raw log / provider response / callback 原文必须先经过 ingestion，不能直接更新状态
- `ImportedSnapshot` 是被 canonical event 接纳过的外部观察，不是第二个事实源，也不是 checkpoint
- `MemoryRecord` 需要结构化 `content`，不能只有标题、标签和来源索引
- `Memory Query` 是 on-demand recall primitive，并支持受 policy 约束的 `query + controlled expand`；它可以是 runtime-invoked capability，不必等同于模型主动调用的 tool
- `GenericAgent` / `PetGPT` / `Hermes Agent` / study companion 都作为 pressure test 使用，不作为 kernel 模板照搬
- `docs/concepts/` 保存从早期 Isotope 讨论迁入的长线概念和应用层设想；它们可以反压 kernel requirement，但不是当前实现队列本身
- `public-internal-docs-boundary.md` 只定义未来公开文档 profile 的分类边界；当前不删除、不移动、不隐藏任何文档

术语约定：

- 文档以中文主叙述为主
- 关键英文术语会保留，并在首次出现时尽量补中文解释
- URI-like 这类写法只作为展示/调试记法，不是正式协议
