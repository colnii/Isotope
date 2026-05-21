from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from isotope.features.supervisor.runner import main as supervisor_main


def test_supervisor_integration_review_groups_ready_and_already_integrated(tmp_path):
    from isotope.features.supervisor.integration_review import (
        collect_integration_reviews,
        render_integration_review_plain,
    )

    codex_home = tmp_path / ".codex"
    ready_cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "ready-12345678"
    done_cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "done-12345678"
    ready_cwd.mkdir(parents=True)
    done_cwd.mkdir(parents=True)
    _write_done_record(codex_home, record_id="managed-ready", name="ready", cwd=ready_cwd)
    _write_done_record(codex_home, record_id="managed-done", name="done", cwd=done_cwd)

    fake_run = _fake_git(
        {
            ready_cwd: {
                ("rev-parse", "--abbrev-ref", "HEAD"): (0, "supervisor/ready-12345678\n", ""),
                ("rev-parse", "HEAD"): (0, "ready111\n", ""),
                ("rev-parse", "main"): (0, "main999\n", ""),
                ("status", "--short"): (0, "", ""),
                ("merge-base", "--is-ancestor", "ready111", "main"): (1, "", ""),
                ("merge-base", "--is-ancestor", "main", "ready111"): (0, "", ""),
                ("cherry", "main", "ready111"): (0, "+ ready111\n", ""),
                ("merge-tree", "--write-tree", "main", "ready111"): (0, "tree-ok\n", ""),
            },
            done_cwd: {
                ("rev-parse", "--abbrev-ref", "HEAD"): (0, "supervisor/done-12345678\n", ""),
                ("rev-parse", "HEAD"): (0, "done222\n", ""),
                ("rev-parse", "main"): (0, "main999\n", ""),
                ("status", "--short"): (0, "", ""),
                ("merge-base", "--is-ancestor", "done222", "main"): (0, "", ""),
                ("merge-base", "--is-ancestor", "main", "done222"): (1, "", ""),
                ("merge-tree", "--write-tree", "main", "done222"): (0, "tree-ok\n", ""),
            },
        }
    )

    payload = collect_integration_reviews(
        codex_home=codex_home,
        include_unfinished=True,
        run=fake_run,
        validation_run=_fake_validation(
            {
                ready_cwd: {
                    _lint_command(): (0, "lint ok\n", ""),
                    _pytest_command(): (0, "12 passed\n", ""),
                },
            }
        ),
    )

    assert payload["status"] == "ok"
    assert payload["base_ref"] == "main"
    assert payload["summary"] == {
        "total": 2,
        "merge_workers": 0,
        "ready_to_integrate": 1,
        "already_integrated": 1,
        "needs_review": 0,
        "conflict_risk": 0,
        "stale_missing_worktrees": 0,
    }
    ready = payload["groups"]["ready_to_integrate"][0]
    assert ready["record_id"] == "managed-ready"
    assert ready["branch"] == "supervisor/ready-12345678"
    assert ready["worker_commit"] == "ready111"
    assert ready["base_commit"] == "main999"
    assert ready["main_contains_worker"] is False
    assert ready["worker_contains_main"] is True
    assert ready["reason"] == "worker 已完成、分支干净、main 尚未包含、未检测到 merge conflict，且 lint/test 已通过。"
    assert ready["validation"]["status"] == "passed"
    already = payload["groups"]["already_integrated"][0]
    assert already["record_id"] == "managed-done"
    assert already["main_contains_worker"] is True

    plain = render_integration_review_plain(payload)
    assert "ready_to_integrate：1" in plain
    assert "already_integrated：1" in plain
    assert "supervisor/ready-12345678 @ ready111" in plain
    assert "validation：passed" in plain


