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
