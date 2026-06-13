import pytest

from isotope.execution.screen.backend_types import ScreenAction


def test_screen_action_accepts_double_click_and_drag_coordinates():
    double_click = ScreenAction.from_dict(
        {"type": "double_click", "button": "left", "x": 10, "y": 20, "duration_ms": 80}
    )
    drag = ScreenAction.from_dict(
        {
            "type": "drag",
            "button": "left",
            "x": 10,
            "y": 20,
            "to_x": 90,
            "to_y": 120,
            "duration_ms": 250,
        }
    )

    assert double_click.to_dict() == {
        "type": "double_click",
        "x": 10,
        "y": 20,
        "button": "left",
        "duration_ms": 80,
    }
    assert drag.to_dict() == {
        "type": "drag",
        "x": 10,
        "y": 20,
        "button": "left",
        "to_x": 90,
        "to_y": 120,
        "duration_ms": 250,
    }


def test_screen_action_accepts_keyboard_actions():
    key_down = ScreenAction.from_dict({"type": "key_down", "key": "Shift"})
    key_up = ScreenAction.from_dict({"type": "key_up", "key": "Shift"})
    key_press = ScreenAction.from_dict({"type": "key_press", "key": "Enter"})

    assert key_down.to_dict() == {"type": "key_down", "key": "Shift"}
    assert key_up.to_dict() == {"type": "key_up", "key": "Shift"}
    assert key_press.to_dict() == {"type": "key_press", "key": "Enter"}


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "double_click", "x": 10},
        {"type": "drag", "x": 10, "y": 20, "to_x": 90},
    ],
)
def test_screen_action_rejects_incomplete_mouse_coordinates(payload):
    with pytest.raises(ValueError, match="requires"):
        ScreenAction.from_dict(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "key_down"},
        {"type": "key_up"},
        {"type": "key_press"},
    ],
)
def test_screen_action_rejects_keyboard_actions_without_key(payload):
    with pytest.raises(ValueError, match="requires key"):
        ScreenAction.from_dict(payload)