def test_supervisor_integration_review_blocks_ready_worker_when_tests_fail(tmp_path):
    from isotope.features.supervisor.integration_review import (
        collect_integration_reviews,
        render_integration_review_plain,
    )

    codex_home = tmp_path / ".codex"
    cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "ready-tests-fail"
    cwd.mkdir(parents=True)
    _write_done_record(codex_home, record_id="managed-ready", name="ready", cwd=cwd)

    fake_run = _fake_git(
        {
            cwd: {
                ("rev-parse", "--abbrev-ref", "HEAD"): (0, "supervisor/ready-tests-fail\n", ""),
                ("rev-parse", "HEAD"): (0, "ready111\n", ""),
                ("rev-parse", "main"): (0, "main999\n", ""),
                ("status", "--short"): (0, "", ""),
                ("merge-base", "--is-ancestor", "ready111", "main"): (1, "", ""),
                ("merge-base", "--is-ancestor", "main", "ready111"): (0, "", ""),
                ("cherry", "main", "ready111"): (0, "+ ready111\n", ""),
                ("merge-tree", "--write-tree", "main", "ready111"): (0, "tree-ok\n", ""),
            },
        }
    )

    payload = collect_integration_reviews(
        codex_home=codex_home,
        run=fake_run,
        validation_run=_fake_validation(
            {
                cwd: {
                    _lint_command(): (0, "lint ok\n", ""),
                    _pytest_command(): (1, "1 failed, 7 passed\n", ""),
                },
            }
        ),
    )

    assert payload["summary"]["ready_to_integrate"] == 0
    assert payload["summary"]["needs_review"] == 1
    item = payload["groups"]["needs_review"][0]
    assert item["record_id"] == "managed-ready"
    assert item["validation"]["status"] == "failed"
    assert item["validation"]["commands"][0]["name"] == "lint"
    assert item["validation"]["commands"][0]["status"] == "passed"
    assert item["validation"]["commands"][1]["name"] == "unit_tests"
    assert item["validation"]["commands"][1]["status"] == "failed"
    assert "pytest tests/isotope -q failed" in item["reasons"]
    assert item["reason"] == "worker 已完成但 lint/test 未通过；修复后才能进入 ready_to_integrate。"

    plain = render_integration_review_plain(payload)
    assert "ready_to_integrate：0" in plain
    assert "needs_review：1" in plain
    assert "validation：failed" in plain
    assert "unit_tests failed rc=1" in plain


def test_supervisor_integration_review_uses_make_lint_when_available(tmp_path):
    from isotope.features.supervisor.integration_review import collect_integration_reviews

    codex_home = tmp_path / ".codex"
    cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "ready-make-lint"
    cwd.mkdir(parents=True)
    (cwd / "Makefile").write_text("lint:\n\tpython -m compileall -q src tests\n", encoding="utf-8")
    _write_done_record(codex_home, record_id="managed-ready", name="ready", cwd=cwd)

    payload = collect_integration_reviews(
        codex_home=codex_home,
        run=_fake_git(
            {
                cwd: {
                    ("rev-parse", "--abbrev-ref", "HEAD"): (0, "supervisor/ready-make-lint\n", ""),
                    ("rev-parse", "HEAD"): (0, "ready111\n", ""),
                    ("rev-parse", "main"): (0, "main999\n", ""),
                    ("status", "--short"): (0, "", ""),
                    ("merge-base", "--is-ancestor", "ready111", "main"): (1, "", ""),
                    ("merge-base", "--is-ancestor", "main", "ready111"): (0, "", ""),
                    ("cherry", "main", "ready111"): (0, "+ ready111\n", ""),
                    ("merge-tree", "--write-tree", "main", "ready111"): (0, "tree-ok\n", ""),
                },
            }
        ),
        validation_run=_fake_validation(
            {
                cwd: {
                    ("make", "lint"): (0, "lint ok\n", ""),
                    _pytest_command(): (0, "12 passed\n", ""),
                },
            }
        ),
    )

    item = payload["groups"]["ready_to_integrate"][0]
    assert item["validation"]["commands"][0]["display"] == "make lint"


def test_supervisor_integration_review_treats_cherry_picked_worker_as_integrated(tmp_path):
    from isotope.features.supervisor.integration_review import collect_integration_reviews

    codex_home = tmp_path / ".codex"
    picked_cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "picked-12345678"
    picked_cwd.mkdir(parents=True)
    _write_done_record(
        codex_home,
        record_id="managed-picked",
        name="picked",
        cwd=picked_cwd,
    )

    fake_run = _fake_git(
        {
            picked_cwd: {
                ("rev-parse", "--abbrev-ref", "HEAD"): (0, "supervisor/picked-12345678\n", ""),
                ("rev-parse", "HEAD"): (0, "picked111\n", ""),
                ("rev-parse", "main"): (0, "main999\n", ""),
                ("status", "--short"): (0, "", ""),
                ("merge-base", "--is-ancestor", "picked111", "main"): (1, "", ""),
                ("merge-base", "--is-ancestor", "main", "picked111"): (0, "", ""),
                ("cherry", "main", "picked111"): (0, "- picked111\n", ""),
                ("merge-tree", "--write-tree", "main", "picked111"): (0, "tree-ok\n", ""),
            },
        }
    )

    payload = collect_integration_reviews(codex_home=codex_home, run=fake_run)

    assert payload["summary"]["ready_to_integrate"] == 0
    assert payload["summary"]["already_integrated"] == 1
    item = payload["groups"]["already_integrated"][0]
    assert item["record_id"] == "managed-picked"
    assert item["main_contains_worker"] is False
    assert item["main_has_worker_patch"] is True
    assert item["reason"] == "main 已包含 worker 等价补丁；可检查后归档。"


