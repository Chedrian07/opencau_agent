import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
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


class SettingsTests(unittest.TestCase):
    def test_cors_origins_are_split_and_trimmed(self) -> None:
        settings = Settings(
            _env_file=None,
            backend_cors_origins="http://localhost:3000, http://127.0.0.1:3000",
        )

        self.assertEqual(settings.cors_origins, ["http://localhost:3000", "http://127.0.0.1:3000"])

    def test_lmstudio_alias_normalizes(self) -> None:
        settings = Settings(_env_file=None, llm_profile="LMStudio")

        self.assertEqual(settings.llm_profile, "lmstudio-responses")

    def test_openai_alias_normalizes(self) -> None:
        settings = Settings(_env_file=None, llm_profile="OpenAI")

        self.assertEqual(settings.llm_profile, "openai-native")


if __name__ == "__main__":
    unittest.main()
