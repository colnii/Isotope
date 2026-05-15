"""Product core facade for single-process conversation flow."""

from __future__ import annotations

from pathlib import Path

from ..platform.ids import new_id
from ..runtime.in_process import InProcessServer
from .dispatch import RuntimeDispatch
from .response import CoreConversationState, CoreTurn, CoreTurnResponse
from .session import CoreConversation, CoreRun, CoreSession
from .task import CoreTask, CoreTaskState


class ProductCore:
    """Thin product flow layer over the current in-process runtime."""

    def __init__(self, runtime: InProcessServer):
        self.runtime = runtime
        self.dispatch = RuntimeDispatch(runtime)
        self._conversations: dict[str, CoreConversation] = {}
        self._conversation_runs: dict[str, list[str]] = {}
        self._turns: dict[str, list[CoreTurn]] = {}
        self._tasks: dict[str, CoreTask] = {}

    @classmethod
    def in_process(cls, root: Path | str) -> "ProductCore":
        return cls(InProcessServer(Path(root)))

    def start_session(self) -> CoreSession:
        return self.dispatch.start_session()

    def start_run(self, session_id: str, *, goal: str) -> CoreRun:
        return self.dispatch.start_run(session_id, goal=goal)

    def submit_user_message(self, run_id: str, text: str) -> CoreTurnResponse:
        return self.dispatch.submit_user_message(run_id, text)

    def start_conversation(self, *, goal: str) -> CoreConversation:
        conversation = self.dispatch.start_conversation(goal=goal)
        self._conversations[conversation.conversation_id] = conversation
        self._conversation_runs[conversation.conversation_id] = [conversation.run_id]
        self._turns[conversation.conversation_id] = []
        return conversation

    def submit_message(self, conversation_id: str, text: str) -> CoreTurnResponse:
        conversation = self._require_conversation(conversation_id)
        run_id = self._active_run_id(conversation)
        response = self.submit_user_message(run_id, text)
        self._turns[conversation_id].append(CoreTurn(text=text, response=response))
        return response

    def get_conversation(self, conversation_id: str) -> CoreConversationState:
        conversation = self._require_conversation(conversation_id)
        return CoreConversationState(
            conversation_id=conversation.conversation_id,
            session_id=conversation.session_id,
            run_id=conversation.run_id,
            goal=conversation.goal,
            run_ids=tuple(self._conversation_runs[conversation_id]),
            turns=tuple(self._turns[conversation_id]),
        )

    def _require_conversation(self, conversation_id: str) -> CoreConversation:
        try:
            return self._conversations[conversation_id]
        except KeyError as exc:
            raise ValueError(f"unknown conversation_id: {conversation_id}") from exc

    def _active_run_id(self, conversation: CoreConversation) -> str:
        run_ids = self._conversation_runs[conversation.conversation_id]
        if not self._turns[conversation.conversation_id]:
            return run_ids[-1]
        run = self.dispatch.start_run(conversation.session_id, goal=conversation.goal)
        run_ids.append(run.run_id)
        return run.run_id

    def start_task(self, *, goal: str) -> CoreTask:
        conversation = self.start_conversation(goal=goal)
        task = CoreTask(
            task_id=new_id("task"),
            conversation_id=conversation.conversation_id,
            goal=goal,
        )
        self._tasks[task.task_id] = task
        return task

    def submit_task_message(self, task_id: str, text: str) -> CoreTaskState:
        task = self._require_task(task_id)
        self.submit_message(task.conversation_id, text)
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> CoreTaskState:
        task = self._require_task(task_id)
        conversation = self.get_conversation(task.conversation_id)
        status = "completed" if conversation.latest_response is not None else "created"
        return CoreTaskState(
            task_id=task.task_id,
            conversation=conversation,
            status=status,
        )

    def _require_task(self, task_id: str) -> CoreTask:
        try:
            return self._tasks[task_id]
        except KeyError as exc:
            raise ValueError(f"unknown task_id: {task_id}") from exc
