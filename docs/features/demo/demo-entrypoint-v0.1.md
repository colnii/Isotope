# Demo Entrypoint v0.1

状态：`implemented`

Acceptance：`accepted as developer demo`，详见 `v0.1-demo-acceptance.md`。

## 1. Purpose

本文定义 v0.1 demo 的最小展示路径：用一个本地可运行命令展示 Isotope core 的核心闭环，而不是展示完整产品。

demo entrypoint 的目标是给开发者和 reviewer 一个稳定的 smoke path：不需要 real LLM、不需要 HTTP server、不需要外部 provider，也不需要真实 durable memory storage。它只展示当前 core slice 已经具备的 deterministic contract。

当前测试基线：`568 passed`。

当前实现：

- `src/isotope/demo.py`
- `tests/isotope/test_demo_entrypoint.py`
- `tests/isotope/test_packaging_smoke.py`
- `tests/isotope/test_ci_workflow.py`
- `.github/workflows/ci.yml`
- `python -m isotope.demo`
- `python -m isotope.demo --json`

当前验收证据：

- local tests: `568 passed`
- demo plain text: success
- demo JSON: success
- editable install smoke: covered
- GitHub Actions CI: passed by web UI confirmation
- no `x_agent.*` imports
- `/home/lumber/Github/x-agent` untouched

## 2. Demo Goal

一个命令跑通：

```text
create session -> create run -> submit input -> deterministic supervisor -> action compiler -> policy -> executor -> artifact -> canonical events -> projector -> checkpoint -> replay verification -> printed summary
```

其中：

- deterministic supervisor 只产生当前 slice 支持的 compact intent。
- action path 必须经过 `ActionCompiler`、`PolicyEngine` 和 `Executor`。
- state summary 必须来自 `RunProjector` rebuild。
- checkpoint verification 必须使用 projector-owned checkpoint creation / rebuild boundary。

## 3. What The Demo Should Prove

demo 应证明：

- compact intent 必须编译成 canonical `ActionProposal`。
- execution 必须使用 `PolicyDecision.grants`。
- artifact 必须有 execution provenance。
- `RunState` 来自 projector。
- event log 可 replay。
- checkpoint-assisted rebuild 可恢复等价 read model。
- memory boundary 存在，但不会展示成真实 memory storage / query。

demo 不应证明：

- real LLM integration 已可用。
- memory storage / query engine 已可用。
- HTTP / public API 已可用。
- plugin system 已可用。

## 4. Proposed Command

先做 module entrypoint，不引入 CLI framework：

```bash
PYTHONPATH=src .venv/bin/python -m isotope.demo
```

可选 JSON 输出：

```bash
PYTHONPATH=src .venv/bin/python -m isotope.demo --json
```

标准 editable install 路径也已通过 smoke：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[test]"
.venv/bin/python -m isotope.demo
.venv/bin/python -m isotope.demo --json
```

后续如果需要稳定 CLI，再单独设计 `python -m isotope.cli demo` 或 console script。本轮不引入。

## 5. Implemented Files

当前实现涉及：

- `src/isotope/demo.py`
- `tests/isotope/test_demo_entrypoint.py`
- `tests/isotope/test_packaging_smoke.py`

不应修改：

- memory storage / query implementation。
- external ingestion implementation。
- real HTTP server。
- plugin loading。

## 6. Demo Storage

默认使用临时目录，不污染 repo：

- event log: temp dir
- artifact store: temp dir
- checkpoint store: temp dir

plain text 输出可以打印 temp dir path，方便开发者检查生成物。

tests 不应依赖固定路径，也不应要求 temp dir 留存。demo 不得在 repo 根目录写入 `runs/`、`artifacts/`、`checkpoints/` 或其他持久目录。

## 7. Minimal Demo Output

plain text 输出至少包含：

- session id
- run id
- final run status
- action outcome
- artifact ref
- artifact summary
- event count
- replay status
- checkpoint status
- memory boundary status: `boundary_only`

JSON 输出至少包含：

- `session_id`
- `run_id`
- `run_status`
- `artifact_ref`
- `artifact_summary`
- `event_count`
- `replay_ok`
- `checkpoint_ok`
- `memory_status`

JSON 输出不得包含 full artifact content、memory full content、raw provider response 或 external snapshot payload。

## 8. Non-Goals

- real LLM
- HTTP server
- UI
- real durable memory storage
- real memory query
- external ingestion
- plugin system
- multi-user auth
- production release packaging

## 9. Implemented Tests

`tests/isotope/test_demo_entrypoint.py` 已落地并通过，覆盖：

- `python -m isotope.demo` 能运行成功。
- plain text 输出包含 run status / artifact ref / replay ok / checkpoint ok。
- `--json` 输出可解析。
- JSON 输出不包含 full artifact content。
- demo 使用 temp dir，不在 repo 根目录写 `runs/` 或 `artifacts/`。
- demo 不 import `x_agent.*`。
- demo 不调用 real LLM / network。
- demo memory status 明确是 `boundary_only`。
- replay / checkpoint 验证来自真实 event log / checkpoint-assisted rebuild，不是 hardcoded true。

`tests/isotope/test_packaging_smoke.py` 已落地并通过，覆盖：

- `pyproject.toml` exists and carries minimum project metadata。
- pytest test dependency / optional dependency group exists。
- src-layout package discovery covers `src/isotope`。
- editable install 后可以 import `isotope`。
- editable install 后可以运行 installed `python -m isotope.demo`。
- editable install 后可以运行 installed `python -m isotope.demo --json`。
- installed demo JSON 包含 run / artifact / replay / checkpoint / memory summary。
- installed demo 不在 repo 根目录写 `runs/` / `artifacts/` / `checkpoints/`。
- installed package source 不 import `x_agent.*`。

`tests/unit/test_ci_workflow.py` 已落地并通过，覆盖：

- `.github/workflows/ci.yml` exists。
- workflow 在 `push` / `pull_request` 时触发。
- workflow 使用带 `isotope-ci` 标签的 Linux x64 self-hosted runner 和 Python `3.13`。
- workflow 用 concurrency 取消同一 ref 上被新 push 取代的旧 run。
- workflow 执行 editable install with test extra：`python -m pip install -e ".[test]"`。
- workflow 运行 `python -m pytest tests/ -q`。
- workflow 运行 demo plain / JSON smoke。
- workflow 不需要 secrets，不引用本地绝对路径，不引用 `x-agent` / `x_agent`。
- workflow 不引入 release、coverage、lint matrix 或 real integration services。
- `.github/workflows/ci-cloud.yml` 仅允许 `workflow_dispatch` 手动触发，作为
  GitHub-hosted runner 的省额度备用 smoke。
- latest remote GitHub Actions run 已由网页确认通过。

该 demo 仍是 developer demo，不是产品 CLI。后续扩展必须继续保持 no real LLM / no network / no repo-root side effects / summary-only output 边界。
