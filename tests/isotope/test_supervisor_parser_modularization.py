from __future__ import annotations

import argparse
import importlib
import inspect

from isotope.features.supervisor.commands import parser as parser_module


def _top_level_command_names(parser: argparse.ArgumentParser) -> set[str]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    raise AssertionError("parser has no top-level subparsers")


def test_supervisor_parser_delegates_memory_commands_to_memory_parser_module():
    memory_parser_module = importlib.import_module(
        "isotope.features.supervisor.commands.parser_memory"
    )

    assert (
        parser_module.add_memory_command_parsers
        is memory_parser_module.add_memory_command_parsers
    )

    built_parser = parser_module.build_parser()
    assert {"memory", "worker-event", "worker-manager"} <= _top_level_command_names(
        built_parser
    )

    source = inspect.getsource(parser_module._build_parser_impl)
    for command in ("memory", "worker-event", "worker-manager"):
        assert f'"{command}"' not in source


def test_supervisor_parser_delegates_daemon_command_to_daemon_parser_module():
    daemon_parser_module = importlib.import_module(
        "isotope.features.supervisor.commands.parser_daemon"
    )

    assert (
        parser_module.add_daemon_command_parser
        is daemon_parser_module.add_daemon_command_parser
    )

    built_parser = parser_module.build_parser()
    assert "daemon" in _top_level_command_names(built_parser)

    daemon_start = built_parser.parse_args(
        [
            "daemon",
            "start",
            "--goal-low-water",
            "1",
            "--webhook-url",
            "http://127.0.0.1/hook",
        ]
    )
    assert daemon_start.command == "daemon"
    assert daemon_start.daemon_command == "start"
    assert daemon_start.goal_low_water == 1
    assert daemon_start.webhook_url == "http://127.0.0.1/hook"

    watcher_run = built_parser.parse_args(["daemon", "watcher", "run", "--iterations", "2"])
    assert watcher_run.daemon_command == "watcher"
    assert watcher_run.watcher_command == "run"
    assert watcher_run.iterations == 2

    source = inspect.getsource(parser_module._build_parser_impl)
    assert '"daemon"' not in source
    assert '"watcher"' not in source


def test_supervisor_parser_delegates_loop_commands_to_loop_parser_module():
    loop_parser_module = importlib.import_module(
        "isotope.features.supervisor.commands.parser_loop"
    )

    assert (
        parser_module.add_loop_command_parsers
        is loop_parser_module.add_loop_command_parsers
    )

    built_parser = parser_module.build_parser()
    assert {"loop", "up"} <= _top_level_command_names(built_parser)

    loop_args = built_parser.parse_args(
        [
            "loop",
            "--goal-low-water",
            "2",
            "--webhook-url",
            "http://127.0.0.1/hook",
            "--no-auto-adopt",
            "--merge-dispatch-execute",
        ]
    )
    assert loop_args.command == "loop"
    assert loop_args.goal_low_water == 2
    assert loop_args.webhook_url == "http://127.0.0.1/hook"
    assert loop_args.auto_adopt is False
    assert loop_args.merge_dispatch_execute is True

    up_args = built_parser.parse_args(
        [
            "up",
            "--max-fanout-launches",
            "4",
            "--auto-merge-promote",
        ]
    )
    assert up_args.command == "up"
    assert up_args.max_fanout_launches == 4
    assert up_args.auto_merge_promote is True

    source = inspect.getsource(parser_module._build_parser_impl)
    assert '"loop"' not in source
    assert '"up"' not in source
