"""Fill optional swim fields from saved activity/lap JSON without Garmin calls."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import database
from app.config import load_config
from app.models import pick, pool_length_m, stroke_name


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    config = load_config()
    if not config.db_ready:
        parser.error("Database writer settings are required")
    scanned = updated = last_id = 0
    with database.connect(config, statement_timeout_ms=30000) as conn:
        if args.apply:
            running = conn.execute("""SELECT count(*) FROM garmin_sync_history
                WHERE status = 'running' AND started_at > now() - interval '24 hours'""").fetchone()[0]
            if running:
                parser.error("A collection run is active; retry after it finishes")
            database.ensure_schema(conn)
        while True:
            rows = conn.execute("""SELECT activity_id, raw_json FROM garmin_activities
                WHERE sport_group = 'swimming' AND activity_id > %s
                ORDER BY activity_id LIMIT 100""", (last_id,)).fetchall()
            if not rows:
                break
            for activity_id, raw in rows:
                listing = raw.get("listing") or {}
                activity = raw.get("activity") or {}
                combined = {**listing, **activity, **(activity.get("summaryDTO") or {})}
                values = (pool_length_m(combined), pick(combined, "averageSwolf", "avgSwolf"),
                          pick(combined, "totalStrokes", "strokeCount"))
                if args.apply:
                    with conn.transaction():
                        conn.execute("SELECT pg_advisory_xact_lock(%s)", (activity_id,))
                        conn.execute("""UPDATE garmin_activities SET
                            pool_length_m = COALESCE(pool_length_m, %s),
                            average_swolf = COALESCE(average_swolf, %s),
                            total_strokes = COALESCE(total_strokes, %s)
                            WHERE activity_id = %s""", (*values, activity_id))
                        laps = conn.execute("""SELECT lap_number, raw_json FROM garmin_laps
                            WHERE activity_id = %s""", (activity_id,)).fetchall()
                        for lap_number, lap in laps:
                            lap_values = (pick(lap, "swolf", "averageSwolf"),
                                          pick(lap, "strokeCount", "totalStrokes"),
                                          stroke_name(pick(lap, "swimStroke", "strokeType")))
                            conn.execute("""UPDATE garmin_laps SET
                                swolf = COALESCE(swolf, %s),
                                stroke_count = COALESCE(stroke_count, %s),
                                stroke_type = COALESCE(stroke_type, %s)
                                WHERE activity_id = %s AND lap_number = %s""",
                                (*lap_values, activity_id, lap_number))
                    updated += 1
                scanned += 1
            last_id = rows[-1][0]
    print(f"swim_activities_scanned={scanned} activities_enriched={updated} mode={'apply' if args.apply else 'dry-run'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
