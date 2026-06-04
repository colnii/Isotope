# Desktop Chat Golden Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Desktop chat the primary product entrypoint where the model can inspect project state, complete small code changes, and launch Codex-assisted Isotope self-repair without fixed intent routing.

**Architecture:** Keep `stream_desktop_chat_events(...)` and `run_supervisor_conversation_events(...)` as the conversational path. Add capabilities and runtime helpers that the model may choose from the manifest, feed structured observations back to the model after each action, and render action progress in product language. Do not add a classifier, pipeline, or hard-coded intent-to-route branch.

**Tech Stack:** Python 3.13, pytest, Svelte 5, Vitest, existing `CapabilityRunner`, Supervisor state projections, managed Codex registry, desktop SSE stream.

---

## File Structure

- Modify `src/isotope/llm/prompts/supervisor_conversation_loop.md`: remove fixed intent-routing rules while keeping output schema, structured observations, and model agency.
- Modify `tests/unit/llm/test_system_prompt_assets.py`: add a regression that rejects prompt wording that maps user intent to a specific capability.
- Modify `src/isotope/capabilities/supervisor.py`: add `supervisor.project_status`, a project-state summary capability.
- Modify `src/isotope/capabilities/catalog.py`: register `supervisor.project_status` and `isotope.self_repair`.
- Modify `src/isotope/capabilities/runner.py`: route `supervisor.project_status` and `isotope.self_repair`.
- Create `src/isotope/features/supervisor/self_repair.py`: build a Codex self-repair work order and launch a managed Codex worker in an isolated worktree.
- Create `src/isotope/capabilities/self_repair.py`: validate `isotope.self_repair` inputs and call the Supervisor self-repair helper.
- Modify `src/isotope/features/supervisor/conversation_loop.py`: keep model-selected capability execution, pass safe defaults, and preserve structured observation feedback for project status and self-repair.
- Modify `tests/unit/features/supervisor/test_supervisor_conversation_loop.py`: cover project status, self-repair, no fixed routing, and Codex-assisted observations.
- Modify `tests/unit/capabilities/test_capability_runner_thin_shell.py`: cover catalog discovery, validation, project status output, and self-repair launch output.
- Modify `tests/integration/supervisor/test_supervisor_desktop_chat.py`: cover `/desktop/chat` stream for project status and Codex-assisted self-repair.
- Modify `apps/desktop/src/lib/view/capacityCallView.ts`: add product-language titles and summaries.
- Modify `apps/desktop/src/lib/view/capacityCallView.test.ts`: cover product-language rendering for project status, code change, Codex worker launch, and self-repair.
- Modify `apps/desktop/src/lib/components/main/CapacityCallCard.svelte`: replace visible `capacity` wording with action wording.
- Modify `apps/desktop/src/lib/components/main/CapacityCallDetails.svelte`: replace empty-detail copy with action wording.
- Modify `apps/desktop/src/lib/components/mini/MiniWindow.svelte`: remove visible `capacity` wording from mini chat copy.
- Modify `apps/desktop/src/lib/stores/appState.ts`: refresh the snapshot after a completed desktop chat turn.
- Modify `apps/desktop/src/lib/stores/appState.test.ts`: cover snapshot refresh after a successful action-bearing chat turn.

## Task 1: Remove Fixed Intent Routing From Conversation Prompt

**Files:**
- Modify: `src/isotope/llm/prompts/supervisor_conversation_loop.md`
- Modify: `tests/unit/llm/test_system_prompt_assets.py`

- [ ] **Step 1: Write the failing prompt-agency test**

Add this test to `tests/unit/llm/test_system_prompt_assets.py`:

```python
def test_supervisor_conversation_prompt_does_not_encode_fixed_intent_routes():
    prompt = load_prompt_template("supervisor_conversation_loop")

    forbidden = [
        "普通问候优先 direct_answer",
        "如果本轮已有 capacity_observation，优先基于 observation 输出 direct_answer",
        "已有 capacity_observation，优先基于 observation 输出 direct_answer",
        "明确要求访问、搜索或总结外部网页时，优先选择 `research.search`",
        "if project question",
        "if code request",
    ]
    for phrase in forbidden:
        assert phrase not in prompt

    assert "capacity_manifest" in prompt
    assert "capacity_observation" in prompt
    assert "call_capability" in prompt
    assert "report_capability_gap" in prompt
```

