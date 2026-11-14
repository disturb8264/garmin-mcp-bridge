import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.mcp_route import get_activity_route
from app.models import activity_row, lap_rows, sample_rows


def cursor(one=None, many=None):
    result = MagicMock()
    result.fetchone.return_value = one
    result.fetchall.return_value = many or []
    return result


class RouteTests(unittest.TestCase):
    def test_missing_gps_is_not_presented_as_estimated_route(self):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.execute.side_effect = [
            cursor(), cursor(one={"activity_id": 1, "sport_group": "swimming", "start_local": None}),
            cursor(many=[]), cursor(one={"sample_count": 20, "gps_point_count": 0,
                                     "first_index": None, "last_index": None}),
        ]
        with patch("app.mcp_route.mcp_data._connection", return_value=conn):
            data = get_activity_route(1)
        self.assertEqual(data["status"], "no_gps_data")
        self.assertEqual(data["points"], [])

    def test_saved_raw_gps_is_downsampled_and_bounded(self):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.execute.side_effect = [
            cursor(), cursor(one={"activity_id": 2, "sport_group": "cycling",
                                  "start_local": datetime(2016, 5, 1)}),
            cursor(many=[]), cursor(one={"sample_count": 100, "gps_point_count": 80,
                                     "first_index": 10, "last_index": 89}),
            cursor(many=[{"sample_index": 10, "latitude": 37.0, "longitude": 127.0},
                         {"sample_index": 50, "latitude": 37.1, "longitude": 127.1}]),
        ]
        with patch("app.mcp_route.mcp_data._connection", return_value=conn):
            data = get_activity_route(2, max_points=2)
        self.assertEqual(data["status"], "success")
        self.assertEqual(len(data["points"]), 2)
        self.assertEqual(data["sample_interval"], 40)
        self.assertIn("raw_json", conn.execute.call_args_list[3].args[0])

    def test_new_samples_and_swim_metrics_are_optional(self):
        details = {"metricDescriptors": [
            {"key": "directLatitude", "metricsIndex": 0},
            {"key": "directLongitude", "metricsIndex": 1},
        ], "activityDetailMetrics": [{"metrics": [37.0, 127.0]},
                                     {"metrics": [91.0, 127.0]}]}
        samples = sample_rows(1, details)
        self.assertEqual(samples[0]["latitude"], 37.0)
        self.assertIsNone(samples[1]["latitude"])
        row = activity_row({"activityId": 1, "poolLength": 25, "poolLengthUnit": "meter",
                            "averageSwolf": 42, "totalStrokes": 700},
                           {}, None, sport_group="swimming")
        self.assertEqual((row["pool_length_m"], row["average_swolf"], row["total_strokes"]),
                         (25, 42, 700))
        laps = lap_rows(1, {"lapDTOs": [{"swolf": 40, "strokeCount": 20}]}, "swimming")
        self.assertEqual((laps[0]["swolf"], laps[0]["stroke_count"]), (40, 20))


if __name__ == "__main__":
    unittest.main()
