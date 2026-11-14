"""Read-only, bounded searches and SQL summaries of saved Garmin activities."""

from datetime import date

from app import mcp_data


SPORTS = {"all", "running", "cycling", "swimming", "multisport"}
GROUPS = {"year": "year", "month": "month", "week": "week"}
SORTS = {
    "newest": "start_local DESC NULLS LAST, activity_id DESC",
    "oldest": "start_local ASC NULLS LAST, activity_id ASC",
    "distance": "distance_m DESC NULLS LAST, activity_id DESC",
    "duration": "duration_s DESC NULLS LAST, activity_id DESC",
}
ACTIVITY_FIELDS = """activity_id, name, activity_type, sport_group, start_local,
    distance_m, duration_s, moving_duration_s, average_pace_s_per_km,
    average_pace_s_per_100m, average_speed_mps, average_hr, average_cadence,
    average_power, elevation_gain_m"""


def _dates(start_date: str | None, end_date: str | None):
    try:
        start = date.fromisoformat(start_date) if start_date else None
        end = date.fromisoformat(end_date) if end_date else None
    except (TypeError, ValueError):
        raise ValueError("Dates must use YYYY-MM-DD") from None
    if start and end and start > end:
        raise ValueError("start_date must be on or before end_date")
    return start, end


def _filters(sport, start, end, *, name=None, min_distance_m=None,
             max_distance_m=None, min_duration_s=None, max_duration_s=None):
    if sport not in SPORTS:
        raise ValueError("Invalid sport")
    clauses, args = ["TRUE"], []
    if sport != "all":
        clauses.append("sport_group = %s")
        args.append(sport)
    if start:
        clauses.append("start_local >= %s::date")
        args.append(start)
    if end:
        clauses.append("start_local < (%s::date + interval '1 day')")
        args.append(end)
    if name:
        if len(name) > 100:
            raise ValueError("name must be at most 100 characters")
        escaped = name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clauses.append("name ILIKE %s ESCAPE '\\'")
        args.append(f"%{escaped}%")
    for column, minimum, maximum in (
        ("distance_m", min_distance_m, max_distance_m),
        ("duration_s", min_duration_s, max_duration_s),
    ):
        if minimum is not None and minimum < 0 or maximum is not None and maximum < 0:
            raise ValueError(f"{column} bounds must be nonnegative")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError(f"{column} minimum exceeds maximum")
        if minimum is not None:
            clauses.append(f"{column} >= %s")
            args.append(minimum)
        if maximum is not None:
            clauses.append(f"{column} <= %s")
            args.append(maximum)
    return " AND ".join(clauses), args


def _coverage(conn, start, end):
    bounds = conn.execute("""SELECT
        (SELECT min(covered_date) FROM garmin_date_coverage) AS covered_first,
        (SELECT max(covered_date) FROM garmin_date_coverage) AS covered_last,
        (SELECT min(start_local)::date FROM garmin_activities) AS activity_first,
        (SELECT max(start_local)::date FROM garmin_activities) AS activity_last""").fetchone()
    first = start or min((d for d in (bounds["covered_first"], bounds["activity_first"]) if d), default=None)
    last = end or max((d for d in (bounds["covered_last"], bounds["activity_last"]) if d), default=None)
    if first is None or last is None or first > last:
        checked = total = 0
    else:
        checked = conn.execute("""SELECT count(*) AS n FROM garmin_date_coverage
            WHERE covered_date BETWEEN %s AND %s""", (first, last)).fetchone()["n"]
        total = (last - first).days + 1
    return {
        "window_start": first.isoformat() if first else None,
        "window_end": last.isoformat() if last else None,
        "checked_days": checked,
        "window_days": total,
        "complete_for_window": bool(total and checked == total and start is not None and end is not None),
        "start_bound_explicit": start is not None,
        "end_bound_explicit": end is not None,
        "account_lifetime_verified": False,
    }


def _data_status(count, coverage):
    if count:
        return "saved_data" if coverage["complete_for_window"] else "partial_collection"
    return "no_matching_activities" if coverage["complete_for_window"] else "not_fully_collected"


