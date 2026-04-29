import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.normalize import normalize_action, normalize_actions
from app.schemas.actions import Action


class NormalizeActionTests(unittest.TestCase):
    def test_drops_null_fields_and_returns_action(self) -> None:
        action = normalize_action(
            {
                "type": "click",
                "x": 10,
                "y": 10,
                "button": None,
                "text": None,
                "keys": None,
            }
        )

        self.assertIsInstance(action, Action)
        self.assertEqual(action.type, "click")
        self.assertEqual(action.x, 10)
        self.assertEqual(action.y, 10)
        self.assertIsNone(action.button)

    def test_wait_default_duration_ms_is_500(self) -> None:
        action = normalize_action({"type": "wait"})

        self.assertEqual(action.type, "wait")
        self.assertEqual(action.duration_ms, 500)

    def test_wait_explicit_duration_ms_is_preserved(self) -> None:
        action = normalize_action({"type": "wait", "duration_ms": 1234})

        self.assertEqual(action.duration_ms, 1234)

    def test_scroll_default_scroll_y_is_one(self) -> None:
        action = normalize_action({"type": "scroll", "x": 0, "y": 0})

        self.assertEqual(action.type, "scroll")
        self.assertEqual(action.scroll_y, 1)
        self.assertIsNone(action.scroll_x)

    def test_scroll_explicit_scroll_x_kept_no_default(self) -> None:
        action = normalize_action({"type": "scroll", "x": 0, "y": 0, "scroll_x": 5})

        self.assertEqual(action.scroll_x, 5)
        # The default is only applied when neither axis was provided.
        self.assertIsNone(action.scroll_y)

    def test_invalid_raw_raises_value_error_not_validation_error(self) -> None:
        # 'click' requires x/y; the absence triggers Action validation.
        # normalize_action calls Action(**...) directly, which raises
        # pydantic ValidationError. normalize_actions wraps it as ValueError.
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            normalize_action({"type": "click"})

    def test_normalize_actions_wraps_validation_error_in_value_error(self) -> None:
        with self.assertRaises(ValueError) as cm:
            normalize_actions([{"type": "click"}])

        # Must NOT be a ValidationError specifically; it should be plain ValueError
        # raised from `raise ValueError(...) from exc`.
        from pydantic import ValidationError

        self.assertNotIsInstance(cm.exception, ValidationError)
        self.assertIn("invalid computer action", str(cm.exception))

    def test_normalize_actions_returns_list_in_order(self) -> None:
        actions = normalize_actions(
            [
                {"type": "screenshot"},
                {"type": "wait"},
                {"type": "click", "x": 1, "y": 2},
            ]
        )

        self.assertEqual(len(actions), 3)
        self.assertEqual([a.type for a in actions], ["screenshot", "wait", "click"])

    def test_duplicate_left_click_pair_compacts_to_double_click(self) -> None:
        actions = normalize_actions(
            [
                {"type": "click", "x": 37, "y": 282},
                {"type": "click", "x": 37, "y": 282},
                {"type": "wait", "duration_ms": 1000},
            ]
        )

        self.assertEqual([a.type for a in actions], ["double_click", "wait"])
        self.assertEqual(actions[0].x, 37)
        self.assertEqual(actions[0].y, 282)

    def test_different_clicks_are_not_compacted(self) -> None:
        actions = normalize_actions(
            [
                {"type": "click", "x": 37, "y": 282},
                {"type": "click", "x": 72, "y": 304},
            ]
        )

        self.assertEqual([a.type for a in actions], ["click", "click"])

    def test_duplicate_double_click_compacts_to_one_action(self) -> None:
        actions = normalize_actions(
            [
                {"type": "double_click", "x": 72, "y": 304},
                {"type": "double_click", "x": 72, "y": 304},
            ]
        )

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].type, "double_click")
        self.assertEqual(actions[0].x, 72)
        self.assertEqual(actions[0].y, 304)

    def test_duplicate_type_and_keypress_compact_to_one_action(self) -> None:
        actions = normalize_actions(
            [
                {"type": "type", "text": "https://example.com"},
                {"type": "type", "text": "https://example.com"},
                {"type": "keypress", "keys": ["Return"]},
                {"type": "keypress", "keys": ["Return"]},
            ]
        )

        self.assertEqual([a.type for a in actions], ["type", "keypress"])
        self.assertEqual(actions[0].text, "https://example.com")
        self.assertEqual(actions[1].keys, ["Return"])

    def test_panel_double_click_downgrades_to_single_click(self) -> None:
        actions = normalize_actions(
            [{"type": "double_click", "x": 985, "y": 1053}],
            display_width=1920,
            display_height=1080,
        )

        self.assertEqual(actions[0].type, "click")
        self.assertEqual(actions[0].x, 985)
        self.assertEqual(actions[0].y, 1053)

    def test_url_type_appends_return_when_missing(self) -> None:
        actions = normalize_actions([{"type": "type", "text": "https://example.com"}])

        self.assertEqual([a.type for a in actions], ["type", "keypress"])
        self.assertEqual(actions[1].keys, ["Return"])

    def test_url_type_does_not_append_duplicate_return(self) -> None:
        actions = normalize_actions(
            [
                {"type": "type", "text": "https://example.com"},
                {"type": "keypress", "keys": ["Return"]},
            ]
        )

        self.assertEqual([a.type for a in actions], ["type", "keypress"])
        self.assertEqual(actions[1].keys, ["Return"])

    def test_x_y_lists_collapse_to_midpoint(self) -> None:
        action = normalize_action({"type": "click", "x": [400, 600], "y": [300, 700]})

        self.assertEqual(action.x, 500)
        self.assertEqual(action.y, 500)

    def test_bbox_box_field_yields_center(self) -> None:
        action = normalize_action({"type": "click", "box": [100, 200, 300, 400]})

        self.assertEqual(action.x, 200)
        self.assertEqual(action.y, 300)

    def test_point_list_field_yields_x_y(self) -> None:
        action = normalize_action({"type": "click", "point": [42, 99]})

        self.assertEqual(action.x, 42)
        self.assertEqual(action.y, 99)

    def test_x_point_list_without_y_yields_x_y_for_any_point_action(self) -> None:
        action = normalize_action({"type": "double_click", "x": [37, 282]})

        self.assertEqual(action.x, 37)
        self.assertEqual(action.y, 282)

    def test_point_dict_field_yields_x_y(self) -> None:
        action = normalize_action({"type": "click", "position": {"x": 10, "y": 20}})

        self.assertEqual(action.x, 10)
        self.assertEqual(action.y, 20)

    def test_fractional_coords_scale_to_display(self) -> None:
        action = normalize_action(
            {"type": "click", "x": 0.5, "y": 0.25},
            display_width=1920,
            display_height=1080,
        )

        self.assertEqual(action.x, int(round(0.5 * 1919)))
        self.assertEqual(action.y, int(round(0.25 * 1079)))

    def test_string_keys_are_wrapped_in_list(self) -> None:
        action = normalize_action({"type": "keypress", "keys": "Return"})

        self.assertEqual(action.keys, ["Return"])

    def test_button_string_lowercased(self) -> None:
        action = normalize_action({"type": "click", "x": 1, "y": 2, "button": "RIGHT"})

        self.assertEqual(action.button, "right")


if __name__ == "__main__":
    unittest.main()
