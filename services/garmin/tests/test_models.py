import unittest

from app.models import activity_row, classify_activity, lap_rows, sample_rows, sport_groups


class MappingTests(unittest.TestCase):
    def test_running_type_and_activity_mapping(self):
        summary = {
            "activityId": 123,
            "activityName": "Morning run",
            "activityType": {"typeKey": "running"},
            "startTimeGMT": "2026-11-11T00:00:00.0",
            "startTimeLocal": "2026-11-11T09:00:00.0",
            "distance": 5000.0,
            "averageSpeed": 2.5,
        }
        self.assertEqual(classify_activity(summary, {"running": "running"}), "running")
        self.assertIsNone(classify_activity({"activityType": {"typeKey": "cycling"}}, {"running": "running"}))
        row = activity_row(summary, {"summaryDTO": {"averageHR": 145}}, None)
        self.assertEqual(row["activity_id"], 123)
        self.assertEqual(row["distance_m"], 5000.0)
        self.assertEqual(row["average_hr"], 145)
        self.assertEqual(row["average_pace_s_per_km"], 400.0)
        self.assertEqual(row["start_utc"].utcoffset().total_seconds(), 0)
        self.assertIsNone(row["average_power"])

    def test_lap_order_and_missing_values(self):
        rows = lap_rows(123, {"lapDTOs": [{"distance": 1000, "averageSpeed": 4}, {"distance": 500}]})
        self.assertEqual([row["lap_number"] for row in rows], [1, 2])
        self.assertIsNone(rows[0]["average_hr"])
        self.assertEqual(rows[0]["average_pace_s_per_km"], 250.0)
        self.assertIsNone(rows[1]["average_pace_s_per_km"])

    def test_sport_hierarchy_and_sport_specific_pace(self):
        groups = sport_groups([
            {"typeId": 1, "typeKey": "running", "parentTypeId": 0},
            {"typeId": 2, "typeKey": "cycling", "parentTypeId": 0},
            {"typeId": 3, "typeKey": "swimming", "parentTypeId": 0},
            {"typeId": 4, "typeKey": "lap_swimming", "parentTypeId": 3},
            {"typeId": 5, "typeKey": "indoor_cycling", "parentTypeId": 2},
            {"typeId": 6, "typeKey": "multi_sport", "parentTypeId": 0},
        ])
        self.assertEqual(groups["lap_swimming"], "swimming")
        self.assertEqual(groups["indoor_cycling"], "cycling")
        self.assertEqual(classify_activity({"activityType": {"typeKey": "multi_sport"}}, groups), "multisport")
        summary = {"activityId": 10, "activityType": {"typeKey": "lap_swimming"}, "averageSpeed": 1.25}
        row = activity_row(summary, {}, None, sport_group="swimming")
        self.assertEqual(row["sport_group"], "swimming")
        self.assertEqual(row["average_pace_s_per_100m"], 80)
        self.assertIsNone(row["average_pace_s_per_km"])
        laps = lap_rows(10, {"lapDTOs": [{"averageSpeed": 1.25}]}, "swimming")
        self.assertEqual(laps[0]["average_pace_s_per_100m"], 80)
        self.assertIsNone(laps[0]["average_pace_s_per_km"])
        bike = activity_row({**summary, "activityType": {"typeKey": "indoor_cycling"}}, {}, None, sport_group="cycling")
        self.assertIsNone(bike["average_pace_s_per_100m"])

    def test_samples_preserve_sparse_order(self):
        details = {
            "metricDescriptors": [
                {"key": "sumDistance", "metricsIndex": 0},
                {"key": "directHeartRate", "metricsIndex": 1},
                {"key": "directTimestamp", "metricsIndex": 2},
            ],
            "activityDetailMetrics": [
                {"metrics": [10, 120, 1000]},
                {"metrics": [20, None, 3000]},
            ],
        }
        rows = sample_rows(123, details)
        self.assertEqual([row["sample_index"] for row in rows], [0, 1])
        self.assertEqual([row["timestamp_utc"].timestamp() for row in rows], [1, 3])
        self.assertIsNone(rows[1]["heart_rate"])


if __name__ == "__main__":
    unittest.main()
