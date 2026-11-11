"""Fill typed GPS columns from saved raw samples without calling Garmin."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import database
from app.config import load_config


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write typed GPS values after the backfill finishes")
    parser.add_argument("--batch-size", type=int, default=25)
    args = parser.parse_args(argv)
    if not 1 <= args.batch_size <= 500:
        parser.error("batch-size must be 1..500")
    config = load_config()
    if not config.db_ready:
        parser.error("Database writer settings are required")
    processed = updated = last_id = 0
    with database.connect(config, statement_timeout_ms=30000) as conn:
        if args.apply:
            running = conn.execute("""SELECT count(*) FROM garmin_sync_history
                WHERE status = 'running' AND started_at > now() - interval '24 hours'""").fetchone()[0]
            if running:
                parser.error("A collection run is active; retry after it finishes")
            database.ensure_schema(conn)
        while True:
            ids = [row[0] for row in conn.execute("""SELECT activity_id FROM garmin_activities
                WHERE activity_id > %s ORDER BY activity_id LIMIT %s""",
                (last_id, args.batch_size)).fetchall()]
            if not ids:
                break
            for activity_id in ids:
                if args.apply:
                    with conn.transaction():
                        conn.execute("SELECT pg_advisory_xact_lock(%s)", (activity_id,))
                        cursor = conn.execute("""UPDATE garmin_samples SET
                            latitude = COALESCE(latitude, (raw_json->>'directLatitude')::double precision),
                            longitude = COALESCE(longitude, (raw_json->>'directLongitude')::double precision)
                            WHERE activity_id = %s
                              AND (latitude IS NULL OR longitude IS NULL)
                              AND jsonb_typeof(raw_json->'directLatitude') = 'number'
                              AND jsonb_typeof(raw_json->'directLongitude') = 'number'
                              AND (raw_json->>'directLatitude')::double precision BETWEEN -90 AND 90
                              AND (raw_json->>'directLongitude')::double precision BETWEEN -180 AND 180""",
                            (activity_id,))
                        updated += cursor.rowcount
                processed += 1
            last_id = ids[-1]
    print(f"activities_scanned={processed} gps_points_updated={updated} mode={'apply' if args.apply else 'dry-run'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
