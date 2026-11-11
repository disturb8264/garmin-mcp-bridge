import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from garminconnect import GarminConnectConnectionError

from app.config import Config
from app.garmin_client import GarminReader, MFARequired, _prompt_mfa


def config(token_dir: Path, email="", password="") -> Config:
    return Config(email, password, token_dir, "", 5432, "", "", "", 7, "INFO")


class AuthTests(unittest.TestCase):
    def test_cached_token_can_login_without_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            token_dir = Path(directory)
            (token_dir / "garmin_tokens.json").write_text("{}")
            with patch("app.garmin_client.Garmin") as garmin:
                GarminReader(config(token_dir)).login()
            garmin.return_value.login.assert_called_once_with(str(token_dir))

    def test_connection_failure_does_not_repeat_full_login(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("app.garmin_client.Garmin") as garmin:
                garmin.return_value.login.side_effect = GarminConnectConnectionError("DNS failed")
                with self.assertRaisesRegex(RuntimeError, "network and DNS"):
                    GarminReader(config(Path(directory), "a@example.com", "secret")).login()
            self.assertEqual(garmin.return_value.login.call_count, 1)

    def test_mfa_does_not_prompt_in_unattended_run(self):
        with patch("app.garmin_client.sys.stdin.isatty", return_value=False):
            with self.assertRaises(MFARequired):
                _prompt_mfa()

if __name__ == "__main__":
    unittest.main()
