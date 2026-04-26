import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.actions import (
    Action,
    ActionValidationError,
    Point,
    actions_match,
    ensure_within_display,
)


class ActionValidationTests(unittest.TestCase):
    def test_click_with_coordinates_succeeds(self) -> None:
        action = Action(type="click", x=10, y=10)

        self.assertEqual(action.type, "click")
        self.assertEqual(action.x, 10)
        self.assertEqual(action.y, 10)

    def test_click_without_coordinates_raises(self) -> None:
        with self.assertRaises(ValidationError):
            Action(type="click")

        with self.assertRaises(ValidationError):
            Action(type="click", x=10)

        with self.assertRaises(ValidationError):
            Action(type="click", y=10)

    def test_drag_requires_path_with_two_points(self) -> None:
        with self.assertRaises(ValidationError):
            Action(type="drag")

        with self.assertRaises(ValidationError):
            Action(type="drag", path=[Point(x=0, y=0)])

        action = Action(
            type="drag",
            path=[Point(x=0, y=0), Point(x=10, y=10)],
        )
        self.assertEqual(len(action.path or []), 2)

    def test_type_requires_non_empty_text(self) -> None:
        with self.assertRaises(ValidationError):
            Action(type="type")

        with self.assertRaises(ValidationError):
            Action(type="type", text="")

        action = Action(type="type", text="hello")
        self.assertEqual(action.text, "hello")

    def test_keypress_requires_non_empty_keys(self) -> None:
        with self.assertRaises(ValidationError):
            Action(type="keypress")

        with self.assertRaises(ValidationError):
            Action(type="keypress", keys=[])

        action = Action(type="keypress", keys=["Return"])
        self.assertEqual(action.keys, ["Return"])

    def test_wait_requires_duration_ms(self) -> None:
        with self.assertRaises(ValidationError):
            Action(type="wait")

        action = Action(type="wait", duration_ms=500)
        self.assertEqual(action.duration_ms, 500)

    def test_scroll_requires_at_least_one_axis(self) -> None:
        with self.assertRaises(ValidationError):
            # scroll has POINT_ACTIONS membership, so x/y are required AND axis is required.
            Action(type="scroll", x=0, y=0)

        action = Action(type="scroll", x=0, y=0, scroll_y=1)
        self.assertEqual(action.scroll_y, 1)

        action_x = Action(type="scroll", x=0, y=0, scroll_x=2)
        self.assertEqual(action_x.scroll_x, 2)


class EnsureWithinDisplayTests(unittest.TestCase):
    def test_in_bounds_point_passes(self) -> None:
        action = Action(type="click", x=10, y=10)
        # Should not raise.
        ensure_within_display(action, width=100, height=100)

    def test_out_of_bounds_x_raises(self) -> None:
        action = Action(type="click", x=200, y=10)
        with self.assertRaises(ActionValidationError):
            ensure_within_display(action, width=100, height=100)

    def test_out_of_bounds_y_raises(self) -> None:
        action = Action(type="click", x=10, y=999)
        with self.assertRaises(ActionValidationError):
            ensure_within_display(action, width=100, height=100)

    def test_drag_path_out_of_bounds_raises(self) -> None:
        action = Action(
            type="drag",
            path=[Point(x=0, y=0), Point(x=200, y=10)],
        )
        with self.assertRaises(ActionValidationError):
            ensure_within_display(action, width=100, height=100)

    def test_drag_path_in_bounds_passes(self) -> None:
        action = Action(
            type="drag",
            path=[Point(x=0, y=0), Point(x=50, y=50)],
        )
        # Should not raise.
        ensure_within_display(action, width=100, height=100)


class ActionsMatchTests(unittest.TestCase):
    def test_returns_true_for_identical_actions(self) -> None:
        a = Action(type="click", x=10, y=10, button="left")
        b = Action(type="click", x=10, y=10, button="left")

        self.assertTrue(actions_match(a, b))

    def test_returns_false_when_x_differs(self) -> None:
        a = Action(type="click", x=10, y=10)
        b = Action(type="click", x=20, y=10)

        self.assertFalse(actions_match(a, b))

    def test_returns_false_when_type_differs(self) -> None:
        a = Action(type="click", x=10, y=10)
        b = Action(type="move", x=10, y=10)

        self.assertFalse(actions_match(a, b))

    def test_returns_false_when_text_differs(self) -> None:
        a = Action(type="type", text="hello")
        b = Action(type="type", text="world")

        self.assertFalse(actions_match(a, b))


if __name__ == "__main__":
    unittest.main()
