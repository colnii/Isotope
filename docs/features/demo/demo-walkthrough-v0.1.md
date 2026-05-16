# Demo Walkthrough v0.1

状态：`current`

## 1. What You Are Running

`python -m isotope.demo` 会跑一个 deterministic core loop（确定性核心闭环）。

它不是聊天机器人，不调用 LLM，不启动 HTTP server，也不连接外部服务。它只用本地临时目录跑通当前 Isotope core 的最小闭环：创建 session / run，生成一个确定性的 artifact-producing intent，通过 action chain 执行，写 canonical events，用 projector 得到 `RunState`，再验证 event replay 和 checkpoint-assisted rebuild。

这个 demo 的目的不是展示完整产品，而是让外部读者看到 core contract 已经能闭合。

如果想先看流程图，见 `demo-architecture-v0.1.md`。那份图只解释 v0.1 demo runtime path，不是完整 Isotope 架构图。

## 2. Quick Run

标准安装和运行路径：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[test]"
.venv/bin/python -m isotope.demo
.venv/bin/python -m isotope.demo --json
```

开发环境中也可以使用 `PYTHONPATH=src`：

```bash
PYTHONPATH=src .venv/bin/python -m isotope.demo
PYTHONPATH=src .venv/bin/python -m isotope.demo --json
```

v0.2 另有 explicit scenario，用来展示 Track A / C / E 的 in-process boundary，默认 v0.1 demo 仍保持兼容：

```bash
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario v0.2
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario v0.2 --json
```

v0.2 scenario 仍不启动 real HTTP server / network listener，不调用 real LLM，不实现 memory storage/query，也不打开 HTTP full-content route。

## 3. What Happens Internally

demo 按顺序执行：

1. 创建 session。
2. 创建 run。
3. deterministic supervisor 生成一个 artifact-producing intent。
4. `ActionCompiler` 编译成 canonical `ActionProposal`。
5. `PolicyEngine` 生成 `PolicyDecision`。
6. `Executor` 只使用 `PolicyDecision.grants` 执行。
7. `ArtifactStore` 保存 artifact summary / ref / provenance。
8. `EventStore` 写入 canonical events。
9. `RunProjector` 从 events 得到 `RunState`。
10. replay 从 event log 重建同等 `RunState`。
11. checkpoint-assisted rebuild 从 checkpoint + suffix events 恢复状态。
12. memory 显示为 `boundary_only`，表示当前只展示边界，不是真实 memory engine。

## 4. What The Output Means

plain text 输出和 JSON 输出表达同一组核心事实。

- `session_id`: demo 创建的 session id。
- `run_id`: demo 创建的 run id。
- `run_status`: projector 看到的最终 run 状态；当前 successful demo 应为 `completed`。
- `action_outcome`: executor action lifecycle 的最终 outcome；当前 successful demo 应为 `completed`。
- `artifact_ref`: structured `ResourceRef`，指向 artifact，而不是内联 artifact full content。
- `artifact_summary`: artifact 的短摘要；demo 不输出 full artifact content。
- `event_count`: 写入 event log 的 canonical event 数量。
- `replay_ok`: fresh replay 是否从 event log 得到等价 read model。
- `checkpoint_ok`: checkpoint-assisted rebuild 是否得到等价 read model。
- `memory_status`: 当前固定为 `boundary_only`，表示 memory 只展示 contract / read-model boundary，不表示 durable memory storage 或 query engine 已实现。

典型 plain text 输出会包含：

```text
run_status: completed
artifact_ref: {"artifact_id": "artifact_001", "ref_type": "artifact", "run_id": "run_001", "scope": "run"}
artifact_summary: hello artifact
event_count: 9
replay_ok: true
checkpoint_ok: true
memory_status: boundary_only
```

JSON 输出适合脚本或 CI smoke 检查，字段名与 plain text 一致。

## 5. What This Proves

这个 demo 证明：

- action chain 没被绕过。
- compact intent 先变成 canonical `ActionProposal`。
- policy 决策先发生，executor 后执行。
- executor 只使用 `PolicyDecision.grants`。
- artifact 有 execution provenance。
- state 来自 canonical events，而不是 executor / artifact store / memory store 直接写入。
- event replay 可重建 `RunState`。
- checkpoint 可辅助恢复 `RunState`。
- memory boundary 存在，但不是产品级 memory。

## 6. What This Does Not Prove

这个 demo 不证明：

- real LLM agent 已可用。
- real listening HTTP server / hosted API 已可用。
- UI 已可用。
- real memory storage / query 已可用。
- external ingestion 已可用。
- plugin system 已可用。
- production readiness 已达到。

## 7. Troubleshooting

### `No module named pytest`

通常是只安装了 package，没有安装 test extra。使用：

```bash
.venv/bin/python -m pip install -e ".[test]"
```

不要只运行 `pip install -e .` 后直接执行 tests。

### `No module named isotope`

说明当前 Python 环境还没有安装 repo，或没有设置 `PYTHONPATH=src`。

可选修复：

```bash
.venv/bin/python -m pip install -e ".[test]"
```

或在本地开发时：

```bash
PYTHONPATH=src .venv/bin/python -m isotope.demo
```

### CI 与本地差异

当前 GitHub Actions smoke 使用 Python `3.12`、`3.13` 和 `3.14`
matrix，并通过 test extra 安装依赖：

```bash
python -m pip install -U pip
python -m pip install -e ".[test]"
python -m pytest tests/isotope -q
python -m isotope.demo
python -m isotope.demo --json
```

如果本地和 CI 结果不同，先确认本地是否使用同一个 install path、同一个 repo commit，以及是否误用了其他虚拟环境。

### Demo 不应污染 repo 根目录

demo 使用临时目录，不应在 repo 根目录留下 `runs/`、`artifacts/` 或 `checkpoints/`。如果看到这些目录，先确认是不是其他手工命令或旧实验留下的文件，不要把它们当成 demo 产物。
