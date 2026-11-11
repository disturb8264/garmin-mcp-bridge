"""Bounded GPS route reads from typed columns or already-saved raw samples."""

from app import mcp_data


def get_activity_route(activity_id: int, sample_interval: int | None = None,
                       max_points: int = 500) -> dict:
    if activity_id <= 0:
        raise ValueError("activity_id must be positive")
    if sample_interval is not None and not 1 <= sample_interval <= 10000:
        raise ValueError("sample_interval must be 1..10000")
    if not 2 <= max_points <= 1000:
        raise ValueError("max_points must be 2..1000")
    with mcp_data._connection() as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            activity = conn.execute("""SELECT activity_id, sport_group, start_local
                FROM garmin_activities WHERE activity_id = %s""", (activity_id,)).fetchone()
            if activity is None:
                return {"status": "not_found", "activity_id": activity_id, "points": []}
            columns = {row["column_name"] for row in conn.execute("""SELECT column_name
                FROM information_schema.columns WHERE table_name = 'garmin_samples'
                AND table_schema = current_schema() AND column_name IN ('latitude', 'longitude')""").fetchall()}
            raw_lat = "CASE WHEN jsonb_typeof(raw_json->'directLatitude')='number' THEN (raw_json->>'directLatitude')::double precision END"
            raw_lon = "CASE WHEN jsonb_typeof(raw_json->'directLongitude')='number' THEN (raw_json->>'directLongitude')::double precision END"
            lat = f"coalesce(latitude, {raw_lat})" if "latitude" in columns else raw_lat
            lon = f"coalesce(longitude, {raw_lon})" if "longitude" in columns else raw_lon
            valid = f"({lat}) BETWEEN -90 AND 90 AND ({lon}) BETWEEN -180 AND 180"
            totals = conn.execute(f"""SELECT count(*) AS sample_count,
                count(*) FILTER (WHERE {valid}) AS gps_point_count,
                min(sample_index) FILTER (WHERE {valid}) AS first_index,
                max(sample_index) FILTER (WHERE {valid}) AS last_index
                FROM garmin_samples WHERE activity_id = %s""", (activity_id,)).fetchone()
            if not totals["sample_count"]:
                return {"status": "not_collected", "activity_id": activity_id,
                        "points": [], "message": "No saved time-series samples"}
            if not totals["gps_point_count"]:
                return {"status": "no_gps_data", "activity_id": activity_id,
                        "points": [], "sample_count": totals["sample_count"]}
            step = sample_interval or max(1, (totals["last_index"] - totals["first_index"] + max_points) // max_points)
            rows = conn.execute(f"""SELECT sample_index, timestamp_utc,
                {lat} AS latitude, {lon} AS longitude, distance_m, elevation_m,
                speed_mps, heart_rate, power FROM garmin_samples
                WHERE activity_id = %s AND {valid}
                  AND (sample_index - %s) %% %s = 0
                ORDER BY sample_index LIMIT %s""",
                (activity_id, totals["first_index"], step, max_points + 1)).fetchall()
    truncated = len(rows) > max_points
    return {"status": "success", "activity_id": activity_id,
            "sport": activity["sport_group"], "start_local": mcp_data._jsonable(activity["start_local"]),
            "sample_count": totals["sample_count"], "gps_point_count": totals["gps_point_count"],
            "sample_interval": step, "truncated": truncated,
            "points": mcp_data._jsonable(rows[:max_points]),
            "units": {"latitude": "degrees", "longitude": "degrees",
                      "distance": "m", "elevation": "m", "speed": "m/s",
                      "heart_rate": "bpm", "power": "W"}}
