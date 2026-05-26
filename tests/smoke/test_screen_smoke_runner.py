from __future__ import annotations

import json

from isotope.features.screen import runner


def test_parse_target_selector_from_cli_args():
    selector = runner._target_selector_from_args(
        app="notepad.exe",
        title_contains=None,
        window_id=None,
    )

    assert selector == {
        "kind": "window",
        "selector": {"app": "notepad.exe"},
    }


def test_smoke_matrix_output_requires_non_unique_samples():
    matrix = runner._default_smoke_matrix()

    assert len(matrix) >= 3
    assert len({entry["category"] for entry in matrix}) >= 3


def test_build_observe_intent_is_screen_observe():
    intent = runner._build_observe_intent(
        target_selector={
            "kind": "window",
            "selector": {"title_contains": "sample"},
        },
        capture=["metadata"],
    )

    assert intent["action"] == "call_tool"
    assert intent["tool"] == "screen_observe"
    assert intent["capture"] == ["metadata"]


def test_build_click_action_uses_control_action_schema():
    assert runner._build_click_action(x=100, y=120, button="left") == {
        "type": "click",
        "button": "left",
        "x": 100,
        "y": 120,
    }


def test_control_click_parser_accepts_coordinate_arguments():
    args = runner._build_parser().parse_args(
        [
            "control-click",
            "--root",
            "runtime-root",
            "--app",
            "notepad.exe",
            "--x",
            "100",
            "--y",
            "120",
        ]
    )

    assert args.command == "control-click"
    assert args.button == "left"
    assert args.x == 100
    assert args.y == 120
    assert args.approve_execute is False


def test_json_print_writes_serializable_payload(capsys):
    runner._print_json({"status": "ok"})

    out = capsys.readouterr().out
    assert json.loads(out) == {"status": "ok"}