def search_activities(sport="all", start_date=None, end_date=None, name=None,
                      min_distance_m=None, max_distance_m=None,
                      min_duration_s=None, max_duration_s=None,
                      sort="newest", offset=0, limit=20):
    if sort not in SORTS:
        raise ValueError("Invalid sort")
    if not 0 <= offset <= 100000 or not 1 <= limit <= 100:
        raise ValueError("offset must be 0..100000 and limit must be 1..100")
    start, end = _dates(start_date, end_date)
    where, args = _filters(sport, start, end, name=name,
                           min_distance_m=min_distance_m, max_distance_m=max_distance_m,
                           min_duration_s=min_duration_s, max_duration_s=max_duration_s)
    with mcp_data._connection() as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            total = conn.execute(f"SELECT count(*) AS n FROM garmin_activities WHERE {where}", args).fetchone()["n"]
            rows = conn.execute(f"""SELECT {ACTIVITY_FIELDS} FROM garmin_activities
                WHERE {where} ORDER BY {SORTS[sort]} LIMIT %s OFFSET %s""", (*args, limit, offset)).fetchall()
            coverage = _coverage(conn, start, end)
    return {"activities": mcp_data._jsonable(rows), "total": total, "offset": offset,
            "limit": limit, "next_offset": offset + len(rows) if offset + len(rows) < total else None,
            "coverage": coverage, "data_status": _data_status(total, coverage),
            "units": {"distance": "m", "duration": "s",
            "pace_running": "s/km", "pace_swimming": "s/100m", "speed": "m/s"}}


def _group_rows(conn, where, args, group_by, period_offset, period_limit):
    granularity = GROUPS[group_by]
    rows = conn.execute(f"""SELECT date_trunc('{granularity}', start_local)::date AS period,
        count(*) AS activity_count, count(distance_m) AS distance_count,
        sum(distance_m) AS total_distance_m, avg(distance_m) AS avg_distance_m,
        sum(duration_s) AS total_duration_s,
        max(distance_m) AS longest_distance_m,
        min(average_pace_s_per_km) FILTER (WHERE average_pace_s_per_km > 0)
          AS fastest_activity_average_running_pace_s_per_km,
        min(average_pace_s_per_100m) FILTER (WHERE average_pace_s_per_100m > 0)
          AS fastest_activity_average_swimming_pace_s_per_100m,
        max(average_speed_mps) AS fastest_activity_average_speed_mps,
        avg(average_pace_s_per_km) AS mean_running_pace_s_per_km,
        sum(distance_m * average_pace_s_per_km)
          / nullif(sum(distance_m) FILTER (WHERE average_pace_s_per_km IS NOT NULL), 0)
          AS distance_weighted_running_pace_s_per_km,
        avg(average_pace_s_per_100m) AS mean_swimming_pace_s_per_100m,
        sum(distance_m * average_pace_s_per_100m)
          / nullif(sum(distance_m) FILTER (WHERE average_pace_s_per_100m IS NOT NULL), 0)
          AS distance_weighted_swimming_pace_s_per_100m,
        avg(average_speed_mps) AS mean_speed_mps,
        sum(distance_m) FILTER (WHERE average_speed_mps > 0)
          / nullif(sum(distance_m / average_speed_mps) FILTER (WHERE average_speed_mps > 0), 0)
          AS aggregate_speed_mps,
        avg(average_hr) AS mean_hr_bpm, count(average_hr) AS hr_count,
        avg(average_power) AS mean_power_w, count(average_power) AS power_count,
        avg(average_cadence) AS mean_cadence, count(average_cadence) AS cadence_count,
        sum(elevation_gain_m) AS total_elevation_gain_m,
        count(average_pace_s_per_km) AS running_pace_count,
        count(average_pace_s_per_100m) AS swimming_pace_count,
        count(average_speed_mps) AS speed_count
        FROM garmin_activities WHERE {where} AND start_local IS NOT NULL
        GROUP BY 1 ORDER BY 1 LIMIT %s OFFSET %s""",
        (*args, period_limit + 1, period_offset)).fetchall()
    has_more = len(rows) > period_limit
    return rows[:period_limit], period_offset + period_limit if has_more else None


