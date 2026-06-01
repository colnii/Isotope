# Capability Hub Core Merge Readiness Review

状态：`ready to merge`

## 1. 结论

`feature/capability-hub-core` 可以合回 `main`。

本分支只把 aggressive Capability Hub 的“能力目录骨架”抽进 mainline：

- `Capability` metadata model。
- `CapabilityCatalog`。
- shelf visibility。
- low-sensitive manifest。
- readiness status。
- 三个 product-candidate built-ins：`artifact.review`、`external.snapshot.review`、`approval.tool.runner`。

它没有把 aggressive branch 的大模块或应用层实验整体带进来。

## 2. Review 结果

确认没有进入本轮禁止范围：

- 没有复制 aggressive `capability_hub.py`。
- 没有引入 49 个 aggressive capabilities。
- 没有 capability execution。
- 没有 LLM route / ask / interactive。
- 没有 DeepSeek provider。
- 没有 diagnostics / pressure-test capabilities 默认暴露。
- 没有 self-evolution harness。
- 没有 workflow engine / product shell / UI / QQ bot。
- 没有新增依赖。

## 3. Rebase 结果

本分支已 rebase 到当前 `origin/main`，吸收了 agent-loop / planner validated runner branch-local work。

rebase 冲突只出现在 docs/status 文件：

- `README.md`
- `AGENTS.md`
- `../current/status.md`
- `../current/agent-task-queue.md`

解决方式：

- 保留最新 `origin/main` 的 agent-loop / planner 内容。
- 重新补入 Capability Hub Core first slice 的 closure 状态。
- 不覆盖 mainline 刚新增的 planner / agent-loop 文档。

## 4. Verification

已验证：

- targeted capability catalog tests：`19 passed`
- full regression：`1115 passed`
- `v0.2 --trace` demo：pass
- `agent-loop-planner-validated-runner --trace` demo：pass
- `x_agent.*` import check：no output
- `/home/lumber/Github/x-agent` scoped status check：no output
- `.github` / `pyproject.toml` diff：no output

## 5. Merge 注意事项

合并后仍应保持以下边界：

- Capability Hub Core 是 catalog，不是 runner。
- `get_capability_status(...)` 只做本地 metadata / env readiness，不构造 provider，不联网。
- 后续 capability execution、LLM routing、ask、interactive、diagnostics shelf 默认暴露、product shell 都必须单独开 boundary 和 red tests。

推荐 merge 方式：

- fast-forward 或 rebase 后合并。
- 不创建 merge commit。
- 不移动 tag。
- 不发布 GitHub Release。
