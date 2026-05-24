# Web Research Design

状态：`implementation in progress`

日期：2026-05-24

## 1. Purpose

第一版 web research 目标不是做普通搜索框，也不是直接接一堆搜索 API。

目标是打开一个 platform/kernel 级 research substrate（研究底座）：外部网页或
Codex delegated research（委托调研）结果必须先变成带 provenance（来源溯源）
的 artifact / imported observation，再通过 retrieval（受控检索）被用户、Agent
或后续 memory promotion（记忆晋升）复用。

第一版采用 `B + C` 薄切片：

- `B`: Codex Supervisor 作为第一版 delegated research provider。
- `C`: 结果进入 artifact / provenance / retrieval 边界，而不是只停留在一次性回答。
- 保留方便手测的搜索入口，先不依赖 UI。

## 2. Reuse Audit

现有可复用模块和边界：

- `src/isotope/features/search/flow.py`
  - 已有本地低敏 `SearchFlow`，支持 project / task / file 摘要搜索。
  - 可作为后续“找回 research summary / source refs”的入口参考。
- `src/isotope/features/supervisor/`
  - 已有 Codex Supervisor、worker 管理、状态投影和 CLI 入口。
  - 第一版 delegated research 应复用 Supervisor 的任务/证据语义，而不是另开后台系统。
- `src/isotope/runtime/in_process.py`
  - 已有 in-process server、artifact store 和 retrieval service wiring。
- `src/isotope/rag/retrieval.py`
  - 已有 summary / full content 的 controlled retrieval 边界。
- `src/isotope/platform/schemas/snapshots.py`
  - 已有 `ImportedSnapshot`，适合表达外部观察，但它不是最终 web research protocol。
- `docs/architecture/external-ingestion-boundary-v0.2.md`
  - 已规定外部输入不能直接更新 `RunState` / `SessionState`，只能进入 canonical event、
    accepted imported observation 或 artifact/provenance-only。
- `docs/architecture/memory-write-query-boundary-v0.1.md`
  - 已规定 memory query 不能绕过 retrieval / grants，memory 不是 transcript dump。

暂不复用或不直接扩展的部分：

- 不把现有 `SearchFlow` 改造成联网搜索。它现在是本地低敏摘要搜索。
- 不直接开启 external ingestion HTTP API。第一版走内部 flow / CLI。
- 不实现 durable memory storage 或 automatic memory write。web research 只产生
  memory candidate basis（候选依据）。
- 不把 Codex report 当成 canonical truth。它只是 external observation / source-backed
  artifact。

## 3. Product Shape

第一版支持三个入口形态，但只实现一个共享底座：

1. 用户手动搜索 / 调研：
   - 通过 CLI 输入 query。
   - 输出 JSON，包含 sources、report、evidence status 和 artifact refs。
2. Agent / Supervisor 调用：
   - Supervisor 可把 research query 委托给 Codex provider。
   - 结果挂到当前 run / task 的 evidence。
3. Platform/kernel 沉淀：
   - research result 进入 artifact / provenance。
   - 后续 retrieval 可以找回 summary / source refs。
   - memory promotion 只读取带 source refs 的 candidate，不从裸报告直接写 memory。

第一版不做完整 Web UI，但 CLI 输出必须足够好读、可复制、可回归测试。

## 4. Core Data Model Candidate

第一版内部使用 `WebResearchRun` 候选模型。字段名仍是 v0 candidate，不是稳定协议。

```python
{
    "research_id": "research_001",
    "query": "agent memory retrieval design",
    "provider": "codex_delegated",
    "created_at": "2026-05-24T00:00:00Z",
    "status": "ok",
    "evidence_status": "complete",
    "sources": [
        {
            "source_id": "src_001",
            "title": "...",
            "url": "https://example.com/page",
            "snippet": "...",
            "why_used": "explains retrieval boundary",
            "retrieved_at": "2026-05-24T00:00:00Z",
            "provider_rank": 1
        }
    ],
    "report": {
        "summary": "...",
        "claims": [
            {
                "text": "...",
                "source_ids": ["src_001"],
                "confidence": "medium"
            }
        ],
        "limitations": ["..."],
        "next_queries": ["..."]
    },
    "artifact_refs": [
        {"ref_type": "artifact", "run_id": "run_001", "artifact_id": "artifact_001"}
    ],
    "provenance": {
        "provider": "codex_delegated",
        "supervisor_task_id": "task_001",
        "raw_transcript_artifact_ref": {
            "ref_type": "artifact",
            "run_id": "run_001",
            "artifact_id": "artifact_raw"
        }
    }
}
```

Hard rules:

- `sources[]` 是必需字段。
- `report.claims[].source_ids` 必须引用已有 source。
- 没有可核查 sources 时，`evidence_status` 必须是 `incomplete_evidence`。
- `report` 可以为空或降级，但 sources 不能被 report 替代。
- 保存 artifact 时必须保留 query、provider、created_at、sources 和 report summary。
- raw Codex transcript 可以保存为 artifact，但不能直接作为 memory record。

## 5. Provider Boundary

第一版 provider：

- `CodexDelegatedResearchProvider`
  - 输入：query、scope、budget hints、source requirements。
  - 输出：结构化 `WebResearchRun` payload。
  - 失败：返回 controlled error 或 `incomplete_evidence`，不能伪造成功。

Provider prompt 要求 Codex 返回 JSON：

- `sources`: URL / title / snippet / why_used。
- `report`: summary / claims / limitations / next_queries。
- `evidence_notes`: 哪些信息缺来源、哪些来源可能过期。

