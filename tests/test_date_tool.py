import unittest
from unittest.mock import AsyncMock, patch

import httpx2

from app.date_query import validate_range
from app.date_tool import get_activities_by_date
from app.collect_range_worker import run as run_worker
from app.garmin_client import GarminAuthError
from garminconnect import GarminConnectConnectionError


class DateLookupTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_single_day_is_returned_without_garmin(self):
        with patch("app.date_tool.mcp_data.activities_by_date", return_value={
            "activities": [{"activity_id": 1}], "coverage_complete": False,
        }), patch("app.date_tool._collect_range", new_callable=AsyncMock) as collect:
            result = await get_activities_by_date("2025-11-13", sport="cycling")
        self.assertEqual((result["status"], result["source"]), ("success", "database"))
        collect.assert_not_awaited()

    async def test_missing_db_date_is_collected_then_read(self):
        with patch("app.date_tool.mcp_data.activities_by_date", side_effect=[
            {"activities": [], "coverage_complete": False},
            {"activities": [{"activity_id": 2}], "coverage_complete": True},
        ]), patch("app.date_tool._collect_range", new_callable=AsyncMock) as collect:
            collect.return_value = {"status": "success"}
            result = await get_activities_by_date("2025-10-29")
        self.assertEqual((result["status"], result["source"]), ("success", "garmin"))
        self.assertEqual(result["activities"][0]["activity_id"], 2)
        collect.assert_awaited_once()

    async def test_confirmed_empty_day_is_not_found(self):
        with patch("app.date_tool.mcp_data.activities_by_date", side_effect=[
            {"activities": [], "coverage_complete": False},
            {"activities": [], "coverage_complete": True},
        ]), patch("app.date_tool._collect_range", new_callable=AsyncMock) as collect:
            collect.return_value = {"status": "success"}
            result = await get_activities_by_date("2025-10-30")
        self.assertEqual(result, {"status": "not_found", "source": "garmin",
                                  "activities": [], "coverage_complete": True})

    async def test_authentication_failure_is_not_not_found(self):
        with patch("app.date_tool.mcp_data.activities_by_date", return_value={
            "activities": [], "coverage_complete": False,
        }), patch("app.date_tool._collect_range", new_callable=AsyncMock) as collect:
            collect.return_value = {"status": "authentication_error", "message": "Garmin authentication failed"}
            result = await get_activities_by_date("2025-10-30")
        self.assertEqual(result["status"], "authentication_error")

    async def test_api_error_is_not_not_found(self):
        with patch("app.date_tool.mcp_data.activities_by_date", return_value={
            "activities": [], "coverage_complete": False,
        }), patch("app.date_tool._collect_range", new_callable=AsyncMock) as collect:
            collect.return_value = {"status": "api_error", "message": "Garmin API connection failed"}
            result = await get_activities_by_date("2025-10-30")
        self.assertEqual(result["status"], "api_error")

    async def test_timeout_is_not_not_found(self):
        with patch("app.date_tool.mcp_data.activities_by_date", return_value={
            "activities": [], "coverage_complete": False,
        }), patch("app.date_tool._collect_range", new_callable=AsyncMock) as collect:
            collect.side_effect = httpx2.ReadTimeout("timed out")
            result = await get_activities_by_date("2025-10-30")
        self.assertEqual(result["status"], "timeout")

    async def test_second_lookup_uses_cache(self):
        with patch("app.date_tool.mcp_data.activities_by_date", side_effect=[
            {"activities": [], "coverage_complete": False},
            {"activities": [{"activity_id": 2}], "coverage_complete": True},
            {"activities": [{"activity_id": 2}], "coverage_complete": True},
        ]), patch("app.date_tool._collect_range", new_callable=AsyncMock) as collect:
            collect.return_value = {"status": "success"}
            first = await get_activities_by_date("2025-10-29")
            second = await get_activities_by_date("2025-10-29")
        self.assertEqual((first["source"], second["source"]), ("garmin", "database"))
        collect.assert_awaited_once()

    async def test_partially_saved_range_fetches_garmin(self):
        with patch("app.date_tool.mcp_data.activities_by_date", side_effect=[
            {"activities": [{"activity_id": 1}], "coverage_complete": False},
            {"activities": [{"activity_id": 1}, {"activity_id": 2}], "coverage_complete": True},
        ]), patch("app.date_tool._collect_range", new_callable=AsyncMock) as collect:
            collect.return_value = {"status": "success"}
            result = await get_activities_by_date("2025-10-29", "2025-10-30")
        self.assertEqual(result["source"], "garmin")
        self.assertEqual(len(result["activities"]), 2)
        collect.assert_awaited_once()

    async def test_invalid_range_rejected_before_db_or_garmin(self):
        with patch("app.date_tool.mcp_data.activities_by_date") as db:
            result = await get_activities_by_date("2025-10-01", "2025-11-01")
        self.assertEqual(result["status"], "invalid_request")
        db.assert_not_called()


class RangeValidationTests(unittest.TestCase):
    def test_inclusive_31_day_limit(self):
        start, end = validate_range("2025-10-01", "2025-10-31")
        self.assertEqual((end - start).days, 30)
        with self.assertRaises(ValueError):
            validate_range("2025-10-01", "2025-11-01")


class WorkerErrorTests(unittest.TestCase):
    def test_authentication_error_has_distinct_status(self):
        with patch("app.collect_range_worker.GarminReader") as reader:
            reader.return_value.login.side_effect = GarminAuthError("private details")
            result = run_worker("2025-10-29", "2025-10-29")
        self.assertEqual(result["status"], "authentication_error")
        self.assertNotIn("private details", str(result))

    def test_garmin_api_error_has_distinct_status(self):
        with patch("app.collect_range_worker.GarminReader") as reader, \
             patch("app.collect_range_worker.database.connect") as connection, \
             patch("app.collect_range_worker.database.ensure_schema"), \
             patch("app.collect_range_worker.collect", side_effect=GarminConnectConnectionError("private details")):
            connection.return_value.__enter__.return_value = connection.return_value
            result = run_worker("2025-10-29", "2025-10-29")
        self.assertEqual(result["status"], "api_error")
        self.assertNotIn("private details", str(result))


if __name__ == "__main__":
    unittest.main()