- [ ] **Step 2: Run the prompt test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/unit/llm/test_system_prompt_assets.py::test_supervisor_conversation_prompt_does_not_encode_fixed_intent_routes -q
```

Expected: FAIL because the current prompt contains fixed preference rules.

- [ ] **Step 3: Replace route rules with capability-and-boundary guidance**

Edit `src/isotope/llm/prompts/supervisor_conversation_loop.md` so the rules section says:

```markdown
边界：
- 根据用户目标、对话历史、capacity_manifest 和 capacity_observation 自主选择下一步；不要把用户意图映射成固定路线。
- 如果已有 observation 足够推进，继续完成用户目标；如果还不够，可以继续选择可用 capability。
- call_capability.arguments 只填 capability input_contract 允许的字段；系统会补 state_root/root/cwd/run_id 等已知上下文。
- report_capability_gap 只用于 Isotope 自身缺少能力、工具、上下文、skill/MCP 或执行边界时；不要用它替代继续调查。
- 不要输出 raw prompt、raw response、messages、secret、token、完整 transcript 或 artifact full content。
```

Keep `required_json_shape` unchanged so existing providers still return the same JSON envelope.

- [ ] **Step 4: Run the prompt test to verify it passes**

Run:

```bash
.venv/bin/python -m pytest tests/unit/llm/test_system_prompt_assets.py::test_supervisor_conversation_prompt_does_not_encode_fixed_intent_routes -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/isotope/llm/prompts/supervisor_conversation_loop.md tests/unit/llm/test_system_prompt_assets.py
git commit -m "fix(supervisor): keep desktop chat model agency"
```

## Task 2: Add Project-State Capability For Desktop Chat

**Files:**
- Modify: `src/isotope/capabilities/supervisor.py`
- Modify: `src/isotope/capabilities/catalog.py`
- Modify: `src/isotope/capabilities/runner.py`
- Modify: `tests/unit/capabilities/test_capability_runner_thin_shell.py`

- [ ] **Step 1: Write the failing discovery and output tests**

Add these tests to `tests/unit/capabilities/test_capability_runner_thin_shell.py`:

```python
def test_runner_discovers_supervisor_project_status_from_default_catalog():
    runner = _runner()

    ids = _ids(runner.list_capabilities())
    assert "supervisor.project_status" in ids
    description = runner.describe_capability("supervisor.project_status")

    assert description["input_contract"]["required"] == ["state_root"]
    assert description["input_contract"]["properties"]["state_root"]["type"] == "string"
    assert "project_state_summary" in description["output_contract"]["fields"]
    assert "read_only_state_projection" in description["safety_boundaries"]


