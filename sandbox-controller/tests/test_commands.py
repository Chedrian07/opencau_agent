import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.commands import ALLOWED_COMMANDS, command_for
from app.config import Settings
from app.schemas import CommandRequest, CreateSessionRequest


class CommandAllowlistTests(unittest.TestCase):
    def test_healthcheck_uses_fixed_command(self) -> None:
        request = CommandRequest(operation="healthcheck")

        self.assertEqual(command_for(request), ["/usr/local/bin/healthcheck.sh"])

    def test_no_shell_entrypoint_is_allowlisted(self) -> None:
        flattened = " ".join(" ".join(command) for command in ALLOWED_COMMANDS.values())

        self.assertNotIn("/bin/sh", flattened)
        self.assertNotIn("bash -c", flattened)

    def test_rejects_unknown_operation(self) -> None:
        with self.assertRaises(ValidationError):
            CommandRequest(operation="shell")  # type: ignore[arg-type]


class SessionIdTests(unittest.TestCase):
    def test_rejects_path_like_session_id(self) -> None:
        with self.assertRaises(ValidationError):
            CreateSessionRequest(session_id="../bad")


class SettingsTests(unittest.TestCase):
    def test_start_timeout_is_bounded(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(sandbox_start_timeout_sec=0)


if __name__ == "__main__":
    unittest.main()
