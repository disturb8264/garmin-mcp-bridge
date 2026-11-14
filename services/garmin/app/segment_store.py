"""Persist user-defined segments and cached GPS passes using ordinary PostgreSQL."""

from datetime import date
from math import isfinite

from psycopg.types.json import Jsonb

from app import database, mcp_data
from app.config import load_config
from app.mcp_analysis import _coverage, _dates
from app.segments import haversine_m, match_passes


def validate_definition(name, sport, start_latitude, start_longitude,
                        end_latitude, end_longitude, radius_m, waypoints):
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
        raise ValueError("Segment name must be 1..100 characters")
    if sport not in ("running", "cycling"):
        raise ValueError("Segment sport must be running or cycling")
    if not isinstance(radius_m, (int, float)) or not isfinite(radius_m) or not 5 <= radius_m <= 200:
        raise ValueError("radius_m must be 5..200")
    checkpoints = [{"latitude": start_latitude, "longitude": start_longitude}]
    if not isinstance(waypoints, list) or len(waypoints) > 8:
        raise ValueError("waypoints must be a list of at most 8 coordinates")
    checkpoints += waypoints
    checkpoints.append({"latitude": end_latitude, "longitude": end_longitude})
    for point in checkpoints:
        if not isinstance(point, dict) or set(point) != {"latitude", "longitude"}:
            raise ValueError("Each checkpoint needs latitude and longitude")
        lat, lon = point["latitude"], point["longitude"]
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)) or not isfinite(lat) or not isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("Checkpoint coordinates are invalid")
    for a, b in zip(checkpoints, checkpoints[1:]):
        if haversine_m(a["latitude"], a["longitude"], b["latitude"], b["longitude"]) <= 2 * radius_m:
            raise ValueError("Adjacent checkpoints must be farther apart than twice radius_m")
    return name.strip(), checkpoints


def register_segment(name, sport, start_latitude, start_longitude,
                     end_latitude, end_longitude, radius_m=30, waypoints=None):
    name, checkpoints = validate_definition(name, sport, start_latitude, start_longitude,
                                            end_latitude, end_longitude, radius_m, waypoints or [])
    config = load_config()
    if not config.db_ready:
        raise RuntimeError("Collector database is not configured")
    with database.connect(config, statement_timeout_ms=10000) as conn:
        if _collection_active(conn):
            return {"status": "busy", "message": "Collection is active; retry segment registration later"}
        database.ensure_schema(conn)
        row = conn.execute("""INSERT INTO garmin_segments
            (name, sport_group, start_latitude, start_longitude,
             end_latitude, end_longitude, waypoints, radius_m)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (name, sport_group) DO NOTHING RETURNING segment_id""",
            (name, sport, start_latitude, start_longitude, end_latitude,
             end_longitude, Jsonb(checkpoints[1:-1]), radius_m)).fetchone()
        if row is None:
            return {"status": "already_exists", "message": "A segment with this name and sport already exists"}
    return {"status": "created", "segment_id": row[0], "name": name, "sport": sport,
            "radius_m": radius_m, "waypoint_count": len(checkpoints) - 2,
            "indexing_complete": False}


def _segment(conn, segment_id, segment_name, sport):
    if (segment_id is None) == (segment_name is None):
        raise ValueError("Provide exactly one of segment_id or segment_name")
    if sport not in ("running", "cycling"):
        raise ValueError("sport must be running or cycling")
    if segment_id is not None:
        row = conn.execute("""SELECT segment_id, name, sport_group, start_latitude,
            start_longitude, end_latitude, end_longitude, waypoints, radius_m
            FROM garmin_segments WHERE segment_id = %s AND sport_group = %s""",
            (segment_id, sport)).fetchone()
    else:
        row = conn.execute("""SELECT segment_id, name, sport_group, start_latitude,
            start_longitude, end_latitude, end_longitude, waypoints, radius_m
            FROM garmin_segments WHERE name = %s AND sport_group = %s""",
            (segment_name, sport)).fetchone()
    return row


