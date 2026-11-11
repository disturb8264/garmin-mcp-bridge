import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from unittest.mock import MagicMock

import httpx2 as httpx
from mcp.client import Client

from app import mcp_data
from app.mcp_server import create_app, mcp


class MCPToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_tools_are_read_only_and_return_structured_data(self):
        async with Client(mcp) as client:
            listed = await client.list_tools()
            self.assertEqual(
                {tool.name for tool in listed.tools},
                {"list_activities", "get_activity", "get_activity_laps", "get_activity_samples", "get_sync_status", "get_activities_by_date"},
            )
            for tool in listed.tools:
                self.assertEqual(tool.annotations.read_only_hint, tool.name != "get_activities_by_date")
                self.assertEqual(tool.annotations.open_world_hint, tool.name == "get_activities_by_date")
            with patch("app.mcp_server.mcp_data.list_activities", return_value={"activities": [{"activity_id": 1}], "count": 1}):
                result = await client.call_tool("list_activities", {"limit": 1, "sport": "cycling"})
            self.assertFalse(result.is_error)
            self.assertEqual(result.structured_content["activities"][0]["activity_id"], 1)
            with patch("app.mcp_server.mcp_data.sync_status", side_effect=RuntimeError("MCP database is not configured")):
                failure = await client.call_tool("get_sync_status", {})
            self.assertTrue(failure.is_error)
            self.assertIn("MCP database is not configured", failure.content[0].text)

    async def test_http_requires_internal_token(self):
        app = create_app(token="a" * 64)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            response = await client.post("/mcp", json={})
        self.assertEqual(response.status_code, 401)

    async def test_http_lists_sport_neutral_tools_with_token(self):
        app = create_app(token="a" * 64)
        transport = httpx.ASGITransport(app=app)
        async with app.app.router.lifespan_context(app.app):
            async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as client:
                response = await client.post(
                    "/mcp",
                    headers={"X-MCP-Internal-Token": "a" * 64,
                             "Accept": "application/json, text/event-stream"},
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                )
        self.assertEqual(response.status_code, 200)
        names = {tool["name"] for tool in response.json()["result"]["tools"]}
        self.assertIn("list_activities", names)
        self.assertIn("get_activity_samples", names)
        self.assertIn("get_activities_by_date", names)


class MCPDatabaseTests(unittest.TestCase):
    def test_read_only_connection_settings(self):
        settings = {
            "MCP_PGHOST": "database", "MCP_PGPORT": "5432",
            "MCP_PGDATABASE": "running", "MCP_PGUSER": "reader",
            "MCP_PGPASSWORD": "test-password",
        }
        with patch.dict(os.environ, settings), patch("app.mcp_data.psycopg.connect") as connect:
            mcp_data._connection()
        self.assertEqual(connect.call_args.kwargs["user"], "reader")
        self.assertIn("default_transaction_read_only=on", connect.call_args.kwargs["options"])

    def test_sample_page_is_bounded_before_db_access(self):
        with patch("app.mcp_data._connection") as connect:
            with self.assertRaises(ValueError):
                mcp_data.activity_samples(1, limit=201)
        connect.assert_not_called()

    def test_list_activities_serializes_time_and_binds_sport(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.execute.return_value.fetchall.return_value = [
            {"activity_id": 7, "start_utc": datetime(2026, 11, 11, tzinfo=timezone.utc)}
        ]
        with patch("app.mcp_data._connection", return_value=connection):
            result = mcp_data.list_activities(1, "swimming")
        self.assertEqual(result["activities"][0]["start_utc"], "2026-11-11T00:00:00+00:00")
        self.assertEqual(connection.execute.call_args.args[1], ("swimming", "swimming", 1))
        self.assertNotIn("raw_json", connection.execute.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
