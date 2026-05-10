import importlib

import pytest

from isotope_kernel import server


def _kernel_error_type():
    return importlib.import_module("isotope_kernel.errors").KernelError


def _new_completed_run(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="produce a hello artifact")
    api.submit_input(run["run_id"], text="hello")
    return api, run["run_id"]


def test_kernel_error_preserves_value_error_message_and_stable_attrs():
    KernelError = _kernel_error_type()

    error = KernelError(
        "run is terminal: completed",
        code="run_terminal",
        category="conflict",
        retryable=False,
        http_status=409,
        details={"run_id": "run_001", "status": "completed"},
    )

    assert isinstance(error, ValueError)
    assert str(error) == "run is terminal: completed"
    assert error.args[0] == "run is terminal: completed"
    assert error.code == "run_terminal"
    assert error.category == "conflict"
    assert error.retryable is False
    assert error.http_status == 409
    assert error.details == {"run_id": "run_001", "status": "completed"}


def test_kernel_error_rejects_secret_or_raw_content_details():
    KernelError = _kernel_error_type()

    with pytest.raises(ValueError, match="details"):
        KernelError(
            "raw payload rejected",
            code="invalid_request",
            category="validation",
            retryable=False,
            http_status=400,
            details={"secret": "do-not-leak"},
        )


def test_terminal_run_helper_error_is_structured_without_message_parsing(tmp_path):
    KernelError = _kernel_error_type()
    api, run_id = _new_completed_run(tmp_path)

    with pytest.raises(ValueError) as exc_info:
        api.submit_input(run_id, text="second input")

    assert isinstance(exc_info.value, KernelError)
    assert str(exc_info.value) == "run is terminal: completed"
    assert exc_info.value.code == "run_terminal"
    assert exc_info.value.category == "conflict"
    assert exc_info.value.retryable is False
    assert exc_info.value.http_status == 409
    assert exc_info.value.details == {"run_id": run_id, "status": "completed"}


def test_unknown_run_helper_error_is_structured(tmp_path):
    KernelError = _kernel_error_type()
    api = server.InProcessServer(tmp_path)

    with pytest.raises(ValueError) as exc_info:
        api.get_run_state("run_missing")

    assert isinstance(exc_info.value, KernelError)
    assert exc_info.value.code == "unknown_run"
    assert exc_info.value.category == "not_found"
    assert exc_info.value.retryable is False
    assert exc_info.value.http_status == 404
    assert exc_info.value.details == {"run_id": "run_missing"}


def test_unknown_session_helper_error_is_structured(tmp_path):
    KernelError = _kernel_error_type()
    api = server.InProcessServer(tmp_path)

    with pytest.raises(ValueError) as exc_info:
        api.create_run("session_missing", goal="hello")

    assert isinstance(exc_info.value, KernelError)
    assert exc_info.value.code == "unknown_session"
    assert exc_info.value.category == "not_found"
    assert exc_info.value.retryable is False
    assert exc_info.value.http_status == 404
    assert exc_info.value.details == {"session_id": "session_missing"}


def test_invalid_request_helper_error_is_structured(tmp_path):
    KernelError = _kernel_error_type()
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="hello")

    with pytest.raises(ValueError) as exc_info:
        api.submit_input(run["run_id"], text="")

    assert isinstance(exc_info.value, KernelError)
    assert exc_info.value.code == "invalid_request"
    assert exc_info.value.category == "validation"
    assert exc_info.value.retryable is False
    assert exc_info.value.http_status == 400
    assert exc_info.value.details == {"field": "text"}


def test_not_enabled_helper_result_uses_structured_error_shape(tmp_path):
    api = server.InProcessServer(tmp_path)

    result = api.create_checkpoint("run_missing")

    assert result["status"] == "not_enabled"
    assert result["error"]["code"] == "not_enabled"
    assert result["error"]["category"] == "not_enabled"
    assert result["error"]["retryable"] is False
    assert result["error"]["details"] == {"capability": "checkpoint"}
