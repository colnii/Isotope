"""AI-first goal planning for the Codex Supervisor."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

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

    def to_dict(self) -> dict[str, str]:
        return {
            "goal": self.goal,
            "target_name": self.target_name,
            "reason": self.reason,
        }


def plan_supervisor_goals(
    *,
    root: Path | str,
    codex_home: Path | str,
    provider: GoalPlanningProvider,
    write: bool = False,
    limit: int = 3,
) -> dict[str, Any]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    workspace = Path(root).expanduser()
    if not workspace.is_dir():
        raise ValueError(f"cwd must be an existing directory: {workspace}")
    if provider is None:
        raise ValueError("LLM provider is required for goal planning")

    facts = read_goal_planning_facts(workspace)
    raw_answer = provider.summarize(
        build_goal_planning_messages(
            root=workspace,
            facts=facts,
            limit=limit,
            write_mode=write,
        )
    )
    candidates = parse_goal_candidates(raw_answer)[:limit]
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
            )
            written.append(goal.to_dict())

    return {
        "status": "ok",
        "mode": "write" if write else "preview",
        "root": str(workspace),
        "sources": list(PLANNING_DOCS),
        "candidates": [candidate.to_dict() for candidate in candidates],
        "written_goals": written,
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
    limit: int,
    write_mode: bool,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是 Codex Supervisor 的 AI-first goal planner。"
                "只能基于用户显式执行 goal plan 命令时提供的当前事实，"
                "生成一小批可执行 Supervisor goals；"
                "不得让无人下达目标的 loop 自行发明任务。"
                "只输出 JSON。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "workspace": str(root),
                    "facts": facts,
                    "goal_count_limit": limit,
                    "write_mode": write_mode,
                    "output_schema": {
                        "goals": [
                            {
                                "goal": "清晰、可执行、可交给 Codex worker 的目标",
                                "target_name": "短横线命名的 worker 名",
                                "reason": "一句话说明依据来自哪些当前事实",
                            }
                        ]
                    },
                    "rules": [
                        "每个 goal 必须能独立启动一个 Supervisor worker。",
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
    text = _required_string(raw_answer, "LLM answer")
    payload = _load_json_payload(text)
    raw_goals = payload.get("goals") if isinstance(payload, dict) else payload
    if not isinstance(raw_goals, list):
        raise ValueError("LLM goal planning answer must contain a goals list")
    candidates: list[GoalCandidate] = []
    for raw in raw_goals:
        if not isinstance(raw, dict):
            continue
        goal = _optional_string(raw.get("goal"))
        if goal is None:
            continue
        target_name = _optional_string(raw.get("target_name")) or _target_name_from_goal(goal)
        reason = _optional_string(raw.get("reason")) or "LLM 基于当前事实生成。"
        candidates.append(
            GoalCandidate(
                goal=goal,
                target_name=_normalize_target_name(target_name),
                reason=reason,
            )
        )
    return candidates


def _load_json_payload(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match is None:
            raise ValueError("LLM goal planning answer is not valid JSON") from None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise ValueError("LLM goal planning answer is not valid JSON") from exc


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