def _pending_sql():
    return """FROM garmin_activities a LEFT JOIN garmin_segment_scans s
        ON s.segment_id = %s AND s.activity_id = a.activity_id
        WHERE a.sport_group = %s AND (s.activity_id IS NULL OR
        s.activity_collected_at IS DISTINCT FROM a.collected_at)"""


def _collection_active(conn):
    return conn.execute("""SELECT EXISTS (SELECT 1 FROM garmin_sync_history
        WHERE status = 'running' AND started_at > now() - interval '12 hours')""").fetchone()[0]


def get_segment_best_efforts(segment_id=None, segment_name=None, sport="cycling",
                             start_date=None, end_date=None, limit=10):
    start, end = _dates(start_date, end_date)
    if not 1 <= limit <= 50:
        raise ValueError("limit must be 1..50")
    with mcp_data._connection() as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            segment = _segment(conn, segment_id, segment_name, sport)
            if segment is None:
                return {"status": "not_found", "efforts": []}
            segment_id = segment["segment_id"]
            dates = ""
            date_args = []
            if start:
                dates += " AND a.start_local >= %s::date"
                date_args.append(start)
            if end:
                dates += " AND a.start_local < (%s::date + interval '1 day')"
                date_args.append(end)
            pending = conn.execute(f"SELECT count(*) AS n {_pending_sql()}{dates}",
                                   (segment_id, sport, *date_args)).fetchone()["n"]
            skipped = conn.execute(f"""SELECT count(*) AS n FROM garmin_segment_scans s
                JOIN garmin_activities a USING (activity_id)
                WHERE s.segment_id = %s AND s.status = 'too_large'{dates}""",
                (segment_id, *date_args)).fetchone()["n"]
            coverage = _coverage(conn, start, end)
            if pending or skipped:
                return {"status": "indexing_required" if pending else "incomplete",
                        "segment_id": segment_id, "segment_name": segment["name"],
                        "sport": sport, "pending_activities": pending,
                        "skipped_activities": skipped, "efforts": [], "coverage": coverage,
                        "message": "Complete segment indexing before ranking efforts"}
            efforts = conn.execute(f"""SELECT e.activity_id, a.start_local::date AS activity_date,
                e.pass_number, e.started_at, e.ended_at, e.distance_m, e.duration_s,
                e.distance_basis, e.average_speed_mps, e.average_pace_s_per_km,
                e.average_hr, e.average_power, e.elevation_gain_m, e.sample_count,
                row_number() OVER (ORDER BY e.duration_s, e.started_at, e.activity_id) AS rank
                FROM garmin_segment_efforts e JOIN garmin_activities a USING (activity_id)
                WHERE e.segment_id = %s{dates}
                ORDER BY e.duration_s, e.started_at, e.activity_id LIMIT %s""",
                (segment_id, *date_args, limit)).fetchall()
    return {"status": "success" if efforts else "no_gps_passes",
            "segment_id": segment_id, "segment_name": segment["name"],
            "sport": sport, "radius_m": segment["radius_m"],
            "waypoints": segment["waypoints"], "indexing_complete": True,
            "efforts": mcp_data._jsonable(efforts), "coverage": coverage,
            "units": {"distance": "m", "duration": "s", "speed": "m/s",
                      "pace": "s/km", "heart_rate": "bpm", "power": "W",
                      "elevation_gain": "m"}}


