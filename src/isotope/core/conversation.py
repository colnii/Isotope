"""Product core facade for single-process conversation flow."""

from __future__ import annotations

from pathlib import Path

from ..runtime.in_process import InProcessServer
from .dispatch import RuntimeDispatch
from .response import CoreTurnResponse
from .session import CoreRun, CoreSession


class ProductCore:
    """Thin product flow layer over the current in-process runtime."""

    def __init__(self, runtime: InProcessServer):
        self.runtime = runtime
        self.dispatch = RuntimeDispatch(runtime)

    @classmethod
    def in_process(cls, root: Path | str) -> "ProductCore":
        return cls(InProcessServer(Path(root)))

    def start_session(self) -> CoreSession:
        return self.dispatch.start_session()

    def start_run(self, session_id: str, *, goal: str) -> CoreRun:
        return self.dispatch.start_run(session_id, goal=goal)

    def submit_user_message(self, run_id: str, text: str) -> CoreTurnResponse:
        return self.dispatch.submit_user_message(run_id, text)
