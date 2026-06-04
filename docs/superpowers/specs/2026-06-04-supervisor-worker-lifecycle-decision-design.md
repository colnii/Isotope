# Supervisor Worker Lifecycle Decision Design

## 背景

当前 Supervisor 已经有几块可复用能力：

- `worker-review` 读取 managed Codex worker 的 `SUPERVISOR_STATUS`、日志、worktree 和变更摘要。
- `integration-review` 把 done worker 分成 `ready_to_integrate`、`conflict_risk`、`needs_review`、`already_integrated` 等组。
- `merge_dispatch` 能从 integration review 生成受控 merge worker 的 launch spec。
- `auto_cleanup` 能在已合入后归档 managed record，并在安全条件满足时清理 worktree。

问题是这些能力目前像散落的零件。Supervisor loop 仍然需要把大量固定流程塞进 prompt，依赖模型判断“是否继续、是否合并、是否清理”。第一刀目标是把确定性流程收进程序，让模型只处理真正需要判断的异常和产品取舍。

## 目标

新增一个程序化 lifecycle decision 层，先处理固定流程：

```text
done worker
  -> worker-review
  -> integration-review
  -> dispatch merge worker when ready_to_integrate exists
  -> archive integrated source/merge workers when already_integrated is proven
  -> hand off conflict, needs_review, blocked, needs_user to model or user
```

成功标准：

- Supervisor loop 在问模型前，先能产出一个明确的 lifecycle decision。
- 对确定流程，程序能给出可执行动作或跳过原因。
- 对不确定流程，程序只返回 `needs_human` / `model_required`，不静默自动修。
- 现有 `worker-review`、`integration-review`、`merge_dispatch`、`auto_cleanup` 继续作为 source of truth，不重造分类逻辑。
- prompt 可以逐步瘦身：worker 只需要汇报状态和证据，固定 merge/cleanup SOP 迁到程序层。

## 非目标

- 不做完整 workflow engine。
- 不自动解决 git conflict。
- 不自动 rerun CI。
- 不自动删除 active worktree。
- 不把所有 Supervisor action 都迁到这个层。
- 不改变 worker 真实写代码、测试、提交的职责。

## 方案比较

### 方案 A：继续靠 prompt

把更多规则写进 worker prompt，让 worker 自己按 SOP 执行。

优点是改动小。缺点是 Supervisor 负担不降，失败模式仍然靠自然语言约定，测试也只能测 prompt 文本。

### 方案 B：新增小型 lifecycle decision 层

新增纯函数模块，输入 worker/integration/cleanup 上下文，输出下一步确定动作。执行层复用现有 `merge_dispatch` 和 `auto_cleanup`。

优点是边界小、可测试、能复用现有模块，能逐步替换 prompt 里的固定流程。缺点是第一版还不是完整状态机。

### 方案 C：一次性引入 workflow engine

把 worker、merge、CI、cleanup 全部建成状态机和持久化事件流。

优点是长期形态最完整。缺点是第一刀过大，容易重写现有模块，也容易把未稳定的产品判断固化过早。

推荐方案 B。

## 设计

新增模块建议命名为：

```text
src/isotope/features/supervisor/lifecycle/decision.py
```

它只做决策，不直接执行副作用。

核心输入：

```python
{
    "worker_reviews": dict | None,
    "integration_review": dict | None,
    "merge_dispatch": dict | None,
    "cleanup_candidates": list[dict],
}
```

核心输出：

```python
{
    "kind": "worker_lifecycle_decision",
    "action": "monitor"
        | "dispatch_merge"
        | "archive_integrated"
        | "cleanup_worktree"
        | "needs_human"
        | "model_required",
    "reason": str,
    "source": "worker_review" | "integration_review" | "cleanup",
    "summary": dict,
    "execution": dict | None,
}
```

第一版 action 语义：

- `monitor`：没有 ready/done 证据，继续观察。
- `dispatch_merge`：存在 `ready_to_integrate`，且没有 merge worker 正在跑。
- `archive_integrated`：integration review 已证明 source/merge worker 已合入，可调用已有 archive 逻辑。
- `cleanup_worktree`：已有归档结果且现有 cleanup safety 允许清理。
- `needs_human`：存在 conflict、blocked、needs_user、权限问题或安全检查失败。
- `model_required`：程序不能确定下一步，交回 LLM action。

## 接入点

第一阶段只把 decision 写进 payload，不改变行为：

- 在 `append_supervise_planning_payload(...)` 收集或接收现有 review payload。
- 调用 `build_worker_lifecycle_decision(...)`。
- 把结果写入 `payload["worker_lifecycle_decision"]`。
- plain/json 输出能看到程序建议，但不会自动执行。

第二阶段开启确定动作执行：

- `dispatch_merge` 复用现有 `merge_dispatch["launch_spec"]` 和 `_execute_launch_action(...)`。
- `archive_integrated` 复用 `auto_archive_integrated_merge_workers(...)`。
- `cleanup_worktree` 继续走现有 `_delete_worktree_candidate_payloads(...)` 和 safety gates。
- `needs_human` / `model_required` 保持原有 LLM action 路线。

## 数据流

```text
supervise / loop
  -> collect worker review
  -> collect integration review
  -> build merge dispatch payload
  -> build worker lifecycle decision
  -> if decision is deterministic and execution flag enabled:
       execute existing action helper
     else:
       expose decision and continue current LLM path
```

这保持一个原则：classification 在 review 模块，execution 在现有 action helper，decision 层只负责选择。

## 错误处理

- review payload 缺失：返回 `monitor` 或 `model_required`，不抛硬错误。
- ready worker 存在但 merge worker 已在跑：返回 `monitor`，reason 写明 `merge worker already running`。
- conflict/needs_review 不自动处理：返回 `needs_human`。
- cleanup safety 不满足：返回 `needs_human`，reason 写明具体 safety reason。
- 执行阶段失败：记录 executed payload 的失败信息，不吞异常证据。

## 测试

新增 focused unit tests：

- done worker ready_to_integrate -> `dispatch_merge`
- ready_to_integrate 但 merge worker already running -> `monitor`
- already_integrated -> `archive_integrated`
- conflict_risk / needs_review -> `needs_human`
- empty review -> `monitor`

新增或扩展 integration tests：

- supervisor loop json payload 包含 `worker_lifecycle_decision`
- merge dispatch 仍复用现有 launch spec
- archive integrated 仍走现有 cleanup safety

回归测试继续跑：

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/features/supervisor/test_supervisor_merge_work_order.py \
  tests/integration/supervisor/test_supervisor_merge_dispatch_loop.py \
  tests/integration/supervisor/test_supervisor_auto_loop_e2e.py -q
```

## 分阶段落地

1. 新增纯决策模块和单元测试，只返回 payload。
2. 在 supervise planning payload 暴露决策，不改变执行。
3. 对 `dispatch_merge` 接入执行路径，保持现有 feature flag / execute flag 约束。
4. 对 `archive_integrated` 接入执行路径，复用现有安全检查。
5. 瘦身 work order prompt，把已经由程序托管的 merge/cleanup 细节移出 prompt。

## 风险

- 如果 review payload 语义漂移，decision 层可能误判。缓解方式是只读现有 summary/groups，并用测试固定关键 group 名。
- 如果过早自动 cleanup，可能误删活跃 worktree。缓解方式是第一版只复用现有 cleanup safety，不新增删除条件。
- 如果执行层和 LLM action 同时触发，可能重复启动 merge worker。缓解方式是先检查 running merge worker，并把 lifecycle decision 放在 LLM action 前作为单一入口。
