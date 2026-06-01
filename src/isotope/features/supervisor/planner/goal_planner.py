"""AI-first goal planning for the Codex Supervisor."""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from isotope.llm.prompts import load_system_prompt

from .goal_queue import record_supervisor_goal

PLANNING_DOCS = (
    "docs/current/status.md",
    "docs/current/agent-task-queue.md",
    "docs/current/supervisor-capability-map.md",
)
MAX_DOC_CHARS = 20000


class GoalPlanningProvider(Protocol):
    def summarize(self, messages: list[dict[str, str]]) -> str:
        ...


@dataclass(frozen=True)
class GoalCandidate:
    goal: str
    target_name: str
    reason: str
    depends_on: tuple[str, ...] = ()
    stage: str | None = None
    scope: str | None = None
    merge_gate: str | None = None

    def to_dict(self) -> dict[str, Any]:
        item: dict[str, Any] = {
            "goal": self.goal,
            "target_name": self.target_name,
            "reason": self.reason,
        }
        if self.depends_on:
            item["depends_on"] = list(self.depends_on)
        if self.stage is not None:
            item["stage"] = self.stage
        if self.scope is not None:
            item["scope"] = self.scope
        if self.merge_gate is not None:
            item["merge_gate"] = self.merge_gate
        return item


@dataclass(frozen=True)
class GoalPlanningResult:
    candidates: list[GoalCandidate]
    plan_summary: str | None
    phases: list[dict[str, Any]]
    parallel_recommendations: list[dict[str, Any]]
    stop_conditions: list[str]
    acceptance_conditions: list[str]


def plan_supervisor_goals(
    *,
    root: Path | str,
    codex_home: Path | str,
    provider: GoalPlanningProvider,
    user_goal: str | None = None,
    write: bool = False,
    limit: int = 3,
    planning_trigger: str = "manual",
) -> dict[str, Any]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    workspace = Path(root).expanduser()
    if not workspace.is_dir():
        raise ValueError(f"cwd must be an existing directory: {workspace}")
    if provider is None:
        raise ValueError("LLM provider is required for goal planning")

    facts = read_goal_planning_facts(workspace)
    messages = build_goal_planning_messages(
        root=workspace,
        facts=facts,
        user_goal=_optional_string(user_goal),
        limit=limit,
        write_mode=write,
        planning_trigger=planning_trigger,
    )
    raw_answer = provider.summarize(messages)
    planning, parse_repaired = _parse_or_repair_goal_planning_result(
        raw_answer,
        provider=provider,
        original_messages=messages,
    )
    candidates = planning.candidates
    if not candidates:
        raise ValueError("LLM returned no goal candidates")

    written = []
    if write:
        for candidate in candidates:
            goal = record_supervisor_goal(
                codex_home=codex_home,
                cwd=workspace,
                goal=candidate.goal,
                target_name=candidate.target_name,
                depends_on=candidate.depends_on,
                stage=candidate.stage,
                scope=candidate.scope,
                merge_gate=candidate.merge_gate,
            )
            written.append(goal.to_dict())

    return {
        "status": "ok",
        "mode": "write" if write else "preview",
        "root": str(workspace),
        "user_goal": _optional_string(user_goal),
        "planning_trigger": planning_trigger,
        "parallel_launch_limit": limit,
        "parse_repaired": parse_repaired,
        "sources": list(PLANNING_DOCS),
        "candidates": [candidate.to_dict() for candidate in candidates],
        "written_goals": written,
        "plan_summary": planning.plan_summary,
        "phases": planning.phases,
        "parallel_recommendations": planning.parallel_recommendations,
        "stop_conditions": planning.stop_conditions,
        "acceptance_conditions": planning.acceptance_conditions,
    }


def read_goal_planning_facts(root: Path) -> dict[str, str]:
    facts: dict[str, str] = {}
    missing: list[str] = []
    for relative in PLANNING_DOCS:
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            missing.append(relative)
            continue
        facts[relative] = _clip(text)
    if missing:
        raise ValueError("missing goal planning docs: " + ", ".join(missing))
    return facts


