from __future__ import annotations

import importlib
import inspect
import subprocess

from isotope.features.supervisor import tmux_discovery


def test_tmux_discovery_lives_in_adoption_module():
    adoption_module = importlib.import_module(
        "isotope.features.supervisor.adoption.tmux_discovery"
    )

    assert tmux_discovery.TmuxAdoptCandidate is adoption_module.TmuxAdoptCandidate
    assert tmux_discovery.discover_tmux_adopt_candidates is (
        adoption_module.discover_tmux_adopt_candidates
    )
    assert inspect.getsourcefile(tmux_discovery.discover_tmux_adopt_candidates) == (
        inspect.getsourcefile(adoption_module.discover_tmux_adopt_candidates)
    )


def test_tmux_discovery_keeps_codex_candidate_projection(tmp_path):
    def fake_run(command, **_kwargs):
        if command[:2] == ["tmux", "list-sessions"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="codex:1\t0\t1\nshell:1\t1\t2\n",
                stderr="",
            )
        if command[:2] == ["tmux", "capture-pane"] and command[4] == "codex:1":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="OpenAI Codex\nSUPERVISOR_STATUS: working\n",
                stderr="",
            )
        if command[:2] == ["tmux", "capture-pane"]:
            return subprocess.CompletedProcess(command, 0, stdout="plain shell\n", stderr="")
        if command[:2] == ["tmux", "display-message"]:
            return subprocess.CompletedProcess(command, 0, stdout=str(tmp_path), stderr="")
        raise AssertionError(f"unexpected command: {command}")

    candidates = tmux_discovery.discover_tmux_adopt_candidates(
        cwd=tmp_path,
        run=fake_run,
    )

    assert len(candidates) == 1
    assert candidates[0].tmux_session == "codex:1"
    assert candidates[0].suggested_name == "codex-1"
    assert candidates[0].cwd == str(tmp_path)
    assert candidates[0].looks_like_codex is True
    assert "isotope-supervisor adopt" in candidates[0].adopt_command