def test_project_status_capability_returns_low_sensitive_snapshot_summary(tmp_path):
    runner = _runner()

    result = runner.run_capability(
        "supervisor.project_status",
        inputs={"state_root": str(tmp_path)},
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "supervisor.project_status"
    assert result["status"] == "completed"
    summary = result["project_state_summary"]
    assert summary["snapshot_id"]
    assert summary["counts"]["runningAgents"] == 0
    assert "raw" not in json.dumps(result, ensure_ascii=False).lower()
    assert "messages" not in json.dumps(result, ensure_ascii=False).lower()
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_discovers_supervisor_project_status_from_default_catalog tests/unit/capabilities/test_capability_runner_thin_shell.py::test_project_status_capability_returns_low_sensitive_snapshot_summary -q
```

Expected: FAIL because `supervisor.project_status` is not registered.

- [ ] **Step 3: Add the project status runner**

In `src/isotope/capabilities/supervisor.py`, add:

```python
SUPERVISOR_PROJECT_STATUS_CAPABILITY = "supervisor.project_status"
```

Include it in `is_supervisor_readonly_capability(...)`, then add:

```python
def run_supervisor_project_status(
    *, inputs: Mapping[str, Any] | None
) -> dict[str, Any]:
    inputs = normalize_supervisor_state_root_inputs(inputs)
    required_inputs = [SUPERVISOR_STATE_ROOT_INPUT]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    state_root = inputs.get(SUPERVISOR_STATE_ROOT_INPUT)
    if not isinstance(state_root, str):
        raise ValueError("state_root must be a string")

    from ..features.supervisor.desktop_snapshot import build_desktop_snapshot

    snapshot = build_desktop_snapshot(state_root=state_root)
    summary = {
        "snapshot_id": snapshot.get("snapshotId"),
        "generated_at": snapshot.get("generatedAt"),
        "source": snapshot.get("source"),
        "active_goal": snapshot.get("activeGoal"),
        "active_agent": snapshot.get("activeAgent"),
        "counts": snapshot.get("counts", {}),
        "approvals": snapshot.get("approvals", [])[:10],
        "activities": snapshot.get("activities", [])[:20],
        "artifacts": snapshot.get("artifacts", [])[:10],
    }
    return {
        "kind": "capability_run_result",
        "capability_id": SUPERVISOR_PROJECT_STATUS_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_readonly",
        "project_state_summary": summary,
    }
```

- [ ] **Step 4: Register the capability**

In `src/isotope/capabilities/catalog.py`, add a `Capability(...)` entry near other Supervisor capabilities:

```python
Capability(
    capability_id="supervisor.project_status",
    title="Supervisor Project Status",
    description=(
        "Read the current low-sensitive Supervisor desktop snapshot summary "
        "for project status, blockers, approvals, workers, and artifacts."
    ),
    maturity="v0.2",
    shelf="product_candidate",
    domain_tags=("supervisor", "project-status", "desktop-chat", "snapshot"),
    input_contract={
        "type": "object",
        "required": ["state_root"],
        "properties": {
            "state_root": {
                "type": "string",
                "description": "Supervisor state root directory.",
            },
        },
    },
    output_contract={
        "type": "object",
        "fields": ["status", "project_state_summary"],
    },
    safety_boundaries=(
        "read_only_state_projection",
        "desktop_snapshot_summary_only",
        "no_raw_transcript_return",
        "public_result_metadata",
    ),
    default_enabled=True,
    network_required=False,
)
```

- [ ] **Step 5: Route through CapabilityRunner**

In `src/isotope/capabilities/runner.py`, import the new constant and runner, then add:

```python
if capability_id == SUPERVISOR_PROJECT_STATUS_CAPABILITY:
    return run_supervisor_project_status(inputs=input_mapping)
```

Also call `validate_supervisor_readonly_inputs(...)` for this capability by including it in the Supervisor project-status predicate.

- [ ] **Step 6: Run the tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_discovers_supervisor_project_status_from_default_catalog tests/unit/capabilities/test_capability_runner_thin_shell.py::test_project_status_capability_returns_low_sensitive_snapshot_summary -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```bash
git add src/isotope/capabilities/supervisor.py src/isotope/capabilities/catalog.py src/isotope/capabilities/runner.py tests/unit/capabilities/test_capability_runner_thin_shell.py
git commit -m "feat(supervisor): expose project status capability"
```

## Task 3: Add Codex-Assisted Isotope Self-Repair Capability

**Files:**
- Create: `src/isotope/features/supervisor/self_repair.py`
- Create: `src/isotope/capabilities/self_repair.py`
- Modify: `src/isotope/capabilities/catalog.py`
- Modify: `src/isotope/capabilities/runner.py`
- Modify: `tests/unit/capabilities/test_capability_runner_thin_shell.py`

- [ ] **Step 1: Write failing capability tests**

Add these tests to `tests/unit/capabilities/test_capability_runner_thin_shell.py`:

```python
def test_runner_discovers_isotope_self_repair_from_default_catalog():
    runner = _runner()

    assert "isotope.self_repair" in _ids(runner.list_capabilities())
    description = runner.describe_capability("isotope.self_repair")

    assert description["input_contract"]["required"] == [
        "state_root",
        "cwd",
        "user_goal",
        "failure_summary",
    ]
    assert "codex_worker_required_for_non_trivial_changes" in description["safety_boundaries"]
    assert "no_auto_merge" in description["safety_boundaries"]


def test_isotope_self_repair_launches_codex_worker_in_isolated_worktree(tmp_path, monkeypatch):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    state_root = tmp_path / ".isotope"
    launched = {}

    def fake_prepare_launch_worktree(*, cwd, target_name, api=None):
        repair_root = tmp_path / "repo" / ".worktrees" / "supervisor" / "desktop-self-repair"
        repair_root.mkdir(parents=True)
        return {
            "enabled": True,
            "source_cwd": str(cwd),
            "cwd": str(repair_root),
            "worktree_root": str(repair_root),
            "branch": "codex/desktop-self-repair",
        }

    class FakeRecord:
        name = "desktop-self-repair"
        record_id = "managed-self-repair"
        pid = 12345
        backend = "process"
        worker_role = "self_repair"
        cwd = str(tmp_path / "repo" / ".worktrees" / "supervisor" / "desktop-self-repair")
        log_path = str(tmp_path / "self-repair.log")

    def fake_launch_managed_codex(**kwargs):
        launched.update(kwargs)
        return FakeRecord()

    monkeypatch.setattr(
        "isotope.features.supervisor.self_repair.prepare_launch_worktree",
        fake_prepare_launch_worktree,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.self_repair.launch_managed_codex",
        fake_launch_managed_codex,
    )

    result = _runner().run_capability(
        "isotope.self_repair",
        inputs={
            "state_root": str(state_root),
            "cwd": str(workspace),
            "user_goal": "让 Desktop chat 可以总结项目态势。",
            "failure_summary": "缺少低敏项目状态 capability。",
            "suggested_fix_summary": "新增 supervisor.project_status。",
        },
    )

    assert result["capability_id"] == "isotope.self_repair"
    assert result["status"] == "launched"
    assert result["self_repair"]["managed"]["name"] == "desktop-self-repair"
    assert result["self_repair"]["managed"]["worker_role"] == "self_repair"
    assert result["self_repair"]["worktree"]["enabled"] is True
    assert launched["codex_home"] == state_root
    assert launched["cwd"].name == "desktop-self-repair"
    assert launched["worker_role"] == "self_repair"
    assert "不要合入 main" in launched["prompt"]
    assert "让 Desktop chat 可以总结项目态势。" in launched["prompt"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_discovers_isotope_self_repair_from_default_catalog tests/unit/capabilities/test_capability_runner_thin_shell.py::test_isotope_self_repair_launches_codex_worker_in_isolated_worktree -q
```

Expected: FAIL because `isotope.self_repair` is not registered.

- [ ] **Step 3: Create the Supervisor self-repair helper**

Create `src/isotope/features/supervisor/self_repair.py`:

```python
"""Codex-assisted self-repair helpers for Isotope."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .commands.llm.execution import prepare_launch_worktree
from .planner.work_order import build_launch_work_order_prompt
from .registry import launch_managed_codex


SELF_REPAIR_WORKER_ROLE = "self_repair"
DEFAULT_SELF_REPAIR_NAME = "desktop-self-repair"


def launch_isotope_self_repair(
    *,
    state_root: Path | str,
    cwd: Path | str,
    user_goal: str,
    failure_summary: str,
    suggested_fix_summary: str = "",
    target_name: str = DEFAULT_SELF_REPAIR_NAME,
) -> dict[str, Any]:
    workspace = Path(cwd).expanduser()
    if not workspace.is_dir():
        raise ValueError(f"cwd must be an existing directory: {workspace}")
    name = _non_empty(target_name, "target_name")
    goal = _non_empty(user_goal, "user_goal")
    failure = _non_empty(failure_summary, "failure_summary")
    suggested = suggested_fix_summary.strip()

    worktree = prepare_launch_worktree(cwd=workspace, target_name=name)
    if worktree.get("failed"):
        return {
            "kind": "isotope_self_repair",
            "status": "blocked",
            "reason": "worktree setup failed",
            "worktree": worktree,
        }

    worker_cwd = Path(str(worktree["cwd"]))
    prompt = self_repair_work_order_prompt(
        target_name=name,
        cwd=worker_cwd,
        user_goal=goal,
        failure_summary=failure,
        suggested_fix_summary=suggested,
    )
    record = launch_managed_codex(
        codex_home=Path(state_root),
        cwd=worker_cwd,
        name=name,
        prompt=prompt,
        worker_role=SELF_REPAIR_WORKER_ROLE,
    )
    return {
        "kind": "isotope_self_repair",
        "status": "launched",
        "managed": {
            "name": record.name,
            "record_id": record.record_id,
            "pid": record.pid,
            "backend": record.backend,
            "worker_role": record.worker_role,
            "cwd": record.cwd,
            "log_path": record.log_path,
        },
        "worktree": worktree,
    }


def self_repair_work_order_prompt(
    *,
    target_name: str,
    cwd: Path,
    user_goal: str,
    failure_summary: str,
    suggested_fix_summary: str,
) -> str:
    goal = "\n".join(
        [
            "修复 Isotope 自身能力缺口，完成后让原始 Desktop chat 目标可以继续推进。",
            f"原始用户目标：{user_goal}",
            f"当前能力缺口：{failure_summary}",
            f"建议修复方向：{suggested_fix_summary or '由你根据代码和验证结果判断'}",
            "边界：在当前隔离 worktree 内修改 Isotope；不要合入 main；不要安装新依赖、skill 或 MCP，除非先明确汇报需要审批。",
            "要求：先检查相关代码和测试；实现最小可验证改动；运行目标测试；提交 Conventional Commits；最后用 SUPERVISOR_STATUS、SUPERVISOR_SUMMARY、SUPERVISOR_NEXT 汇报。",
        ]
    )
    return build_launch_work_order_prompt(
        target_name=target_name,
        cwd=str(cwd),
        goal=goal,
        allow_remote_push=False,
    )


def _non_empty(value: str, field_name: str) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text
```

- [ ] **Step 4: Create the capability wrapper**

Create `src/isotope/capabilities/self_repair.py`:

```python
"""Isotope self-repair capability wrapper."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from isotope.features.supervisor.self_repair import launch_isotope_self_repair
from isotope.platform.schemas.input_contract import missing_required_input_keys


ISOTOPE_SELF_REPAIR_CAPABILITY = "isotope.self_repair"


def is_self_repair_capability(capability_id: str) -> bool:
    return capability_id == ISOTOPE_SELF_REPAIR_CAPABILITY


def validate_self_repair_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    if not is_self_repair_capability(capability_id):
        return dict(inputs or {})
    input_mapping = dict(inputs or {})
    for name in ("state_root", "cwd", "user_goal", "failure_summary"):
        if name in missing_inputs:
            continue
        value = input_mapping.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
    for name in ("suggested_fix_summary", "target_name"):
        value = input_mapping.get(name)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
    return input_mapping


def run_isotope_self_repair(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    input_mapping = dict(inputs or {})
    missing_inputs = missing_required_input_keys(
        input_mapping,
        ["state_root", "cwd", "user_goal", "failure_summary"],
    )
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    validated = validate_self_repair_inputs(
        capability_id=ISOTOPE_SELF_REPAIR_CAPABILITY,
        inputs=input_mapping,
        missing_inputs=missing_inputs,
    )
    repair = launch_isotope_self_repair(
        state_root=Path(validated["state_root"]),
        cwd=Path(validated["cwd"]),
        user_goal=validated["user_goal"],
        failure_summary=validated["failure_summary"],
        suggested_fix_summary=validated.get("suggested_fix_summary", ""),
        target_name=validated.get("target_name", "desktop-self-repair"),
    )
    return {
        "kind": "capability_run_result",
        "capability_id": ISOTOPE_SELF_REPAIR_CAPABILITY,
        "status": repair["status"],
        "runner_kind": "codex_assisted_self_repair",
        "self_repair": repair,
    }
```

- [ ] **Step 5: Register and route the capability**

In `src/isotope/capabilities/catalog.py`, register:

```python
Capability(
    capability_id="isotope.self_repair",
    title="Isotope Self Repair",
    description=(
        "Launch Codex in an isolated Supervisor worktree to repair an Isotope "
        "capability gap. Isotope orchestrates context, isolation, verification "
        "expectations, and result projection; Codex performs non-trivial code changes."
    ),
    maturity="v0.1",
    shelf="product_candidate",
    domain_tags=("isotope", "self-repair", "codex", "desktop-chat"),
    input_contract={
        "type": "object",
        "required": ["state_root", "cwd", "user_goal", "failure_summary"],
        "properties": {
            "state_root": {"type": "string", "description": "Supervisor state root."},
            "cwd": {"type": "string", "description": "Source workspace directory."},
            "user_goal": {"type": "string", "description": "Original user goal."},
            "failure_summary": {"type": "string", "description": "Low-sensitive gap summary."},
            "suggested_fix_summary": {"type": "string", "description": "Optional fix direction."},
            "target_name": {"type": "string", "description": "Optional managed worker name."},
        },
    },
    output_contract={
        "type": "object",
        "fields": ["status", "runner_kind", "self_repair"],
    },
    safety_boundaries=(
        "codex_worker_required_for_non_trivial_changes",
        "isolated_worktree_required",
        "no_auto_merge",
        "no_dependency_skill_or_mcp_install_without_approval",
        "public_result_metadata",
    ),
    default_enabled=True,
    network_required=False,
)
```

In `src/isotope/capabilities/runner.py`, import `ISOTOPE_SELF_REPAIR_CAPABILITY`, `validate_self_repair_inputs`, and `run_isotope_self_repair`. Add validation before `_validate_inputs_against_contract(...)`:

```python
validate_self_repair_inputs(
    capability_id=capability_id,
    inputs=input_mapping,
    missing_inputs=missing_inputs,
)
```

Add execution routing:

```python
if capability_id == ISOTOPE_SELF_REPAIR_CAPABILITY:
    return run_isotope_self_repair(inputs=input_mapping)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_discovers_isotope_self_repair_from_default_catalog tests/unit/capabilities/test_capability_runner_thin_shell.py::test_isotope_self_repair_launches_codex_worker_in_isolated_worktree -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```bash
git add src/isotope/features/supervisor/self_repair.py src/isotope/capabilities/self_repair.py src/isotope/capabilities/catalog.py src/isotope/capabilities/runner.py tests/unit/capabilities/test_capability_runner_thin_shell.py
git commit -m "feat(isotope): add codex-assisted self repair capability"
```

## Task 4: Wire Project Status And Self-Repair Through Desktop Conversation

**Files:**
- Modify: `src/isotope/features/supervisor/conversation_loop.py`
- Modify: `tests/unit/features/supervisor/test_supervisor_conversation_loop.py`
- Modify: `tests/integration/supervisor/test_supervisor_desktop_chat.py`

- [ ] **Step 1: Write failing conversation-loop tests**

Add these tests to `tests/unit/features/supervisor/test_supervisor_conversation_loop.py`:

```python
def test_conversation_loop_can_use_project_status_without_fixed_route(tmp_path) -> None:
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "supervisor.project_status",
                    "arguments": {},
                    "rationale": "需要读取项目状态。",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "当前没有运行中的 worker，也没有等待审批。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path,
            user_message="现在项目卡在哪？",
            provider=provider,
            max_turns=3,
        )
    )

    assert [event.event for event in events] == ["capacity_start", "capacity_result", "delta"]
    assert events[0].payload["capacity_id"] == "supervisor.project_status"
    assert events[1].payload["status"] == "ok"
    second_prompt = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    assert "project_state_summary" in second_prompt
    assert events[2].payload["text"] == "当前没有运行中的 worker，也没有等待审批。"


def test_conversation_loop_can_launch_codex_assisted_self_repair(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()

    def fake_run_capability(self, capability_id, *, inputs=None, root_path=None, env=None):
        assert capability_id == "isotope.self_repair"
        return {
            "kind": "capability_run_result",
            "capability_id": "isotope.self_repair",
            "status": "launched",
            "runner_kind": "codex_assisted_self_repair",
            "self_repair": {
                "kind": "isotope_self_repair",
                "status": "launched",
                "managed": {
                    "name": "desktop-self-repair",
                    "record_id": "managed-self-repair",
                    "pid": 12345,
                    "backend": "process",
                    "worker_role": "self_repair",
                },
                "worktree": {
                    "enabled": True,
                    "cwd": str(workspace / ".worktrees" / "supervisor" / "desktop-self-repair"),
                },
            },
        }

    monkeypatch.setattr(
        "isotope.capabilities.runner.CapabilityRunner.run_capability",
        fake_run_capability,
    )
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "isotope.self_repair",
                    "arguments": {
                        "user_goal": "让 Desktop chat 能回答项目状态。",
                        "failure_summary": "缺少项目状态 capability。",
                        "suggested_fix_summary": "新增 supervisor.project_status。",
                    },
                    "rationale": "这是 Isotope 自身能力缺口。",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "我已启动 Codex 自修复 worker，并会等待它回报结果。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=workspace,
            user_message="你现在没法总结项目状态，自己补一下。",
            provider=provider,
            max_turns=3,
        )
    )

    assert [event.event for event in events] == ["capacity_start", "capacity_result", "delta"]
    assert events[0].payload["capacity_id"] == "isotope.self_repair"
    assert events[1].payload["status"] == "ok"
    assert events[1].payload["result_summary"]["agent_loop_tick_status"] == "executed"
    second_prompt = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    assert "desktop-self-repair" in second_prompt
    assert "raw_response" not in second_prompt
    assert events[2].payload["text"] == "我已启动 Codex 自修复 worker，并会等待它回报结果。"
```

- [ ] **Step 2: Run the unit tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_loop_can_use_project_status_without_fixed_route tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_loop_can_launch_codex_assisted_self_repair -q
```

Expected: first test fails before Task 2 is implemented; second test fails before Task 3 is implemented or before self-repair observations are structured enough.

- [ ] **Step 3: Make display inputs and observations useful**

In `src/isotope/features/supervisor/conversation_loop.py`, extend `_capacity_display_inputs(...)`:

```python
if capacity_id == "isotope.self_repair":
    display = dict(inputs)
    if "state_root" in display:
        display["state_root"] = "[supervisor_state_root]"
    if "cwd" in display:
        display["cwd"] = str(display["cwd"])
    return display
```

No special intent branch is added. The existing `call_capability` path handles both new capabilities.

- [ ] **Step 4: Add desktop endpoint integration tests**

Add to `tests/integration/supervisor/test_supervisor_desktop_chat.py`:

```python
def test_desktop_chat_stream_can_answer_from_project_status_capacity(tmp_path) -> None:
    provider = MultiResponseDesktopChatProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "supervisor.project_status",
                    "arguments": {},
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "项目状态已读取，没有等待审批。",
                }
            ),
        ]
    )

    events = list(
        stream_desktop_chat_events(
            state_root=tmp_path,
            question="现在项目卡在哪？",
            provider=provider,
        )
    )

    assert [event.event for event in events] == ["capacity_start", "capacity_result", "delta"]
    assert events[0].payload["capacity_id"] == "supervisor.project_status"
    assert events[2].payload["text"] == "项目状态已读取，没有等待审批。"
