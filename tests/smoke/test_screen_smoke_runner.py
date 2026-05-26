from __future__ import annotations

import json

import pytest

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
    assert any("real" in entry["control"] for entry in matrix)


def test_build_observe_intent_is_screen_observe():
    intent = runner._build_observe_intent(
        target_selector={
            "kind": "window",
            "selector": {"title_contains": "sample"},
        },
        capture=["metadata"],
        target_allowlist=None,
    )

    assert intent["action"] == "call_tool"
    assert intent["tool"] == "screen_observe"
    assert intent["capture"] == ["metadata"]


def test_build_observe_intent_can_carry_target_allowlist():
    intent = runner._build_observe_intent(
        target_selector={
            "kind": "window",
            "selector": {"title_contains": "sample"},
        },
        capture=["metadata"],
        target_allowlist={
            "allowed_apps": ["notepad.exe"],
            "allowed_title_contains": ["sample"],
        },
    )

    assert intent["target_allowlist"] == {
        "allowed_apps": ["notepad.exe"],
        "allowed_title_contains": ["sample"],
    }


def test_target_allowlist_can_load_reusable_json_file(tmp_path):
    allowlist_file = tmp_path / "screen-allowlist.json"
    allowlist_file.write_text(
        json.dumps(
            {
                "allowed_apps": ["notepad.exe"],
                "allowed_title_contains": ["Mahjong Soul"],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    allowlist = runner._target_allowlist_from_args(
        allow_apps=["calc.exe"],
        allow_title_contains=["local"],
        allowlist_file=str(allowlist_file),
    )

    assert allowlist == {
        "allowed_apps": ["notepad.exe", "calc.exe"],
        "allowed_title_contains": ["Mahjong Soul", "local"],
        "allow_first_match_execute": False,
    }


def test_target_allowlist_can_load_named_profile(tmp_path):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    profile_file = profile_dir / "mahjong.json"
    profile_file.write_text(
        json.dumps(
            {
                "allowed_apps": ["msedge.exe"],
                "allowed_title_contains": ["Mahjong Soul"],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    allowlist = runner._target_allowlist_from_args(
        allow_apps=["obsidian.exe"],
        allow_title_contains=[],
        allowlist_file=None,
        allowlist_profile="mahjong",
        allowlist_profile_dir=str(profile_dir),
    )

    assert allowlist == {
        "allowed_apps": ["msedge.exe", "obsidian.exe"],
        "allowed_title_contains": ["Mahjong Soul"],
        "allow_first_match_execute": False,
    }


def test_target_allowlist_profile_rejects_path_like_names(tmp_path):
    with pytest.raises(ValueError, match="allowlist-profile must be a simple name"):
        runner._target_allowlist_from_args(
            allow_apps=[],
            allow_title_contains=[],
            allowlist_file=None,
            allowlist_profile="../mahjong",
            allowlist_profile_dir=str(tmp_path),
        )


def test_validate_target_allowlist_file_returns_low_sensitive_summary(tmp_path):
    allowlist_file = tmp_path / "screen-allowlist.json"
    allowlist_file.write_text(
        json.dumps(
            {
                "allowed_apps": ["notepad.exe", "calc.exe"],
                "allowed_title_contains": ["Mahjong Soul"],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    result = runner.validate_target_allowlist_file(str(allowlist_file))

    assert result == {
        "status": "ok",
        "path": str(allowlist_file),
        "allowed_app_count": 2,
        "allowed_title_contains_count": 1,
        "allow_first_match_execute": False,
    }


def test_validate_target_allowlist_profile_resolves_named_profile(tmp_path):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    profile_file = profile_dir / "mahjong.json"
    profile_file.write_text(
        json.dumps(
            {
                "allowed_apps": ["msedge.exe"],
                "allowed_title_contains": ["Mahjong Soul"],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    result = runner.validate_target_allowlist_profile(
        profile="mahjong",
        profile_dir=str(profile_dir),
    )

    assert result == {
        "status": "ok",
        "profile": "mahjong",
        "path": str(profile_file),
        "allowed_app_count": 1,
        "allowed_title_contains_count": 1,
        "allow_first_match_execute": False,
    }


def test_validate_target_allowlist_profile_rejects_path_like_names(tmp_path):
    with pytest.raises(ValueError, match="allowlist-profile must be a simple name"):
        runner.validate_target_allowlist_profile(
            profile="../mahjong",
            profile_dir=str(tmp_path),
        )


def test_list_target_allowlist_profiles_returns_low_sensitive_sorted_summary(tmp_path):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "mahjong.json").write_text(
        json.dumps(
            {
                "allowed_apps": ["msedge.exe"],
                "allowed_title_contains": ["Mahjong Soul"],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (profile_dir / "notes.json").write_text(
        json.dumps({"allowed_apps": ["notepad.exe"]}, sort_keys=True),
        encoding="utf-8",
    )

    result = runner.list_target_allowlist_profiles(str(profile_dir))

    assert result == {
        "status": "ok",
        "profile_dir": str(profile_dir),
        "profile_count": 2,
        "profiles": [
            {
                "profile": "mahjong",
                "path": str(profile_dir / "mahjong.json"),
                "allowed_app_count": 1,
                "allowed_title_contains_count": 1,
                "allow_first_match_execute": False,
            },
            {
                "profile": "notes",
                "path": str(profile_dir / "notes.json"),
                "allowed_app_count": 1,
                "allowed_title_contains_count": 0,
                "allow_first_match_execute": False,
            },
        ],
    }


def test_build_target_allowlist_template_returns_editable_json_shape():
    template = runner.build_target_allowlist_template()

    assert template == {
        "allowed_apps": ["notepad.exe"],
        "allowed_title_contains": ["Untitled - Notepad"],
    }
    assert "allow_first_match_execute" not in template


def test_build_click_action_uses_control_action_schema():
    assert runner._build_click_action(x=100, y=120, button="left") == {
        "type": "click",
        "button": "left",
        "x": 100,
        "y": 120,
    }


def test_build_restore_window_action_uses_control_action_schema():
    assert runner._build_restore_window_action() == {"type": "restore_window"}


def test_control_click_parser_accepts_coordinate_arguments():
    args = runner._build_parser().parse_args(
        [
            "control-click",
            "--root",
            "runtime-root",
            "--app",
            "notepad.exe",
            "--allow-app",
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
    assert args.allow_app == ["notepad.exe"]
    assert args.approve_execute is False


def test_control_restore_parser_accepts_target_allowlist():
    args = runner._build_parser().parse_args(
        [
            "control-restore",
            "--root",
            "runtime-root",
            "--app",
            "notepad.exe",
            "--allow-app",
            "notepad.exe",
        ]
    )

    assert args.command == "control-restore"
    assert args.allow_app == ["notepad.exe"]
    assert args.allowlist_file is None
    assert args.approve_execute is False


def test_observe_parser_accepts_reusable_allowlist_file():
    args = runner._build_parser().parse_args(
        [
            "observe",
            "--root",
            "runtime-root",
            "--app",
            "notepad.exe",
            "--allowlist-file",
            "screen-allowlist.json",
        ]
    )

    assert args.command == "observe"
    assert args.allowlist_file == "screen-allowlist.json"


def test_observe_parser_accepts_allowlist_profile():
    args = runner._build_parser().parse_args(
        [
            "observe",
            "--root",
            "runtime-root",
            "--app",
            "notepad.exe",
            "--allowlist-profile",
            "mahjong",
            "--allowlist-profile-dir",
            "profiles",
        ]
    )

    assert args.command == "observe"
    assert args.allowlist_profile == "mahjong"
    assert args.allowlist_profile_dir == "profiles"


def test_allowlist_validate_parser_accepts_path():
    args = runner._build_parser().parse_args(
        [
            "allowlist",
            "validate",
            "--path",
            "screen-allowlist.json",
            "--json",
        ]
    )

    assert args.command == "allowlist"
    assert args.allowlist_command == "validate"
    assert args.path == "screen-allowlist.json"
    assert args.json is True


def test_allowlist_validate_parser_accepts_profile():
    args = runner._build_parser().parse_args(
        [
            "allowlist",
            "validate",
            "--profile",
            "mahjong",
            "--profile-dir",
            "profiles",
            "--json",
        ]
    )

    assert args.command == "allowlist"
    assert args.allowlist_command == "validate"
    assert args.path is None
    assert args.profile == "mahjong"
    assert args.profile_dir == "profiles"
    assert args.json is True


def test_allowlist_template_parser_accepts_json_flag():
    args = runner._build_parser().parse_args(
        [
            "allowlist",
            "template",
            "--json",
        ]
    )

    assert args.command == "allowlist"
    assert args.allowlist_command == "template"
    assert args.json is True


def test_allowlist_list_parser_accepts_profile_dir():
    args = runner._build_parser().parse_args(
        [
            "allowlist",
            "list",
            "--profile-dir",
            "profiles",
            "--json",
        ]
    )

    assert args.command == "allowlist"
    assert args.allowlist_command == "list"
    assert args.profile_dir == "profiles"
    assert args.json is True


def test_real_smoke_plan_prints_real_backend_commands():
    commands = runner._real_smoke_commands(
        root="runtime-root",
        app="notepad.exe",
        title_contains=None,
    )

    assert any(" observe " in command and "--capture metadata" in command for command in commands)
    assert any(" control-click " in command for command in commands)
    assert any(" control-restore " in command for command in commands)
    assert all("fake" not in command for command in commands)


def test_real_smoke_plan_carries_reusable_allowlist_file():
    commands = runner._real_smoke_commands(
        root="runtime-root",
        app="notepad.exe",
        title_contains=None,
        allowlist_file="screen-allowlist.json",
    )

    assert all(
        "--allowlist-file screen-allowlist.json" in command for command in commands
    )


def test_real_smoke_plan_carries_allowlist_profile():
    commands = runner._real_smoke_commands(
        root="runtime-root",
        app="notepad.exe",
        title_contains=None,
        allowlist_file=None,
        allowlist_profile="mahjong",
        allowlist_profile_dir="profiles",
    )

    assert all("--allowlist-profile mahjong" in command for command in commands)
    assert all("--allowlist-profile-dir profiles" in command for command in commands)


def test_json_print_writes_serializable_payload(capsys):
    runner._print_json({"status": "ok"})

    out = capsys.readouterr().out
    assert json.loads(out) == {"status": "ok"}
