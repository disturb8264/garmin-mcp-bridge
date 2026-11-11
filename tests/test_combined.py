import os
import unittest
from unittest.mock import patch

from app import combined, combined_healthcheck


class CombinedModeTests(unittest.TestCase):
    def test_direct_mode_starts_only_collector_and_mcp(self):
        with patch.dict(os.environ, {"TUNNEL_ENABLED": "false"}):
            self.assertEqual([name for name, _ in combined.enabled_commands()], ["collector", "mcp"])

    def test_default_mode_includes_tunnel(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual([name for name, _ in combined.enabled_commands()],
                             ["collector", "mcp", "tunnel"])

    def test_direct_healthcheck_skips_tunnel_probe(self):
        with patch.dict(os.environ, {"TUNNEL_ENABLED": "false"}), \
                patch.object(combined_healthcheck, "check_mcp") as check_mcp, \
                patch.object(combined_healthcheck.urllib.request, "urlopen") as urlopen:
            combined_healthcheck.main()
        check_mcp.assert_called_once_with()
        urlopen.assert_not_called()

    def test_default_healthcheck_probes_tunnel(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(combined_healthcheck, "check_mcp") as check_mcp, \
                patch.object(combined_healthcheck.urllib.request, "urlopen") as urlopen:
            response = urlopen.return_value.__enter__.return_value
            response.status = 200
            response.read.return_value = b"ready"
            combined_healthcheck.main()
        check_mcp.assert_called_once_with()
        urlopen.assert_called_once_with("http://127.0.0.1:8080/readyz", timeout=2)

    def test_invalid_mode_is_rejected(self):
        with patch.dict(os.environ, {"TUNNEL_ENABLED": "maybe"}):
            with self.assertRaisesRegex(ValueError, "TUNNEL_ENABLED"):
                combined.enabled_commands()
