import unittest
from datetime import date, datetime
from unittest.mock import MagicMock, patch

from app import mcp_analysis


def result(*, one=None, many=None):
    cursor = MagicMock()
    cursor.fetchone.return_value = one
    cursor.fetchall.return_value = many if many is not None else []
    return cursor


def connection(*responses):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.execute.side_effect = responses
    return conn


BOUNDS = {"covered_first": date(2016, 1, 1), "covered_last": date(2016, 12, 31),
          "activity_first": date(2016, 4, 3), "activity_last": date(2016, 11, 1)}


class AnalysisTests(unittest.TestCase):
    def test_first_recorded_swim_is_qualified_by_coverage(self):
        summary = {"first_recorded_date": date(2016, 4, 3),
                   "last_recorded_date": date(2016, 11, 1),
                   "activity_count": 2, "total_distance_m": 1500,
                   "total_duration_s": 2400}
        conn = connection(result(), result(one=summary), result(one={"activity_id": 1}),
                          result(one={"activity_id": 2}),
                          result(one={"activity_id": 2, "lap_number": 4,
                                      "distance_m": 100, "duration_s": 82}), result(many=[]),
                          result(one=BOUNDS), result(one={"n": 200}))
        with patch("app.mcp_analysis.mcp_data._connection", return_value=conn):
            data = mcp_analysis.get_sport_history("swimming", "2016-01-01", "2016-12-31")
        self.assertEqual(data["summary"]["first_recorded_date"], "2016-04-03")
        self.assertFalse(data["coverage"]["complete_for_window"])
        self.assertFalse(data["coverage"]["account_lifetime_verified"])
        self.assertIn("average", data["best_record"]["basis"])
        self.assertEqual(data["best_measured_100m_lap"]["duration_s"], 82)

    def test_yearly_cycling_distance_is_sql_aggregate(self):
        period = {"period": date(2016, 1, 1), "activity_count": 10,
                  "total_distance_m": 125000.0, "total_duration_s": 20000.0}
        summary = {"first_recorded_date": date(2016, 4, 3),
                   "last_recorded_date": date(2016, 11, 1), "activity_count": 10,
                   "total_distance_m": 125000.0, "total_duration_s": 20000.0}
        conn = connection(result(), result(one=summary), result(one={"activity_id": 1}),
                          result(one={"activity_id": 2}), result(many=[period]),
                          result(one=BOUNDS), result(one={"n": 366}))
        with patch("app.mcp_analysis.mcp_data._connection", return_value=conn):
            data = mcp_analysis.get_sport_history("cycling", "2016-01-01", "2016-12-31")
        self.assertEqual(data["periods"][0]["total_distance_m"], 125000.0)
        self.assertEqual(data["periods"][0]["period"], "2016-01-01")
        self.assertTrue(data["coverage"]["complete_for_window"])
        queries = [call.args[0] for call in conn.execute.call_args_list]
        self.assertTrue(any("date_trunc('year'" in query and "sum(distance_m)" in query for query in queries))

    def test_monthly_running_progress_keeps_missing_metric_counts(self):
        periods = [
            {"period": date(2016, 4, 1), "activity_count": 2,
             "mean_running_pace_s_per_km": 400, "hr_count": 1},
            {"period": date(2016, 5, 1), "activity_count": 3,
             "mean_running_pace_s_per_km": 370, "hr_count": 2},
        ]
        conn = connection(result(), result(one={"n": 5}), result(many=periods), result(many=[]),
                          result(one=BOUNDS), result(one={"n": 50}))
        with patch("app.mcp_analysis.mcp_data._connection", return_value=conn):
            data = mcp_analysis.get_sport_progress("running", "2016-04-01", "2016-05-31")
        self.assertEqual([row["mean_running_pace_s_per_km"] for row in data["periods"]], [400, 370])
        self.assertEqual([row["hr_count"] for row in data["periods"]], [1, 2])
        self.assertFalse(data["coverage"]["complete_for_window"])
        self.assertEqual(data["data_status"], "partial_collection")
        queries = [call.args[0] for call in conn.execute.call_args_list]
        self.assertTrue(any("distance_band" in query and "pace_band" in query for query in queries))

    def test_search_is_bounded_and_uses_literal_name_filter(self):
        activity = {"activity_id": 1, "name": "Hill 100%", "start_local": datetime(2016, 4, 3)}
        conn = connection(result(), result(one={"n": 2}), result(many=[activity]),
                          result(one=BOUNDS), result(one={"n": 0}))
        with patch("app.mcp_analysis.mcp_data._connection", return_value=conn):
            data = mcp_analysis.search_activities("cycling", name="100%", sort="oldest", limit=1)
        self.assertEqual(data["next_offset"], 1)
        self.assertEqual(data["activities"][0]["start_local"], "2016-04-03T00:00:00")
        self.assertIn("%100\\%%", conn.execute.call_args_list[1].args[1])
        self.assertFalse(data["coverage"]["complete_for_window"])

    def test_invalid_input_does_not_open_database(self):
        with patch("app.mcp_analysis.mcp_data._connection") as connect:
            with self.assertRaises(ValueError):
                mcp_analysis.search_activities(sort="newest; DROP TABLE garmin_activities")
            with self.assertRaises(ValueError):
                mcp_analysis.get_sport_history("swimming", "2026-01-02", "2026-01-01")
            with self.assertRaises(ValueError):
                mcp_analysis.search_activities(limit=101)
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
