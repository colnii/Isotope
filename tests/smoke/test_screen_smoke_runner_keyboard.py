from isotope.features.screen import runner


def test_build_key_actions_use_control_action_schema():
    assert runner._build_key_press_action(key="Enter") == {
        "type": "key_press",
        "key": "Enter",
    }
    assert runner._build_key_down_action(key="Shift") == {
        "type": "key_down",
        "key": "Shift",
    }
    assert runner._build_key_up_action(key="Shift") == {
        "type": "key_up",
        "key": "Shift",
    }


def test_control_key_press_parser_accepts_key_argument():
    args = runner._build_parser().parse_args(
        [
            "control-key-press",
            "--root",
            "runtime-root",
            "--app",
            "notepad.exe",
            "--key",
            "Enter",
        ]
    )

    assert args.command == "control-key-press"
    assert args.key == "Enter"
    assert args.approve_execute is False


def test_control_key_down_parser_accepts_key_argument():
    args = runner._build_parser().parse_args(
        [
            "control-key-down",
            "--root",
            "runtime-root",
            "--app",
            "notepad.exe",
            "--key",
            "Shift",
        ]
    )

    assert args.command == "control-key-down"
    assert args.key == "Shift"
    assert args.approve_execute is False


def test_control_key_up_parser_accepts_key_argument():
    args = runner._build_parser().parse_args(
        [
            "control-key-up",
            "--root",
            "runtime-root",
            "--app",
            "notepad.exe",
            "--key",
            "Shift",
        ]
    )

    assert args.command == "control-key-up"
    assert args.key == "Shift"
    assert args.approve_execute is False
