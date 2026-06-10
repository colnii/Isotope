"""Timeout helpers for Supervisor conversation capability execution."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Any

RESEARCH_SEARCH_CAPACITY_TIMEOUT_SECONDS = 120.0


class CapacityExecutionTimeout(TimeoutError):
    def __init__(self, *, capacity_id: str, timeout_seconds: float) -> None:
        self.capacity_id = capacity_id
        self.timeout_seconds = timeout_seconds
        super().__init__(capacity_timeout_message(capacity_id, timeout_seconds))


def execute_capacity_step_with_timeout(
    *,
    goal: str,
    capability_id: str,
    inputs: dict[str, Any],
    state_root: Path,
    timeout_seconds: float | None,
    executor_func: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    if timeout_seconds is None:
        return executor_func(
            goal=goal,
            capability_id=capability_id,
            inputs=inputs,
            state_root=state_root,
        )
    if timeout_seconds <= 0:
        raise CapacityExecutionTimeout(
            capacity_id=capability_id,
            timeout_seconds=timeout_seconds,
        )
    executor = ThreadPoolExecutor(max_workers=1)
    pending_call = executor.submit(
        executor_func,
        goal=goal,
        capability_id=capability_id,
        inputs=inputs,
        state_root=state_root,
    )
    try:
        return pending_call.result(timeout=timeout_seconds)
    except FutureTimeoutError as exc:
        pending_call.cancel()
        raise CapacityExecutionTimeout(
            capacity_id=capability_id,
            timeout_seconds=timeout_seconds,
        ) from exc
    except TimeoutError as exc:
        pending_call.cancel()
        if isinstance(exc, CapacityExecutionTimeout):
            raise
        raise CapacityExecutionTimeout(
            capacity_id=capability_id,
            timeout_seconds=timeout_seconds,
        ) from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def capacity_timeout_seconds(
    capacity_id: str,
    timeout_seconds: float | None,
) -> float | None:
    if capacity_id == "supervisor.goal_plan":
        return None
    if capacity_id == "research.search":
        if timeout_seconds is None:
            return RESEARCH_SEARCH_CAPACITY_TIMEOUT_SECONDS
        if timeout_seconds < 1:
            return timeout_seconds
        return max(timeout_seconds, RESEARCH_SEARCH_CAPACITY_TIMEOUT_SECONDS)
    return timeout_seconds


def capacity_timeout_message(capacity_id: str, timeout_seconds: float) -> str:
    return (
        f"{capacity_id} capacity execution timed out after "
        f"{timeout_seconds:g}s"
    )
