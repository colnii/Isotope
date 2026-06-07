"""Parallel event fan-in helpers for Supervisor conversation capacity calls."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from queue import Queue
from threading import Thread
from typing import Any


def run_parallel_event_generators(
    generators: Iterable[Iterator[Any]],
) -> Iterator[Any]:
    generator_list = list(generators)
    if not generator_list:
        return

    queue: Queue[tuple[str, Any]] = Queue()

    def worker(generator: Iterator[Any]) -> None:
        try:
            for event in generator:
                queue.put(("event", event))
                if getattr(event, "event", None) == "capacity_start":
                    payload = getattr(event, "payload", {})
                    if isinstance(payload, dict):
                        queue.put(("event", _capacity_update_event(event, payload)))
        except BaseException as exc:  # noqa: BLE001 - re-raise in caller thread.
            queue.put(("error", exc))
        finally:
            queue.put(("done", None))

    threads = [Thread(target=worker, args=(generator,), daemon=True) for generator in generator_list]
    for thread in threads:
        thread.start()

    finished = 0
    while finished < len(threads):
        kind, payload = queue.get()
        if kind == "event":
            yield payload
        elif kind == "error":
            raise payload
        elif kind == "done":
            finished += 1

    for thread in threads:
        thread.join(timeout=0.1)


def _capacity_update_event(event: Any, payload: dict[str, Any]) -> Any:
    event_type = type(event)
    return event_type(
        event="capacity_update",
        payload={
            "id": payload.get("id"),
            "capacity_id": payload.get("capacity_id"),
            "title": payload.get("title"),
            "status": "running",
            "result": {"phase": "executing"},
            "details": [
                {
                    "label": "Progress",
                    "kind": "json",
                    "content": {"phase": "executing"},
                }
            ],
        },
        provider=getattr(event, "provider", "unknown"),
        model=getattr(event, "model", "unknown"),
    )
