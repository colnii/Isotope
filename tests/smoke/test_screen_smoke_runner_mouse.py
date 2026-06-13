from isotope.features.screen import runner


def test_build_double_click_action_uses_control_action_schema():
    assert runner._build_double_click_action(x=100, y=120, button="left") == {
        "type": "double_click",
        "button": "left",
        "x": 100,
        "y": 120,
    }


def test_build_drag_action_uses_control_action_schema():
    assert runner._build_drag_action(
        x=100,
        y=120,
        to_x=180,
        to_y=220,
        button="left",
        duration_ms=250,
    ) == {
        "type": "drag",
        "button": "left",
        "x": 100,
        "y": 120,
        "to_x": 180,
        "to_y": 220,
        "duration_ms": 250,
    }


def test_control_double_click_parser_accepts_coordinate_arguments():
    args = runner._build_parser().parse_args(
        [
            "control-double-click",
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

    assert args.command == "control-double-click"
    assert args.button == "left"
    assert args.x == 100
    assert args.y == 120
    assert args.approve_execute is False


def test_control_drag_parser_accepts_start_and_end_coordinates():
    args = runner._build_parser().parse_args(
        [
            "control-drag",
            "--root",
            "runtime-root",
            "--app",
            "notepad.exe",
            "--x",
            "100",
            "--y",
            "120",
            "--to-x",
            "180",
            "--to-y",
            "220",
            "--duration-ms",
            "250",
        ]
    )

    assert args.command == "control-drag"
    assert args.button == "left"
    assert args.x == 100
    assert args.y == 120
    assert args.to_x == 180
    assert args.to_y == 220
    assert args.duration_ms == 250
    assert args.approve_execute is False