def test_supervisor_integration_review_flags_dirty_and_unfinished_workers(tmp_path):
    from isotope.features.supervisor.integration_review import collect_integration_reviews

    codex_home = tmp_path / ".codex"
    dirty_cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "dirty-12345678"
    blocked_cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "blocked-12345678"
    dirty_cwd.mkdir(parents=True)
    blocked_cwd.mkdir(parents=True)
    _write_done_record(codex_home, record_id="managed-dirty", name="dirty", cwd=dirty_cwd)
    _write_record(
        codex_home,
        record_id="managed-blocked",
        name="blocked",
        cwd=blocked_cwd,
        protocol_status="blocked",
    )

    fake_run = _fake_git(
        {
            dirty_cwd: {
                ("rev-parse", "--abbrev-ref", "HEAD"): (0, "supervisor/dirty-12345678\n", ""),
                ("rev-parse", "HEAD"): (0, "dirty111\n", ""),
                ("rev-parse", "main"): (0, "main999\n", ""),
                ("status", "--short"): (0, " M src/isotope/features/supervisor/runner.py\n", ""),
                ("merge-base", "--is-ancestor", "dirty111", "main"): (1, "", ""),
                ("merge-base", "--is-ancestor", "main", "dirty111"): (0, "", ""),
                ("merge-tree", "--write-tree", "main", "dirty111"): (0, "tree-ok\n", ""),
            },
            blocked_cwd: {
                ("rev-parse", "--abbrev-ref", "HEAD"): (0, "supervisor/blocked-12345678\n", ""),
                ("rev-parse", "HEAD"): (0, "blocked111\n", ""),
                ("rev-parse", "main"): (0, "main999\n", ""),
                ("status", "--short"): (0, "", ""),
                ("merge-base", "--is-ancestor", "blocked111", "main"): (1, "", ""),
                ("merge-base", "--is-ancestor", "main", "blocked111"): (0, "", ""),
                ("merge-tree", "--write-tree", "main", "blocked111"): (0, "tree-ok\n", ""),
            },
        }
    )

    payload = collect_integration_reviews(
        codex_home=codex_home,
        include_unfinished=True,
        run=fake_run,
    )

    assert payload["summary"]["needs_review"] == 2
    reasons = {item["record_id"]: item["reason"] for item in payload["groups"]["needs_review"]}
    assert reasons["managed-dirty"] == "worker worktree 仍有未提交改动；先复查并要求 worker 提交。"
    assert reasons["managed-blocked"] == "worker 未汇报 done；先按 SUPERVISOR_NEXT 继续或拆分。"


