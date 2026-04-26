import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.sandbox.keymap import normalize_chord, normalize_key


class NormalizeKeyTests(unittest.TestCase):
    def test_cmd_maps_to_super(self) -> None:
        self.assertEqual(normalize_key("CMD"), "super")
        self.assertEqual(normalize_key("cmd"), "super")
        self.assertEqual(normalize_key("Command"), "super")

    def test_enter_maps_to_return(self) -> None:
        self.assertEqual(normalize_key("Enter"), "Return")
        self.assertEqual(normalize_key("enter"), "Return")

    def test_single_letter_passes_through(self) -> None:
        self.assertEqual(normalize_key("a"), "a")
        self.assertEqual(normalize_key("Z"), "Z")

    def test_function_keys_map_through_table(self) -> None:
        self.assertEqual(normalize_key("F5"), "F5")
        self.assertEqual(normalize_key("f5"), "F5")

    def test_empty_key_raises(self) -> None:
        with self.assertRaises(ValueError):
            normalize_key("")

        with self.assertRaises(ValueError):
            normalize_key("   ")


class NormalizeChordTests(unittest.TestCase):
    def test_chord_joins_with_plus(self) -> None:
        self.assertEqual(
            normalize_chord(["ctrl", "shift", "t"]),
            "ctrl+shift+t",
        )

    def test_chord_normalizes_each_part(self) -> None:
        self.assertEqual(
            normalize_chord(["cmd", "Enter"]),
            "super+Return",
        )

    def test_empty_list_raises(self) -> None:
        with self.assertRaises(ValueError):
            normalize_chord([])


if __name__ == "__main__":
    unittest.main()
