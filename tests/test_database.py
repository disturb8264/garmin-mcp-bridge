import unittest
from unittest.mock import MagicMock, patch

from app.database import save_activity


class SaveActivityTests(unittest.TestCase):
    def test_repeated_save_upserts_without_deleting_existing_samples(self):
        conn = MagicMock()
        activity = {"activity_id": 123, "name": "ride"}
        samples = [{"activity_id": 123, "sample_index": 0, "latitude": None,
                    "longitude": None, "raw_json": {"directLatitude": None}}]
        with patch("app.database._insert") as insert:
            save_activity(conn, activity, [], samples)
            save_activity(conn, activity, [], samples)
        commands = [call.args[0] for call in conn.execute.call_args_list]
        self.assertEqual(commands.count("SELECT pg_advisory_xact_lock(%s)"), 2)
        self.assertFalse(any("DELETE FROM garmin_samples" in command for command in commands))
        sample_calls = [call for call in insert.call_args_list if call.args[1] == "garmin_samples"]
        self.assertEqual(len(sample_calls), 2)
        self.assertIn("ON CONFLICT (activity_id, sample_index) DO UPDATE", sample_calls[0].args[3])
        self.assertIn("jsonb_strip_nulls", sample_calls[0].args[3])


if __name__ == "__main__":
    unittest.main()