def test_supervisor_integration_review_groups_merge_workers_separately(tmp_path):
    from isotope.features.supervisor.integration_review import (
        collect_integration_reviews,
        render_integration_review_plain,
    )

    codex_home = tmp_path / ".codex"
    dispatch_cwd = (
        tmp_path / "repo" / ".worktrees" / "supervisor" / "supervisor-merge-dispatch"
    )
    sourced_cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "merge-source"
    dispatch_cwd.mkdir(parents=True)
    sourced_cwd.mkdir(parents=True)
    _write_record(
        codex_home,
        record_id="managed-dispatch",
        name="supervisor-merge-dispatch",
        cwd=dispatch_cwd,
        protocol_status="working",
    )
    _write_record(
        codex_home,
        record_id="managed-source",
        name="custom-merge-worker",
        cwd=sourced_cwd,
        protocol_status="working",
        prompt="WORK ORDER\nsource=integration_review\nmerge ready workers",
    )

    fake_run = _fake_git(
        {
            dispatch_cwd: {
                ("rev-parse", "--abbrev-ref", "HEAD"): (0, "supervisor/supervisor-merge-dispatch\n", ""),
                ("rev-parse", "HEAD"): (0, "dispatch111\n", ""),
                ("rev-parse", "main"): (0, "main999\n", ""),
                ("status", "--short"): (0, "", ""),
                ("merge-base", "--is-ancestor", "dispatch111", "main"): (1, "", ""),
                ("merge-base", "--is-ancestor", "main", "dispatch111"): (0, "", ""),
                ("merge-tree", "--write-tree", "main", "dispatch111"): (0, "tree-ok\n", ""),
            },
            sourced_cwd: {
                ("rev-parse", "--abbrev-ref", "HEAD"): (0, "supervisor/merge-source\n", ""),
                ("rev-parse", "HEAD"): (0, "source111\n", ""),
                ("rev-parse", "main"): (0, "main999\n", ""),
                ("status", "--short"): (0, "", ""),
                ("merge-base", "--is-ancestor", "source111", "main"): (1, "", ""),
                ("merge-base", "--is-ancestor", "main", "source111"): (0, "", ""),
                ("merge-tree", "--write-tree", "main", "source111"): (0, "tree-ok\n", ""),
            },
        }
    )

    payload = collect_integration_reviews(codex_home=codex_home, run=fake_run)

    assert payload["summary"]["total"] == 2
    assert payload["include_unfinished"] is False
    assert payload["summary"]["merge_workers"] == 2
    assert payload["summary"]["ready_to_integrate"] == 0
    assert payload["summary"]["needs_review"] == 0
    assert [item["record_id"] for item in payload["groups"]["merge_workers"]] == [
        "managed-dispatch",
        "managed-source",
    ]
    assert payload["groups"]["merge_workers"][0]["merge_worker"] is True
    assert payload["groups"]["merge_workers"][1]["merge_worker_source"] == "integration_review"
    assert "merge_workers：2" in render_integration_review_plain(payload)


def test_supervisor_integration_review_defaults_to_done_unarchived_workers(tmp_path):
    from isotope.features.supervisor.integration_review import collect_integration_reviews

    codex_home = tmp_path / ".codex"
    done_cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "done-12345678"
    blocked_cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "blocked-12345678"
    archived_cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "archived-12345678"
    done_cwd.mkdir(parents=True)
    blocked_cwd.mkdir(parents=True)
    archived_cwd.mkdir(parents=True)
    _write_done_record(codex_home, record_id="managed-done", name="done", cwd=done_cwd)
    _write_record(
        codex_home,
        record_id="managed-blocked",
        name="blocked",
        cwd=blocked_cwd,
        protocol_status="blocked",
    )
    _write_done_record(
        codex_home,
        record_id="managed-archived",
        name="archived",
        cwd=archived_cwd,
        record_status="archived",
    )

    fake_run = _fake_git(
        {
            done_cwd: {
                ("rev-parse", "--abbrev-ref", "HEAD"): (0, "supervisor/done-12345678\n", ""),
                ("rev-parse", "HEAD"): (0, "done111\n", ""),
                ("rev-parse", "main"): (0, "main999\n", ""),
                ("status", "--short"): (0, "", ""),
                ("merge-base", "--is-ancestor", "done111", "main"): (1, "", ""),
                ("merge-base", "--is-ancestor", "main", "done111"): (0, "", ""),
                ("cherry", "main", "done111"): (0, "+ done111\n", ""),
                ("merge-tree", "--write-tree", "main", "done111"): (0, "tree-ok\n", ""),
            },
        }
    )

    payload = collect_integration_reviews(codex_home=codex_home, run=fake_run)

    assert payload["include_unfinished"] is False
    assert payload["summary"]["total"] == 1
    assert payload["workers"][0]["record_id"] == "managed-done"


def test_supervisor_integration_review_hides_missing_worktrees_by_default(tmp_path):
    from isotope.features.supervisor.integration_review import collect_integration_reviews

    codex_home = tmp_path / ".codex"
    missing_cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "missing-12345678"
    _write_done_record(
        codex_home,
        record_id="managed-missing",
        name="missing",
        cwd=missing_cwd,
    )

    payload = collect_integration_reviews(codex_home=codex_home)

    assert payload["summary"]["total"] == 0
    assert payload["summary"]["needs_review"] == 0
    assert payload["summary"]["stale_missing_worktrees"] == 1
    assert payload["stale_missing_worktrees"][0]["record_id"] == "managed-missing"


def test_supervisor_integration_review_can_include_missing_worktrees(tmp_path):
    from isotope.features.supervisor.integration_review import collect_integration_reviews

    codex_home = tmp_path / ".codex"
    missing_cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "missing-12345678"
    _write_done_record(
        codex_home,
        record_id="managed-missing",
        name="missing",
        cwd=missing_cwd,
    )

    payload = collect_integration_reviews(
        codex_home=codex_home,
        include_missing_worktrees=True,
    )

    assert payload["summary"]["total"] == 1
    assert payload["summary"]["needs_review"] == 1
    assert payload["summary"]["stale_missing_worktrees"] == 1
    assert payload["groups"]["needs_review"][0]["reason"] == (
        "worker worktree 缺失；先确认登记表和分支是否仍存在。"
    )