def build_goal_planning_messages(
    *,
    root: Path,
    facts: dict[str, str],
    user_goal: str | None,
    limit: int,
    write_mode: bool,
    planning_trigger: str = "manual",
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": load_system_prompt("goal_planning"),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "workspace": str(root),
                    "user_goal": user_goal,
                    "planning_trigger": planning_trigger,
                    "facts": facts,
                    "parallel_launch_limit": limit,
                    "write_mode": write_mode,
                    "accepted_output_formats": [
                        "首选严格 JSON。",
                        "如果模型无法稳定输出 JSON，可输出清晰 TOML；系统会先用本地解析器转成 JSON。",
                        "无论哪种格式，都必须包含可执行 goals。",
                    ],
                    "output_schema": {
                        "plan_summary": (
                            "面向完整功能板块的可审阅计划摘要；"
                            "如果只是在拆一个小目标，可用一句话说明范围。"
                        ),
                        "phases": [
                            {
                                "name": "阶段或批次名称",
                                "goals": ["本阶段覆盖的可执行目标或交付点"],
                                "stop_conditions": ["本阶段应该暂停或回到用户的条件"],
                                "acceptance_conditions": ["本阶段可验收的具体证据"],
                            }
                        ],
                        "parallel_recommendations": [
                            {
                                "batch": "可并行批次名称",
                                "targets": ["可并行 worker target_name"],
                                "reason": "为什么这些目标可以并行",
                            }
                        ],
                        "stop_conditions": ["整个板块规划应停止或请求用户的条件"],
                        "acceptance_conditions": ["整个板块完成验收所需的证据"],
                        "goals": [
                            {
                                "goal": "清晰、可执行、可交给 Codex worker 的目标",
                                "target_name": "短横线命名的 worker 名",
                                "reason": "一句话说明依据来自哪些当前事实",
                                "depends_on": ["可选，必须先完成并合入的 target_name 或 goal_id"],
                                "stage": "可选，同阶段可并行；后续阶段必须等前置阶段完成",
                                "scope": "可选，本目标触碰的代码或文档范围",
                                "merge_gate": "可选，解锁本目标前必须完成的 merge gate 名称",
                            }
                        ]
                    },
                    "rules": [
                        "每个 goal 必须能独立启动一个 Supervisor worker。",
                        "完整规划可以多于 parallel_launch_limit；parallel_launch_limit 只表示建议首批并发上限，不是规划截断上限。",
                        "如果 user_goal 存在，必须围绕它拆解可执行目标。",
                        "当 user_goal 指向完整功能板块时，必须输出 plan_summary、phases、parallel_recommendations、stop_conditions 和 acceptance_conditions。",
                        "不要输出泛泛的继续推进、优化系统、阅读文档。",
                        "不要生成需要用户另行解释范围的任务。",
                        "target_name 使用小写字母、数字和短横线。",
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
    ]


def parse_goal_candidates(raw_answer: str) -> list[GoalCandidate]:
    return parse_goal_planning_result(raw_answer).candidates


def _parse_or_repair_goal_planning_result(
    raw_answer: str,
    *,
    provider: GoalPlanningProvider,
    original_messages: list[dict[str, str]],
) -> tuple[GoalPlanningResult, bool]:
    try:
        return parse_goal_planning_result(raw_answer), False
    except ValueError as original_error:
        repair_answer = provider.summarize(
            build_goal_planning_repair_messages(
                raw_answer=raw_answer,
                original_messages=original_messages,
            )
        )
        try:
            return parse_goal_planning_result(repair_answer), True
        except ValueError:
            raise original_error from None


def build_goal_planning_repair_messages(
    *,
    raw_answer: str,
    original_messages: list[dict[str, str]],
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": load_system_prompt("goal_planning_repair"),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "task": "repair_goal_planning_output",
                    "raw_answer": raw_answer,
                    "original_goal_request": (
                        original_messages[1]["content"]
                        if len(original_messages) > 1
                        else ""
                    ),
                    "required_json_shape": {
                        "plan_summary": "可选，规划摘要",
                        "phases": [
                            {
                                "name": "可选，阶段名",
                                "goals": ["可选，本阶段目标"],
                                "stop_conditions": ["可选，暂停条件"],
                                "acceptance_conditions": ["可选，验收条件"],
                            }
                        ],
                        "parallel_recommendations": [
                            {
                                "batch": "可选，并行批次名",
                                "targets": ["可选，worker target_name"],
                                "reason": "可选，并行原因",
                            }
                        ],
                        "stop_conditions": ["可选，整体暂停条件"],
                        "acceptance_conditions": ["可选，整体验收条件"],
                        "goals": [
                            {
                                "goal": "必填，可执行目标",
                                "target_name": "必填，小写短横线 worker 名",
                                "reason": "必填，依据",
                                "depends_on": ["可选，依赖的 target_name 或 goal_id"],
                                "stage": "可选，阶段名",
                                "scope": "可选，影响范围",
                                "merge_gate": "可选，依赖的 merge gate",
                            }
                        ],
                    },
                    "rules": [
                        "必须输出一个 JSON object。",
                        "必须包含非空 goals 数组。",
                        "不得输出 Markdown 代码块包裹。",
                        "如果原文没有 target_name，按 goal 生成短横线英文名。",
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
    ]


def parse_goal_planning_result(raw_answer: str) -> GoalPlanningResult:
    text = _required_string(raw_answer, "LLM answer")
    payload = _load_json_payload(text)
    candidates = _goal_candidates_from_payload(payload)
    if not candidates:
        raise ValueError("LLM goal planning answer must contain usable goals")
    return GoalPlanningResult(
        candidates=candidates,
        plan_summary=_planning_summary_from_payload(payload),
        phases=_phase_list_from_payload(payload),
        parallel_recommendations=_parallel_recommendations_from_payload(payload),
        stop_conditions=_string_list_from_mapping(payload, "stop_conditions"),
        acceptance_conditions=_string_list_from_mapping(
            payload,
            "acceptance_conditions",
        ),
    )


def _goal_candidates_from_payload(payload: Any) -> list[GoalCandidate]:
    raw_goals = payload.get("goals") if isinstance(payload, dict) else payload
    if not isinstance(raw_goals, list):
        return []
    candidates: list[GoalCandidate] = []
    for raw in raw_goals:
        if not isinstance(raw, dict):
            continue
        goal = _optional_string(raw.get("goal"))
        if goal is None:
            continue
        target_name = _optional_string(raw.get("target_name")) or _target_name_from_goal(goal)
        reason = _optional_string(raw.get("reason")) or "LLM 基于当前事实生成。"
        depends_on = tuple(
            _normalize_target_name(item)
            for item in _string_list(raw.get("depends_on"))
        )
        candidates.append(
            GoalCandidate(
                goal=goal,
                target_name=_normalize_target_name(target_name),
                reason=reason,
                depends_on=depends_on,
                stage=_optional_string(raw.get("stage")),
                scope=_optional_string(raw.get("scope")),
                merge_gate=_optional_string(raw.get("merge_gate")),
            )
        )
    return candidates


def _planning_summary_from_payload(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    return _optional_string(payload.get("plan_summary"))


def _phase_list_from_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    raw_phases = payload.get("phases")
    if not isinstance(raw_phases, list):
        return []
    phases: list[dict[str, Any]] = []
    for raw in raw_phases:
        if not isinstance(raw, dict):
            continue
        phase: dict[str, Any] = {}
        name = _optional_string(raw.get("name"))
        if name:
            phase["name"] = name
        goals = _string_list(raw.get("goals"))
        if goals:
            phase["goals"] = goals
        stop_conditions = _string_list(raw.get("stop_conditions"))
        if stop_conditions:
            phase["stop_conditions"] = stop_conditions
        acceptance_conditions = _string_list(raw.get("acceptance_conditions"))
        if acceptance_conditions:
            phase["acceptance_conditions"] = acceptance_conditions
        if phase:
            phases.append(phase)
    return phases


def _parallel_recommendations_from_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    raw_recommendations = payload.get("parallel_recommendations")
    if not isinstance(raw_recommendations, list):
        return []
    recommendations: list[dict[str, Any]] = []
    for raw in raw_recommendations:
        if not isinstance(raw, dict):
            continue
        recommendation: dict[str, Any] = {}
        batch = _optional_string(raw.get("batch"))
        if batch:
            recommendation["batch"] = batch
        targets = _string_list(raw.get("targets"))
        if targets:
            recommendation["targets"] = [
                _normalize_target_name(target) for target in targets
            ]
        reason = _optional_string(raw.get("reason"))
        if reason:
            recommendation["reason"] = reason
        if recommendation:
            recommendations.append(recommendation)
    return recommendations


def _string_list_from_mapping(payload: Any, key: str) -> list[str]:
    if not isinstance(payload, dict):
        return []
    return _string_list(payload.get(key))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = _optional_string(item)
        if text:
            items.append(text)
    return items


def _load_json_payload(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for payload in reversed(_json_payload_candidates(text)):
            if _has_goal_list_payload(payload):
                return payload
        toml_payload = _toml_payload(text)
        if _has_goal_list_payload(toml_payload):
            return toml_payload
        raise ValueError(
            "LLM goal planning answer did not contain usable goals JSON"
        ) from None


def _json_payload_candidates(text: str) -> list[Any]:
    decoder = json.JSONDecoder()
    candidates: list[Any] = []
    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        candidates.append(payload)
    return candidates


def _toml_payload(text: str) -> Any:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return None


def _has_goal_list_payload(payload: Any) -> bool:
    return bool(_goal_candidates_from_payload(payload))


def _target_name_from_goal(goal: str) -> str:
    ascii_words = re.findall(r"[A-Za-z0-9]+", goal.lower())
    if ascii_words:
        return "-".join(ascii_words[:6])
    return "supervisor-goal"


def _normalize_target_name(value: str) -> str:
    text = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    text = re.sub(r"-+", "-", text)
    return text[:80] or "supervisor-goal"


def _clip(text: str) -> str:
    if len(text) <= MAX_DOC_CHARS:
        return text
    return text[:MAX_DOC_CHARS] + "\n...[truncated]"


def _required_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must not be empty")
    return value.strip()


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()
