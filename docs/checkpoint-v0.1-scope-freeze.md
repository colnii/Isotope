# Checkpoint v0.1 Scope Freeze

状态：frozen for current kernel slice

本文冻结 checkpoint v0.1（检查点 v0.1）的当前实现范围。后续 agent 不应因为 checkpoint docs 里还列有 history index、retention、GC 等 deferred 项，就继续沿 checkpoint 线无限深挖。

## Current Decision

Checkpoint v0.1 is functionally sufficient for the current kernel slice.

当前 checkpoint 能力已经足够支撑 Isotope kernel slice 的 recovery / rebuild / inspection acceleration（恢复、重建、检查加速）。checkpoint 仍只是 derived object（派生对象），不是第二事实源。

当前实现基线：

- latest implementation commit：`146a811cd862ab42defb3e1b81198617344b8719`。
- full regression：`391 passed`。

除非后续出现明确的 storage growth、performance 或 operational need，并先落新的 design patch 和 red tests，否则暂不继续实现 checkpoint history index、retention policy、checkpoint GC、automatic scheduling 或 public checkpoint API。

## Implemented

当前 checkpoint 线已实现：

- latest checkpoint save：`RunProjector.save_checkpoint(...)` + `FileCheckpointStore.save_checkpoint(...)`。
- history checkpoint save：`RunProjector.save_checkpoint_history(...)` + `FileCheckpointStore.save_checkpoint_history(...)`。
- projector-owned checkpoint creation：`RunProjector.create_checkpoint(...)` 只从 canonical events 和 projected `RunState` 生成 checkpoint。
- checkpoint-assisted rebuild：`RunProjector.rebuild_with_checkpoint(...)`。
- old-checkpoint fallback：`load_checkpoint_candidates(...)` + projector-owned candidate validation chain。
- integrity/hash validation：checkpoint `integrity` 使用 `sha256` 和 deterministic JSON。
- event prefix digest：checkpoint 绑定到 run 内 event-log prefix representation。
- event envelope version binding：event prefix digest metadata 记录当前 event envelope version。
- server read path checkpoint-assisted rebuild：`InProcessServer.get_run_state(...)` 可选调用 projector-owned rebuild boundary。
- internal latest save trigger：`InProcessServer.save_checkpoint_for_run(...)`。
- internal explicit history save trigger：`InProcessServer.save_checkpoint_history_for_run(...)`。
- latest-only storage hardening：`save_checkpoint(...)` 仍只替换 `latest.json`。
- checkpoint state schema validation、prefix consistency validation、projector version boundary validation。

核心边界保持不变：

- canonical event log 仍是唯一 source of truth。
- checkpoint 只加速 recovery / rebuild / inspection。
- checkpoint 不修复、不覆盖、不裁剪 canonical event log。
- `FileCheckpointStore` 仍是 opaque storage，不解释 checkpoint business state。
- `InProcessServer` 不能直接读取、解释或返回 checkpoint `state`；server 只能调用 projector-owned boundary。

## Explicitly Deferred

以下 checkpoint 能力仍然 deferred，并且在当前 v0.1 freeze 下不继续推进：

- checkpoint history index。
- retention policy。
- checkpoint GC。
- automatic checkpoint scheduling。
- public checkpoint API / HTTP endpoint。
- `CheckpointService`。
- event log compaction。
- checkpoint retention / compaction implementation。
- checkpoint inspection API。
- checkpoint migration / version negotiation implementation。
- schema / migrator registry。

这些 deferred 项不是当前下一步建议。它们只有在真实 storage growth、performance 或 operational need 出现时，才应被显式 reopened。

## Why Freeze Here

继续实现 checkpoint history index / retention / GC 的边际收益已经下降：

- 当前 checkpoint 已能覆盖 latest save、history save、assisted rebuild、candidate fallback、hash、event prefix digest 和 server internal triggers。
- checkpoint 线的核心 correctness boundary 已经被验证：即使使用 checkpoint，也不能跳过 canonical event validation、lifecycle validation、state schema validation 或 prefix consistency validation。
- 更深的 retention / GC / index work 主要是 operational storage management，不是当前 kernel correctness 的阻塞项。
- 当前更有价值的是推进下一个 kernel surface，避免 checkpoint 线吸走后续实现注意力。

后续只有在实际出现 checkpoint 文件增长、rebuild 性能瓶颈、部署运维需求或明确产品需求时，才重新打开 checkpoint retention / GC / index 设计。

## Next Kernel Surfaces

后续优先级建议从 checkpoint 线转向其他 kernel surface：

1. `ActionTypeRegistry` minimal boundary。
2. memory write/query boundary。
3. external ingestion / `ImportedSnapshot` boundary。

推荐下一轮先做 `ActionTypeRegistry` minimal boundary docs / red tests。不要直接进入 real LLM、memory write implementation 或 external ingestion implementation；这些仍需要先落 design/doc patch 和 red tests。