def test_supervisor_integration_review_flags_merge_conflict_risk(tmp_path):
    from isotope.features.supervisor.integration_review import collect_integration_reviews

    codex_home = tmp_path / ".codex"
    conflict_cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "conflict-12345678"
    conflict_cwd.mkdir(parents=True)
    _write_done_record(
        codex_home,
        record_id="managed-conflict",
        name="conflict",
        cwd=conflict_cwd,
    )

    fake_run = _fake_git(
        {
            conflict_cwd: {
                ("rev-parse", "--abbrev-ref", "HEAD"): (0, "supervisor/conflict-12345678\n", ""),
                ("rev-parse", "HEAD"): (0, "conflict111\n", ""),
                ("rev-parse", "main"): (0, "main999\n", ""),
                ("status", "--short"): (0, "", ""),
                ("merge-base", "--is-ancestor", "conflict111", "main"): (1, "", ""),
                ("merge-base", "--is-ancestor", "main", "conflict111"): (1, "", ""),
                ("cherry", "main", "conflict111"): (0, "+ conflict111\n", ""),
                ("merge-tree", "--write-tree", "main", "conflict111"): (
                    1,
                    "",
                    "CONFLICT (content): Merge conflict in src/example.py\n",
                ),
            },
        }
    )

    payload = collect_integration_reviews(codex_home=codex_home, run=fake_run)

    assert payload["summary"]["conflict_risk"] == 1
    item = payload["groups"]["conflict_risk"][0]
    assert item["record_id"] == "managed-conflict"
    assert item["merge_conflict"] is True
    assert item["reason"] == "只读 merge-tree 检测到 conflict；需要人工 rebase/merge 处理。"
    assert "CONFLICT (content)" in item["merge_check"]["stderr"]


