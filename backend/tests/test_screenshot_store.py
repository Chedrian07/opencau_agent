import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.storage.screenshot_store import ScreenshotStore


ONE_PIXEL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c63f8cfc0f01f0006000301010005bf24310000000049454e44ae426082"
)


class ScreenshotStoreTests(unittest.TestCase):
    def test_save_png_returns_url_hash_and_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ScreenshotStore(tmp)

            metadata = store.save_png("abc123", ONE_PIXEL_PNG)

            self.assertTrue(metadata.path.is_file())
            self.assertEqual(metadata.size_bytes, len(ONE_PIXEL_PNG))
            self.assertEqual(len(metadata.sha256), 64)
            self.assertIn("/api/sessions/abc123/screenshots/", metadata.url)
            self.assertTrue(metadata.thumb_url.endswith(".webp") or metadata.thumb_url.endswith(".png"))

    def test_remove_paths_removes_files_and_empty_session_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "abc123" / "shot.png"
            path.parent.mkdir()
            path.write_bytes(b"png")

            ScreenshotStore(tmp).remove_paths([path])

            self.assertFalse(path.exists())
            self.assertFalse(path.parent.exists())


if __name__ == "__main__":
    unittest.main()
