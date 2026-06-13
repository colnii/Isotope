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
