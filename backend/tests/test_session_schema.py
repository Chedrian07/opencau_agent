import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.sessions import CreateSessionRequest


class CreateSessionRequestTests(unittest.TestCase):
    def test_accepts_missing_session_id(self) -> None:
        request = CreateSessionRequest()

        self.assertIsNone(request.session_id)

    def test_accepts_safe_session_id(self) -> None:
        request = CreateSessionRequest(session_id="abc-123_ok")

        self.assertEqual(request.session_id, "abc-123_ok")

    def test_rejects_unsafe_session_id(self) -> None:
        with self.assertRaises(ValidationError):
            CreateSessionRequest(session_id="../host")


if __name__ == "__main__":
    unittest.main()
