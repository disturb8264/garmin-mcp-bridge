import unittest
from unittest.mock import patch

from app import combined, combined_healthcheck


class CombinedModeTests(unittest.TestCase):
    def test_starts_collector_and_mcp(self):
        self.assertEqual([name for name, _ in combined.COMMANDS], ["collector", "mcp"])

    def test_healthcheck_checks_mcp(self):
        with patch.object(combined_healthcheck, "check_mcp") as check_mcp:
            combined_healthcheck.main()
        check_mcp.assert_called_once_with()