```

- [ ] **Step 5: Run conversation and desktop chat tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_loop_can_use_project_status_without_fixed_route tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_loop_can_launch_codex_assisted_self_repair tests/integration/supervisor/test_supervisor_desktop_chat.py::test_desktop_chat_stream_can_answer_from_project_status_capacity -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add src/isotope/features/supervisor/conversation_loop.py tests/unit/features/supervisor/test_supervisor_conversation_loop.py tests/integration/supervisor/test_supervisor_desktop_chat.py
git commit -m "feat(desktop): let chat use project state and self repair"
```

## Task 5: Render Desktop Actions In Product Language

**Files:**
- Modify: `apps/desktop/src/lib/view/capacityCallView.ts`
- Modify: `apps/desktop/src/lib/view/capacityCallView.test.ts`
- Modify: `apps/desktop/src/lib/components/main/CapacityCallCard.svelte`
- Modify: `apps/desktop/src/lib/components/main/CapacityCallDetails.svelte`
- Modify: `apps/desktop/src/lib/components/mini/MiniWindow.svelte`

- [ ] **Step 1: Write failing product-language tests**

Add to `apps/desktop/src/lib/view/capacityCallView.test.ts`:

```ts
test('uses product language for internal capability actions', () => {
  expect(capacityCallProductTitle({ ...call, capacityId: 'supervisor.project_status' })).toBe('读取项目状态');
  expect(capacityCallProductTitle({ ...call, capacityId: 'coding_task.execute' })).toBe('修改代码');
  expect(capacityCallProductTitle({ ...call, capacityId: 'isotope.self_repair' })).toBe('修复 Isotope 能力');
  expect(capacityCallProductTitle({ ...call, capacityId: 'supervisor.codex_operation' })).toBe('调度 Codex');
});

test('summarizes self repair without exposing raw capacity wording', () => {
  const selfRepair: DesktopCapacityCall = {
    ...call,
    capacityId: 'isotope.self_repair',
    title: 'isotope.self_repair',
    resultSummary: {
      status: 'launched',
      runner_kind: 'codex_assisted_self_repair'
    }
  };

  expect(capacityCallSummary(selfRepair)).toBe('修复 Isotope 能力 · status: launched · runner_kind: codex_assisted_self_repair');
});
```

