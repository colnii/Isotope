import importlib
import inspect


def test_capability_runner_keeps_cli_entrypoint_in_cli_module():
    runner = importlib.import_module("isotope.capabilities.runner")
    cli = importlib.import_module("isotope.capabilities.runner_cli")

    assert runner.main is cli.main
    assert runner._build_parser is cli._build_parser
    assert runner._json_object_argument is cli._json_object_argument
    assert inspect.getsourcefile(cli.main) == inspect.getsourcefile(
        cli._build_parser
    )