def get_sport_history(sport, start_date=None, end_date=None, group_by="year",
                      period_offset=0, period_limit=120):
    if group_by not in GROUPS:
        raise ValueError("Invalid group_by")
    if not 0 <= period_offset <= 100000 or not 1 <= period_limit <= 120:
        raise ValueError("period_offset must be 0..100000 and period_limit must be 1..120")
    start, end = _dates(start_date, end_date)
    where, args = _filters(sport, start, end)
    with mcp_data._connection() as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            summary = conn.execute(f"""SELECT min(start_local)::date AS first_recorded_date,
                max(start_local)::date AS last_recorded_date, count(*) AS activity_count,
                coalesce(sum(distance_m), 0) AS total_distance_m,
                coalesce(sum(duration_s), 0) AS total_duration_s
                FROM garmin_activities WHERE {where}""", args).fetchone()
            longest = conn.execute(f"""SELECT activity_id, start_local, distance_m FROM garmin_activities
                WHERE {where} AND distance_m IS NOT NULL ORDER BY distance_m DESC, activity_id DESC LIMIT 1""", args).fetchone()
            pace_column = {"running": "average_pace_s_per_km", "swimming": "average_pace_s_per_100m"}.get(sport)
            if pace_column:
                best = conn.execute(f"""SELECT activity_id, start_local, distance_m,
                    {pace_column} AS average_pace_s FROM garmin_activities
                    WHERE {where} AND {pace_column} > 0
                    ORDER BY {pace_column}, activity_id LIMIT 1""", args).fetchone()
                best_label = "fastest_activity_average_pace_s_per_km" if sport == "running" else "fastest_activity_average_pace_s_per_100m"
            else:
                best = conn.execute(f"""SELECT activity_id, start_local, distance_m,
                    average_speed_mps FROM garmin_activities WHERE {where} AND average_speed_mps > 0
                    ORDER BY average_speed_mps DESC, activity_id LIMIT 1""", args).fetchone()
                best_label = "fastest_activity_average_speed_mps"
            best_100m_lap = None
            if sport == "swimming":
                best_100m_lap = conn.execute(f"""SELECT l.activity_id, a.start_local::date AS activity_date,
                    l.lap_number, l.distance_m, l.duration_s
                    FROM garmin_laps l JOIN garmin_activities a USING (activity_id)
                    WHERE {where} AND l.distance_m BETWEEN 99 AND 101 AND l.duration_s > 0
                    ORDER BY l.duration_s, l.activity_id, l.lap_number LIMIT 1""", args).fetchone()
            periods, next_offset = _group_rows(conn, where, args, group_by, period_offset, period_limit)
            coverage = _coverage(conn, start, end)
    return {"sport": sport, "group_by": group_by, "summary": mcp_data._jsonable(summary),
            "data_status": _data_status(summary["activity_count"], coverage),
            "longest_activity": mcp_data._jsonable(longest),
            "best_record": {"metric": best_label, "activity": mcp_data._jsonable(best),
                            "basis": "saved activity average; not a timed segment or 100m split"},
            "best_measured_100m_lap": mcp_data._jsonable(best_100m_lap),
            "periods": mcp_data._jsonable(periods), "period_offset": period_offset,
            "period_limit": period_limit, "next_period_offset": next_offset,
            "coverage": coverage,
            "units": {"distance": "m", "duration": "s", "pace_running": "s/km",
                      "pace_swimming": "s/100m", "speed": "m/s", "heart_rate": "bpm",
                      "power": "W"}}