后续 provider 预留：

- Tavily：普通 search API provider。
- SearXNG：可选 self-hosted / fallback provider，不依赖公共实例作为核心路径。
- Local browser / crawler：最低层 URL fetch / extract fallback，不负责大规模搜索。
- OpenAI / ChatGPT Deep Research：高级 research provider，因预算和屏幕监控条件暂不打开。
- Codex-as-delegated-provider：当前优先路径，但仍按外部观察处理。

## 6. Flow

### 6.1 Manual CLI Flow

```text
user query
  -> ResearchFlow.search(...)
  -> CodexDelegatedResearchProvider.run(...)
  -> validate WebResearchRun
  -> save raw/provider result artifact
  -> save normalized summary artifact
  -> return JSON response
```

建议测试入口：

```bash
PYTHONPATH=src .venv/bin/python -m isotope.features.research.runner search \
  --query "agent memory retrieval design" \
  --json
```

后续可在 Supervisor CLI 增加：

```bash
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner research \
  --query "agent memory retrieval design" \
  --json
```

如果只能先做一个入口，优先做 `features.research.runner`，Supervisor CLI 作为薄代理。

### 6.2 Agent / Supervisor Flow

```text
agent needs external evidence
  -> proposes research action
  -> policy checks budget / provider / scope
  -> Supervisor launches Codex delegated research
  -> ResearchFlow validates and stores artifacts
  -> result refs return to agent context
```

第一版可以先不做完整 model-invoked tool。可以从 manual / Supervisor command 入口验证
provider 和 artifact 边界，再把它接入 agent loop。

### 6.3 Retrieval / Memory Flow

```text
research artifact
  -> summary retrieval returns query / report summary / source refs
  -> controlled expand can read full normalized result if granted
  -> memory promotion candidate uses only source-backed claims
```

Memory promotion 第一版只标记 candidate，不自动写 `MemoryRecord`。

## 7. Error Handling

受控状态：

- `ok`: sources 和 report 都通过最小校验。
- `partial`: sources 存在，但 report 缺失、引用不完整或部分来源弱。
- `incomplete_evidence`: 没有 URL / title / snippet 等可核查 sources。
- `provider_failed`: Codex task 失败或没有返回可解析结构。
- `validation_failed`: 返回结构存在，但字段非法或 claim 引用不存在的 source。
- `not_enabled`: provider 或 artifact persistence 未启用。

错误响应必须包含：

- stable code
- human-readable message
- retryable flag
- low-sensitive details

失败不能留下看起来成功的 research summary。provider 没有返回可解析结果时，
只保存 `research.provider_trace` 调用轨迹；`research.report` 只用于通过校验的
normalized research result。

## 8. Testing Strategy

第一批测试先不用真实 Codex 网络调用，使用 fake provider：

- `ResearchFlow` 接收 fake provider 返回完整 sources + report，保存 normalized artifact。
- 缺 sources 时返回 `incomplete_evidence`，不能进入 memory candidate。
- claim 引用不存在的 source 时返回 `validation_failed`。
- raw transcript artifact 和 normalized summary artifact 都带 provenance。
- CLI `search --json` 输出 machine-readable payload。
- retrieval 至少能找回 research summary / source refs 的低敏视图。

真实 Codex provider 可作为 smoke / manual test，不作为默认 pytest 依赖。

## 9. First Implementation Slice

第一版实现范围：

1. 新增 `src/isotope/features/research/`。
2. 新增 `ResearchFlow`、`ResearchResult` / `WebResearchRun` validation helper。
3. 新增 fake provider 用于测试。
4. 新增 Codex delegated provider contract，但真实调用可以先 behind not-enabled / manual path。
5. 新增 CLI runner：`research search --query ... --json`。
6. 保存 normalized research artifact，并带 provenance。
7. 提供 summary / source refs 低敏输出。

Implementation plan:
`docs/superpowers/plans/2026-05-24-web-research-implementation-plan.md`.

明确不做：

- Tavily / SearXNG provider。
- OpenAI / ChatGPT Deep Research provider。
- 自动浏览器操作。
- 自动 memory write。
- Web UI。
- 公共 HTTP ingestion API。
- 把 research result 投影成 native `RunState` fact。

## 10. Acceptance Criteria

第一版完成后应能证明：

- 一个 query 可以通过方便的 CLI 入口发起。
- 返回结构同时包含 sources 列表和带引用 report。
- evidence 不完整时系统会降级，而不是假装成功。
- research result 被保存为 artifact/provenance。
- 后续 retrieval / search 能看到低敏 summary 和 source refs。
- memory 仍保持 ref-first / provenance-aware，不直接吞网页全文。

## 11. Resolved Decisions

用户已确认第一版按以下决策进入 implementation plan：

1. 第一版保留 fake provider 测试，同时真实入口应尝试自动启动 Codex session。
   fake provider 证明 validation / artifact / retrieval substrate；真实入口证明
   Codex Supervisor delegated research 的可用性。
2. artifact type 使用：
   - normalized result: `research.report`
   - raw Codex output / transcript: `research.raw_transcript`
   - provider failure trace: `research.provider_trace`
   这样不把能力锁死成只支持 web API，后续 Tavily / SearXNG / Deep Research
   也可以复用 research 命名。
3. CLI 第一批保留两个入口：
   - `isotope.features.research.runner search`: 底层功能入口，开发和测试优先。
   - `isotope.features.supervisor.runner research`: Supervisor 薄代理入口，贴近日常使用。
   底层逻辑必须在 `ResearchFlow`，Supervisor CLI 不能另写一套 research 流程。
