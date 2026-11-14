"""Bounded, read-only queries exposed by the MCP server."""

import os
from datetime import date, datetime
from decimal import Decimal

import psycopg
from dotenv import dotenv_values
from psycopg.rows import dict_row

from app.config import ENV_PATH


def _setting(name: str, fallback: str = "") -> str:
    # dotenv_values does not export the Garmin credentials to this process.
    values = dotenv_values(ENV_PATH)
    return str(os.getenv(name) or values.get(name) or fallback)


def _connection():
    host = _setting("MCP_PGHOST", _setting("PGHOST"))
    database = _setting("MCP_PGDATABASE", _setting("PGDATABASE"))
    user = _setting("MCP_PGUSER")
    password = _setting("MCP_PGPASSWORD")
    if not all((host, database, user, password)):
        raise RuntimeError("MCP database is not configured; set MCP_PGUSER and MCP_PGPASSWORD")
    return psycopg.connect(
        host=host,
        port=int(_setting("MCP_PGPORT", _setting("PGPORT", "5432"))),
        dbname=database,
        user=user,
        password=password,
        connect_timeout=5,
        row_factory=dict_row,
        autocommit=True,
        options="-c default_transaction_read_only=on -c statement_timeout=5000",
    )


def _jsonable(value):
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _activity_id(value: int) -> int:
    if value <= 0:
        raise ValueError("activity_id must be positive")
    return value


SPORT_FILTERS = {"all", "running", "cycling", "swimming", "multisport"}


def list_activities(limit: int = 5, sport: str = "all") -> dict:
    if not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")
    if sport not in SPORT_FILTERS:
        raise ValueError("sport must be all, running, cycling, swimming or multisport")
    with _connection() as conn:
        rows = conn.execute(
            """SELECT activity_id, name, activity_type, sport_group, start_local, start_utc,
                      distance_m, duration_s, moving_duration_s,
                      average_pace_s_per_km, average_pace_s_per_100m,
                      average_speed_mps, average_hr, max_hr,
                      average_cadence, average_power, elevation_gain_m,
                      aerobic_te, anaerobic_te
               FROM garmin_activities
               WHERE (%s = 'all' OR sport_group = %s)
               ORDER BY start_utc DESC NULLS LAST, activity_id DESC
               LIMIT %s""",
            (sport, sport, limit),
        ).fetchall()
    return {"activities": _jsonable(rows), "count": len(rows), "sport": sport}


def activities_by_date(start: date, end: date, sport: str) -> dict:
    """Return local-date rows and whether every day was fully checked at Garmin."""
    with _connection() as conn:
        rows = conn.execute(
            """SELECT activity_id, name, activity_type, sport_group, start_local, start_utc,
                      distance_m, duration_s, moving_duration_s,
                      average_pace_s_per_km, average_pace_s_per_100m,
                      average_speed_mps, average_hr, max_hr,
                      average_cadence, average_power, elevation_gain_m,
                      aerobic_te, anaerobic_te
               FROM garmin_activities
               WHERE start_local >= %s::date AND start_local < (%s::date + interval '1 day')
                 AND (%s = 'all' OR sport_group = %s)
               ORDER BY start_local, activity_id""",
            (start, end, sport, sport),
        ).fetchall()
        covered_days = conn.execute(
            """SELECT count(*) AS n FROM garmin_date_coverage
               WHERE covered_date BETWEEN %s AND %s""",
            (start, end),
        ).fetchone()["n"]
    return {"activities": _jsonable(rows),
            "coverage_complete": covered_days == (end - start).days + 1}


def activity_details(activity_id: int) -> dict:
    activity_id = _activity_id(activity_id)
    with _connection() as conn:
        row = conn.execute(
            """SELECT activity_id, name, activity_type, sport_group, start_local, start_utc,
                      distance_m, duration_s, moving_duration_s,
                      average_pace_s_per_km, average_pace_s_per_100m, average_hr, max_hr,
                      average_cadence, average_stride_length, average_power,
                      elevation_gain_m, elevation_loss_m, average_speed_mps,
                      max_speed_mps, calories, aerobic_te, anaerobic_te,
                      hr_zones, collected_at
               FROM garmin_activities WHERE activity_id = %s""",
            (activity_id,),
        ).fetchone()
        if row is None:
            return {"found": False, "activity_id": activity_id}
        laps = conn.execute(
            "SELECT count(*) AS n FROM garmin_laps WHERE activity_id = %s", (activity_id,)
        ).fetchone()["n"]
        samples = conn.execute(
            "SELECT count(*) AS n FROM garmin_samples WHERE activity_id = %s", (activity_id,)
        ).fetchone()["n"]
    return {"found": True, "activity": _jsonable(row), "lap_count": laps, "sample_count": samples}


def activity_laps(activity_id: int) -> dict:
    activity_id = _activity_id(activity_id)
    with _connection() as conn:
        rows = conn.execute(
            """SELECT lap_number, distance_m, duration_s, average_pace_s_per_km,
                      average_pace_s_per_100m,
                      average_hr, max_hr, average_cadence, elevation_gain_m, lap_type
               FROM garmin_laps WHERE activity_id = %s ORDER BY lap_number""",
            (activity_id,),
        ).fetchall()
    return {"activity_id": activity_id, "laps": _jsonable(rows), "count": len(rows)}


def activity_samples(activity_id: int, offset: int = 0, limit: int = 100) -> dict:
    activity_id = _activity_id(activity_id)
    if offset < 0 or not 1 <= limit <= 200:
        raise ValueError("offset must be nonnegative and limit between 1 and 200")
    with _connection() as conn:
        total = conn.execute(
            "SELECT count(*) AS n FROM garmin_samples WHERE activity_id = %s", (activity_id,)
        ).fetchone()["n"]
        rows = conn.execute(
            """SELECT sample_index, timestamp_utc, elapsed_s, heart_rate,
                      speed_mps, distance_m, elevation_m, cadence, power
               FROM garmin_samples WHERE activity_id = %s
               ORDER BY sample_index LIMIT %s OFFSET %s""",
            (activity_id, limit, offset),
        ).fetchall()
    next_offset = offset + len(rows) if offset + len(rows) < total else None
    return {"activity_id": activity_id, "total": total, "offset": offset,
            "next_offset": next_offset, "samples": _jsonable(rows)}


def sync_status() -> dict:
    with _connection() as conn:
        history = conn.execute(
            """SELECT mode, started_at, completed_at, status,
                      found_count, saved_count, failed_count
               FROM garmin_sync_history ORDER BY id DESC LIMIT 1"""
        ).fetchone()
        latest = conn.execute(
            """SELECT activity_id, name, sport_group, start_utc, collected_at
               FROM garmin_activities ORDER BY start_utc DESC NULLS LAST,
               activity_id DESC LIMIT 1"""
        ).fetchone()
    return {"last_sync": _jsonable(history), "latest_activity": _jsonable(latest)}