def _matched_heart_rate(conn, where, args):
    """Compare early/late HR only within the same pace and distance bands."""
    return conn.execute(f"""WITH eligible AS (
        SELECT average_hr, average_pace_s_per_km,
          floor(average_pace_s_per_km / 15)::int AS pace_band,
          CASE WHEN distance_m < 5000 THEN 'under_5km'
               WHEN distance_m < 10000 THEN '5_10km'
               WHEN distance_m < 20000 THEN '10_20km' ELSE '20km_plus' END AS distance_band,
          ntile(2) OVER (ORDER BY start_local, activity_id) AS half
        FROM garmin_activities WHERE {where} AND sport_group = 'running'
          AND average_hr IS NOT NULL AND average_pace_s_per_km > 0 AND distance_m >= 1000
    ), bands AS (
        SELECT pace_band, distance_band,
          count(*) FILTER (WHERE half = 1) AS early_count,
          count(*) FILTER (WHERE half = 2) AS late_count,
          avg(average_hr) FILTER (WHERE half = 1) AS early_hr_bpm,
          avg(average_hr) FILTER (WHERE half = 2) AS late_hr_bpm
        FROM eligible GROUP BY pace_band, distance_band
    ) SELECT pace_band * 15 AS pace_band_start_s_per_km, distance_band,
        early_count, late_count, early_hr_bpm, late_hr_bpm,
        late_hr_bpm - early_hr_bpm AS hr_change_bpm
      FROM bands WHERE early_count >= 2 AND late_count >= 2
      ORDER BY distance_band, pace_band LIMIT 30""", args).fetchall()


def get_sport_progress(sport, start_date=None, end_date=None, group_by="month",
                       period_offset=0, period_limit=120):
    if group_by not in GROUPS:
        raise ValueError("Invalid group_by")
    if not 0 <= period_offset <= 100000 or not 1 <= period_limit <= 120:
        raise ValueError("period_offset must be 0..100000 and period_limit must be 1..120")
    start, end = _dates(start_date, end_date)
    where, args = _filters(sport, start, end)
    with mcp_data._connection() as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            total = conn.execute(f"SELECT count(*) AS n FROM garmin_activities WHERE {where}", args).fetchone()["n"]
            periods, next_offset = _group_rows(conn, where, args, group_by, period_offset, period_limit)
            matched = _matched_heart_rate(conn, where, args) if sport == "running" else []
            swim_detail = []
            swim_detail_available = False
            if sport == "swimming":
                count = conn.execute("""SELECT count(*) AS n FROM information_schema.columns
                    WHERE table_schema = current_schema() AND table_name = 'garmin_activities'
                    AND column_name IN ('pool_length_m', 'average_swolf', 'total_strokes')""").fetchone()["n"]
                swim_detail_available = count == 3
                if swim_detail_available and periods:
                    granularity = GROUPS[group_by]
                    swim_detail = conn.execute(f"""SELECT date_trunc('{granularity}', start_local)::date AS period,
                        pool_length_m, count(*) AS activity_count,
                        avg(average_swolf) AS mean_swolf, count(average_swolf) AS swolf_count,
                        sum(total_strokes) AS total_strokes, count(total_strokes) AS stroke_count
                        FROM garmin_activities WHERE {where} AND sport_group = 'swimming'
                        AND pool_length_m IS NOT NULL
                        AND date_trunc('{granularity}', start_local)::date = ANY(%s::date[])
                        GROUP BY 1, 2 ORDER BY 1, 2""",
                        (*args, [row["period"] for row in periods])).fetchall()
            coverage = _coverage(conn, start, end)
    return {"sport": sport, "group_by": group_by, "periods": mcp_data._jsonable(periods),
            "activity_count": total, "data_status": _data_status(total, coverage),
            "period_offset": period_offset, "period_limit": period_limit,
            "next_period_offset": next_offset,
            "matched_pace_heart_rate": mcp_data._jsonable(matched),
            "swim_detail_by_pool_length": mcp_data._jsonable(swim_detail),
            "swim_detail_available": swim_detail_available,
            "method": {"pace": "arithmetic and distance-weighted activity averages; no 100m split inference",
                       "speed": "arithmetic activity average and aggregate distance/time from positive activity average speed",
                       "heart_rate_comparison": "early vs late half, same 15 s/km pace band and distance band; at least 2 activities per half",
                       "missing_metrics": "NULL excluded from metric averages; *_count gives contributing activities",
                       "swim_detail": "SWOLF grouped by known pool length; unverified pool units are excluded"},
            "coverage": coverage, "units": {"distance": "m", "duration": "s",
            "pace_running": "s/km", "pace_swimming": "s/100m", "speed": "m/s",
            "heart_rate": "bpm", "power": "W", "elevation_gain": "m"}}
