import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import httpx2 as httpx

from app.collector_api import create_app
from app.segment_store import get_segment_best_efforts
from app.segment_store import validate_definition
from app.segments import match_passes


START = {"latitude": 0.0, "longitude": 0.0}
END = {"latitude": 0.001, "longitude": 0.0}
ORIGIN = datetime(2026, 1, 1, tzinfo=timezone.utc)


def point(lat, second, distance=None):
    return {"latitude": lat, "longitude": 0.0,
            "timestamp_utc": ORIGIN + timedelta(seconds=second),
            "distance_m": distance, "heart_rate": 140, "power": 200,
            "elevation_m": lat * 1000}


class SegmentMatchingTests(unittest.TestCase):
    def test_start_and_end_entry_yield_timestamp_based_effort(self):
        points = [point(-0.0002, 0, 0), point(0, 10, 20),
                  point(0.0005, 20, 75), point(0.001, 30, 130)]
        passes = match_passes(points, [START, END], 15)
        self.assertEqual(len(passes), 1)
        self.assertEqual(passes[0]["duration_s"], 20)
        self.assertEqual(passes[0]["distance_m"], 110)
        self.assertEqual(passes[0]["distance_basis"], "device_cumulative_distance")

    def test_repeated_passes_are_kept_separately(self):
        latitudes = [-0.0002, 0, 0.0005, 0.001, 0.0013,
                     0.0005, -0.0002, 0, 0.0005, 0.001]
        points = [point(lat, i * 10, i * 55) for i, lat in enumerate(latitudes)]
        passes = match_passes(points, [START, END], 15)
        self.assertEqual([effort["pass_number"] for effort in passes], [1, 2])
        self.assertLess(passes[0]["started_at"], passes[1]["started_at"])

    def test_reverse_incomplete_and_gps_jump_are_excluded(self):
        reverse = [point(0.0012, 0), point(0.001, 10),
                   point(0.0005, 20), point(0, 30), point(-0.0002, 40)]
        self.assertEqual(match_passes(reverse, [START, END], 15), [])
        incomplete = [point(-0.0002, 0), point(0, 10), point(0.0005, 20)]
        self.assertEqual(match_passes(incomplete, [START, END], 15), [])
        jump = [point(-0.0002, 0), point(0, 10), point(1.0, 11), point(0.001, 20)]
        self.assertEqual(match_passes(jump, [START, END], 15), [])

    def test_ordered_waypoint_and_definition_validation(self):
        waypoint = {"latitude": 0.0005, "longitude": 0.0}
        points = [point(-0.0002, 0), point(0, 10),
                  point(0.0005, 20), point(0.001, 30)]
        self.assertEqual(len(match_passes(points, [START, waypoint, END], 15)), 1)
        name, checkpoints = validate_definition(" Test climb ", "cycling", 0, 0,
                                                0.001, 0, 15, [waypoint])
        self.assertEqual(name, "Test climb")
        self.assertEqual(len(checkpoints), 3)
        with self.assertRaises(ValueError):
            validate_definition("too short", "cycling", 0, 0, 0.0001, 0, 15, [])


class SegmentCacheTests(unittest.TestCase):
    def test_incomplete_index_never_returns_provisional_best(self):
        def cursor(one=None):
            result = MagicMock()
            result.fetchone.return_value = one
            return result
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.execute.side_effect = [
            cursor(), cursor(one={"segment_id": 1, "name": "User climb", "radius_m": 20}),
            cursor(one={"n": 3}), cursor(one={"n": 0}),
            cursor(one={"covered_first": None, "covered_last": None,
                        "activity_first": None, "activity_last": None}),
        ]
        with patch("app.segment_store.mcp_data._connection", return_value=conn):
            data = get_segment_best_efforts(segment_id=1, sport="cycling")
        self.assertEqual(data["status"], "indexing_required")
        self.assertEqual(data["efforts"], [])
        self.assertEqual(data["pending_activities"], 3)


class SegmentApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_segment_registration_requires_private_token(self):
        app = create_app(token="a" * 64)
        transport = httpx.ASGITransport(app=app)
        payload = {"name": "User climb", "sport": "cycling",
                   "start_latitude": 0.0, "start_longitude": 0.0,
                   "end_latitude": 0.001, "end_longitude": 0.0}
        with patch("app.collector_api.segment_store.register_segment",
                   return_value={"status": "created", "segment_id": 1}) as register:
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
                denied = await client.post("/register-segment", json=payload)
                allowed = await client.post("/register-segment", json=payload,
                                            headers={"X-Collector-Internal-Token": "a" * 64})
        self.assertEqual(denied.status_code, 401)
        self.assertEqual(allowed.json()["segment_id"], 1)
        register.assert_called_once()


if __name__ == "__main__":
    unittest.main()