- [ ] **Step 2: Run the frontend test to verify it fails**

Run:

```bash
cd apps/desktop && npm run test -- capacityCallView.test.ts
```

Expected: FAIL because `capacityCallProductTitle` does not exist and summaries start with raw IDs.

- [ ] **Step 3: Add product-title helper**

Modify `apps/desktop/src/lib/view/capacityCallView.ts`:

```ts
export function capacityCallProductTitle(call: DesktopCapacityCall): string {
  switch (call.capacityId) {
    case 'supervisor.project_status':
      return '读取项目状态';
    case 'coding_task.execute':
      return '修改代码';
    case 'isotope.self_repair':
      return '修复 Isotope 能力';
    case 'supervisor.codex_operation':
      return '调度 Codex';
    case 'research.search':
      return '查找资料';
    default:
      return call.title && call.title !== call.capacityId ? call.title : '执行能力';
  }
}
```

Change `capacityCallSummary(...)`:

```ts
export function capacityCallSummary(call: DesktopCapacityCall): string {
  const resultParts = Object.entries(call.resultSummary)
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .slice(0, 3)
    .map(([key, value]) => `${key}: ${formatInlineValue(value)}`);
  return [capacityCallProductTitle(call), ...resultParts].join(' · ');
}
```

- [ ] **Step 4: Update Svelte copy**