def refresh_segment(segment_id: int, batch_size: int = 5):
    if segment_id <= 0 or not 1 <= batch_size <= 20:
        raise ValueError("Invalid segment_id or batch_size")
    config = load_config()
    if not config.db_ready:
        raise RuntimeError("Collector database is not configured")
    with database.connect(config, statement_timeout_ms=30000) as conn:
        if _collection_active(conn):
            return {"status": "busy", "message": "Collection is active; retry segment indexing later"}
        database.ensure_schema(conn)
        row = conn.execute("""SELECT segment_id, name, sport_group, start_latitude,
            start_longitude, end_latitude, end_longitude, waypoints, radius_m
            FROM garmin_segments WHERE segment_id = %s""", (segment_id,)).fetchone()
        if row is None:
            return {"status": "not_found", "segment_id": segment_id}
        _, name, sport, slat, slon, elat, elon, waypoints, radius = row
        checkpoints = [{"latitude": slat, "longitude": slon}, *waypoints,
                       {"latitude": elat, "longitude": elon}]
        activity_ids = [item[0] for item in conn.execute(
            f"SELECT a.activity_id {_pending_sql()} ORDER BY a.activity_id LIMIT %s",
            (segment_id, sport, batch_size)).fetchall()]
        scanned = efforts_saved = skipped = 0
        for activity_id in activity_ids:
            with conn.transaction():
                conn.execute("SELECT pg_advisory_xact_lock(%s)", (activity_id,))
                revision = conn.execute("SELECT collected_at FROM garmin_activities WHERE activity_id = %s",
                                        (activity_id,)).fetchone()
                if revision is None:
                    continue
                old = conn.execute("""SELECT activity_collected_at FROM garmin_segment_scans
                    WHERE segment_id = %s AND activity_id = %s""", (segment_id, activity_id)).fetchone()
                if old and old[0] == revision[0]:
                    continue
                raw_lat = "CASE WHEN jsonb_typeof(raw_json->'directLatitude')='number' THEN (raw_json->>'directLatitude')::double precision END"
                raw_lon = "CASE WHEN jsonb_typeof(raw_json->'directLongitude')='number' THEN (raw_json->>'directLongitude')::double precision END"
                lat = f"coalesce(latitude, {raw_lat})"
                lon = f"coalesce(longitude, {raw_lon})"
                rows = conn.execute(f"""SELECT timestamp_utc, {lat} AS latitude,
                    {lon} AS longitude, distance_m, elevation_m, heart_rate, power
                    FROM garmin_samples WHERE activity_id = %s ORDER BY sample_index LIMIT 100001""",
                    (activity_id,)).fetchall()
                conn.execute("DELETE FROM garmin_segment_efforts WHERE segment_id = %s AND activity_id = %s",
                             (segment_id, activity_id))
                if len(rows) > 100000:
                    status, passes = "too_large", []
                    skipped += 1
                else:
                    keys = ("timestamp_utc", "latitude", "longitude", "distance_m",
                            "elevation_m", "heart_rate", "power")
                    points = [dict(zip(keys, item)) for item in rows]
                    passes = match_passes(points, checkpoints, radius)
                    status = "completed" if any(p.get("latitude") is not None and p.get("longitude") is not None and p.get("timestamp_utc") is not None for p in points) else "no_gps"
                for effort in passes:
                    conn.execute("""INSERT INTO garmin_segment_efforts
                        (segment_id, activity_id, pass_number, started_at, ended_at,
                         distance_m, duration_s, distance_basis, average_speed_mps,
                         average_pace_s_per_km, average_hr, average_power,
                         elevation_gain_m, sample_count)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (segment_id, activity_id, effort["pass_number"], effort["started_at"],
                         effort["ended_at"], effort["distance_m"], effort["duration_s"],
                         effort["distance_basis"], effort["average_speed_mps"],
                         effort["average_pace_s_per_km"], effort["average_hr"],
                         effort["average_power"], effort["elevation_gain_m"],
                         effort["sample_count"]))
                conn.execute("""INSERT INTO garmin_segment_scans
                    (segment_id, activity_id, activity_collected_at, status)
                    VALUES (%s,%s,%s,%s) ON CONFLICT (segment_id, activity_id)
                    DO UPDATE SET activity_collected_at = EXCLUDED.activity_collected_at,
                    status = EXCLUDED.status, scanned_at = now()""",
                    (segment_id, activity_id, revision[0], status))
                scanned += 1
                efforts_saved += len(passes)
        remaining = conn.execute(f"SELECT count(*) {_pending_sql()}",
                                 (segment_id, sport)).fetchone()[0]
        skipped_total = conn.execute("""SELECT count(*) FROM garmin_segment_scans
            WHERE segment_id = %s AND status = 'too_large'""", (segment_id,)).fetchone()[0]
    return {"status": "complete" if remaining == 0 and skipped_total == 0 else "partial",
            "segment_id": segment_id, "segment_name": name, "scanned_activities": scanned,
            "new_efforts": efforts_saved, "remaining_activities": remaining,
            "skipped_activities": skipped_total, "skipped_activities_in_batch": skipped}
