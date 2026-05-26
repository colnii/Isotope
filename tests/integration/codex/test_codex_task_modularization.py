from isotope.integrations.codex import task
from isotope.integrations.codex import task_contract
from isotope.integrations.codex import task_request


def test_codex_task_facade_reuses_contract_and_request_modules():
    assert task.CodexTaskRequest is task_contract.CodexTaskRequest
    assert task.CodexTaskResult is task_contract.CodexTaskResult
    assert task.build_codex_task_request is task_request.build_codex_task_request