In `CapacityCallCard.svelte`, import `capacityCallProductTitle`, derive `productTitle`, and replace visible `capacity` text:

```svelte
<span class="text-xs font-semibold uppercase text-isotope-muted">action</span>
<div class="mt-1 truncate text-sm font-semibold">{productTitle}</div>
```

Update ARIA labels from `capacity 调用` and `capacity 详情` to `行动` and `行动详情`.

In `CapacityCallDetails.svelte`, replace:

```svelte
本次 capacity 调用没有返回详情载荷。
```

with:

```svelte
本次行动没有返回详情。
```

In `MiniWindow.svelte`, replace visible copy:

```svelte
向 Isotope 提问；使用能力时，过程会显示在主对话中。
```

and:

```svelte
{message.capacityCalls.length} 次行动
```

- [ ] **Step 5: Run frontend tests and copy audit**

Run:

```bash
cd apps/desktop && npm run test -- capacityCallView.test.ts copyAudit.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```bash
git add apps/desktop/src/lib/view/capacityCallView.ts apps/desktop/src/lib/view/capacityCallView.test.ts apps/desktop/src/lib/components/main/CapacityCallCard.svelte apps/desktop/src/lib/components/main/CapacityCallDetails.svelte apps/desktop/src/lib/components/mini/MiniWindow.svelte
git commit -m "feat(desktop): render capability actions in product language"
```

## Task 6: Refresh Desktop Snapshot After Chat Actions

**Files:**
- Modify: `apps/desktop/src/lib/stores/appState.ts`
- Modify: `apps/desktop/src/lib/stores/appState.test.ts`

- [ ] **Step 1: Write the failing refresh test**

Add to `apps/desktop/src/lib/stores/appState.test.ts`:

```ts
test('refreshes desktop snapshot after a successful chat action', async () => {
  const before = realSnapshot();
  const after: IsotopeSnapshot = {
    ...realSnapshot(),
    snapshotId: 'desktop_snapshot_after_chat',
    counts: {
      runningAgents: 1,
      needsAttention: 0,
      approvals: 0,
      artifacts: 1,
      errors: 0
    },
    approvals: []
  };
  let loadCount = 0;
  const state = createAppState({
    agentClient: {
      loadSnapshot: async () => {
        loadCount += 1;
        return loadCount === 1 ? before : after;
      },
      resolveApproval: async () => ({
        status: 'ok',
        approvalId: 'decision-1',
        resolution: 'approved',
        runStatus: 'completed',
        snapshot: after
      }),
      askDesktopQuestion: async (question, handlers) => {
        handlers?.onCapacityResult?.({
          id: 'capacity_isotope_self_repair',
          capacityId: 'isotope.self_repair',
          title: 'isotope.self_repair',
          status: 'ok',
          inputSummary: {},
          resultSummary: { status: 'launched' },
          details: []
        });
        return { question, answer: '已启动自修复。' };
      }
    }
  });

  await state.initialize();
  await state.askDesktopQuestion('你自己补一下能力');

  expect(loadCount).toBe(2);
  expect(get(state.snapshot)?.snapshotId).toBe('desktop_snapshot_after_chat');
  expect(get(state.snapshot)?.counts.runningAgents).toBe(1);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd apps/desktop && npm run test -- appState.test.ts
```

Expected: FAIL because `askDesktopQuestion(...)` does not reload the snapshot.

- [ ] **Step 3: Refresh snapshot after successful chat**

In `apps/desktop/src/lib/stores/appState.ts`, after assistant message update succeeds, add:

```ts
try {
  const loadedSnapshot = await clients.agentClient.loadSnapshot();
  snapshot.set(loadedSnapshot);
  selectedActivityId.update((current) =>
    current && loadedSnapshot.activities.some((activity) => activity.id === current)
      ? current
      : loadedSnapshot.activeActivity?.id ?? loadedSnapshot.activities[0]?.id ?? null
  );
} catch {
  // Chat already succeeded; keep the existing snapshot if refresh fails.
}
```

Keep `chatError` unchanged on refresh failure, because the chat turn itself completed.

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
cd apps/desktop && npm run test -- appState.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit Task 6**

```bash
git add apps/desktop/src/lib/stores/appState.ts apps/desktop/src/lib/stores/appState.test.ts
git commit -m "feat(desktop): refresh snapshot after chat actions"
```

## Task 7: Final Verification

**Files:**
- No source changes unless verification exposes a defect.

- [ ] **Step 1: Run backend targeted tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/llm/test_system_prompt_assets.py tests/unit/capabilities/test_capability_runner_thin_shell.py tests/unit/features/supervisor/test_supervisor_conversation_loop.py tests/integration/supervisor/test_supervisor_desktop_chat.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend targeted tests**

Run:

```bash
cd apps/desktop && npm run test -- capacityCallView.test.ts appState.test.ts copyAudit.test.ts
```

Expected: PASS.

- [ ] **Step 3: Run type check**

Run:

```bash
cd apps/desktop && npm run check
```

Expected: PASS.

- [ ] **Step 4: Run diff hygiene**

Run:

```bash
git diff --check
git status --short --branch
```

Expected: `git diff --check` exits 0. `git status --short --branch` shows only the current branch status after all task commits.

- [ ] **Step 5: Push branch**

Run:

```bash
git push
```

Expected: remote branch updates successfully.