def test_supervisor_integration_review_cli_json(tmp_path, capsys, monkeypatch):
    codex_home = tmp_path / ".codex"
    cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "ready-12345678"
    cwd.mkdir(parents=True)
    _write_done_record(codex_home, record_id="managed-ready", name="ready", cwd=cwd)
    monkeypatch.setattr(
        "isotope.features.supervisor.integration_review.subprocess.run",
        _fake_git(
            {
                cwd: {
                    ("rev-parse", "--abbrev-ref", "HEAD"): (0, "supervisor/ready-12345678\n", ""),
                    ("rev-parse", "HEAD"): (0, "ready111\n", ""),
                    ("rev-parse", "main"): (0, "main999\n", ""),
                    ("status", "--short"): (0, "", ""),
                    ("merge-base", "--is-ancestor", "ready111", "main"): (1, "", ""),
                    ("merge-base", "--is-ancestor", "main", "ready111"): (0, "", ""),
                    ("cherry", "main", "ready111"): (0, "+ ready111\n", ""),
                    ("merge-tree", "--write-tree", "main", "ready111"): (0, "tree-ok\n", ""),
                    _lint_command(): (0, "lint ok\n", ""),
                    _pytest_command(): (0, "12 passed\n", ""),
                }
            }
        ),
    )

    exit_code = supervisor_main(
        ["integration-review", "--codex-home", str(codex_home), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["ready_to_integrate"] == 1
    assert payload["groups"]["ready_to_integrate"][0]["record_id"] == "managed-ready"


def test_supervisor_integration_review_cli_posts_webhook_for_passing_done_worker(
    tmp_path,
    capsys,
    monkeypatch,
):
    import isotope.features.supervisor.runner as runner

    payloads: list[dict[str, object]] = []

    def fake_collect(**_kwargs):
        return {
            "status": "ok",
            "summary": {
                "total": 1,
                "ready_to_integrate": 1,
                "already_integrated": 0,
                "needs_review": 0,
                "conflict_risk": 0,
            },
            "groups": {
                "ready_to_integrate": [
                    {
                        "record_id": "managed-ready",
                        "name": "raw_content=secret",
                        "supervisor_protocol": {"status": "done"},
                        "group": "ready_to_integrate",
                    }
                ],
                "already_integrated": [],
                "needs_review": [],
                "conflict_risk": [],
            },
            "workers": [],
        }

    def fake_urlopen(request, timeout):
        payloads.append(json.loads(request.data.decode("utf-8")))

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b"ok"

        return Response()

    monkeypatch.setattr(runner, "collect_integration_reviews", fake_collect)
    monkeypatch.setattr(
        "isotope.features.supervisor.notifications.urllib.request.urlopen",
        fake_urlopen,
    )

    exit_code = supervisor_main(
        [
            "integration-review",
            "--codex-home",
            str(tmp_path / ".codex"),
            "--webhook-url",
            "https://example.test/supervisor",
            "--json",
        ]
    )

    assert exit_code == 0
    capsys.readouterr()
    assert payloads == [
        {
            "event_type": "supervisor_worker_integration_review",
            "source_ref": {
                "ref_type": "supervisor_worker_integration_review",
                "record_id": "managed-ready",
                "status": "done",
                "group": "ready_to_integrate",
            },
        }
    ]
    assert "raw_content=secret" not in json.dumps(payloads, ensure_ascii=False)


def _fake_git(
    responses: dict[Path, dict[tuple[str, ...], tuple[int, str, str]]],
):
    def fake_run(
        command: list[str],
        **kwargs,
    ) -> subprocess.CompletedProcess[str]:
        check = kwargs["check"]
        text = kwargs["text"]
        capture_output = kwargs["capture_output"]
        assert check is False
        assert text is True
        assert capture_output is True
        if _is_pytest_gate_command(command):
            assert Path(kwargs["cwd"]) in responses
            assert "src" in kwargs["env"]["PYTHONPATH"].split(":")
            return subprocess.CompletedProcess(command, 0, "12 passed in 0.34s\n", "")
        if command[:2] == ["git", "-C"]:
            worktree = Path(command[2])
            args = tuple(command[3:])
        else:
            cwd = kwargs.get("cwd")
            assert cwd is not None
            worktree = Path(cwd)
            args = tuple(command)
        try:
            returncode, stdout, stderr = responses[worktree][args]
        except KeyError as exc:
            raise AssertionError(f"unexpected command: {command}") from exc
        return subprocess.CompletedProcess(command, returncode, stdout, stderr)

    return fake_run


def _fake_validation(
    responses: dict[Path, dict[tuple[str, ...], tuple[int, str, str]]],
):
    def fake_run(
        command: list[str],
        *,
        cwd: str | Path,
        check: bool,
        text: bool,
        capture_output: bool,
        **_kwargs,
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        assert text is True
        assert capture_output is True
        worktree = Path(cwd)
        args = tuple(command)
        try:
            returncode, stdout, stderr = responses[worktree][args]
        except KeyError as exc:
            raise AssertionError(f"unexpected validation command: {command}") from exc
        return subprocess.CompletedProcess(command, returncode, stdout, stderr)

    return fake_run


def _lint_command() -> tuple[str, ...]:
    return (sys.executable, "-m", "compileall", "-q", "src/isotope", "tests/isotope")


def _pytest_command() -> tuple[str, ...]:
    return (sys.executable, "-m", "pytest", "tests/isotope", "-q")


def _is_pytest_gate_command(command: list[str]) -> bool:
    return (
        command[1:] == ["-m", "pytest", "tests/isotope", "-q"]
        and command[0] in {".venv/bin/python", sys.executable}
    )


def _write_done_record(
    codex_home: Path,
    *,
    record_id: str,
    name: str,
    cwd: Path,
    record_status: str = "launched",
) -> None:
    _write_record(
        codex_home,
        record_id=record_id,
        name=name,
        cwd=cwd,
        protocol_status="done",
        record_status=record_status,
    )


def _write_record(
    codex_home: Path,
    *,
    record_id: str,
    name: str,
    cwd: Path,
    protocol_status: str,
    record_status: str = "launched",
    prompt: str | None = None,
) -> None:
    log_path = codex_home / "supervisor" / "logs" / f"{record_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(
            [
                f"SUPERVISOR_STATUS: {protocol_status}",
                f"SUPERVISOR_SUMMARY: {name} summary",
                "SUPERVISOR_NEXT: 等待 Supervisor 归档",
            ]
        ),
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with registry_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "record_id": record_id,
                    "name": name,
                    "cwd": str(cwd),
                    "prompt": prompt or f"review {name}",
                    "command": ["codex", "exec", "-C", str(cwd), "prompt"],
                    "pid": 0,
                    "started_at": "2026-05-20T12:00:00+00:00",
                    "log_path": str(log_path),
                    "status": record_status,
                    "backend": "process",
                    "tmux_session": None,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
