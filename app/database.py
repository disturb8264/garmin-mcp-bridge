"""PostgreSQL persistence with one transaction per activity."""

from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from app.config import Config, ROOT


def connect(config: Config, statement_timeout_ms: int | None = None):
    return psycopg.connect(
        host=config.pg_host,
        port=config.pg_port,
        dbname=config.pg_database,
        user=config.pg_user,
        password=config.pg_password,
        connect_timeout=10,
        autocommit=True,
        options=(f"-c statement_timeout={statement_timeout_ms}" if statement_timeout_ms else ""),
    )


def ensure_schema(conn) -> None:
    schema = (ROOT / "sql" / "schema.sql").read_text(encoding="utf-8")
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (-8620201,))
        conn.execute(schema)
        conn.execute(
            "INSERT INTO garmin_schema_migrations (version) VALUES (1) ON CONFLICT DO NOTHING"
        )
        applied = {
            row[0] for row in conn.execute("SELECT version FROM garmin_schema_migrations").fetchall()
        }
        for path in sorted((ROOT / "sql" / "migrations").glob("[0-9][0-9][0-9]_*.sql")):
            version = int(path.name.split("_", 1)[0])
            if version in applied:
                continue
            if version <= 1:
                raise ValueError(f"Invalid migration version: {path.name}")
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO garmin_schema_migrations (version) VALUES (%s)", (version,))


def latest_activity_date(conn):
    row = conn.execute("SELECT max(start_utc)::date FROM garmin_activities").fetchone()
    return row[0]


def mark_date_coverage(conn, start, end) -> None:
    with conn.transaction():
        conn.execute(
            """INSERT INTO garmin_date_coverage (covered_date)
               SELECT day::date FROM generate_series(%s::date, %s::date, interval '1 day') AS day
               ON CONFLICT (covered_date) DO UPDATE SET checked_at = now()""",
            (start, end),
        )


def date_range_covered(conn, start, end) -> bool:
    row = conn.execute(
        "SELECT count(*) FROM garmin_date_coverage WHERE covered_date BETWEEN %s AND %s",
        (start, end),
    ).fetchone()
    return row[0] == (end - start).days + 1


def pending_summaries(conn) -> list[dict]:
    return [row[0] for row in conn.execute(
        "SELECT summary_json FROM garmin_failed_activities ORDER BY last_failed_at"
    ).fetchall()]


def record_failure(conn, summary: dict) -> None:
    with conn.transaction():
        conn.execute(
            """INSERT INTO garmin_failed_activities (activity_id, summary_json)
               VALUES (%s, %s) ON CONFLICT (activity_id) DO UPDATE SET
               summary_json = EXCLUDED.summary_json, last_failed_at = now(),
               attempt_count = garmin_failed_activities.attempt_count + 1""",
            (summary["activityId"], Jsonb(summary)),
        )


def start_history(conn, mode: str) -> int:
    with conn.transaction():
        row = conn.execute(
            "INSERT INTO garmin_sync_history (mode, status) VALUES (%s, 'running') RETURNING id",
            (mode,),
        ).fetchone()
    return row[0]


def finish_history(conn, history_id: int, status: str, found: int, saved: int, failed: int, error=None) -> None:
    with conn.transaction():
        conn.execute(
            """UPDATE garmin_sync_history SET completed_at = now(), status = %s,
               found_count = %s, saved_count = %s, failed_count = %s, error_message = %s
               WHERE id = %s""",
            (status, found, saved, failed, error, history_id),
        )


def _insert(conn, table: str, row: dict, conflict: str) -> None:
    columns = list(row)
    values = [Jsonb(value) if key in ("raw_json", "hr_zones") and value is not None else value
              for key, value in row.items()]
    stmt = sql.SQL("INSERT INTO {} ({}) VALUES ({}) {}").format(
        sql.Identifier(table),
        sql.SQL(", ").join(map(sql.Identifier, columns)),
        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        sql.SQL(conflict),
    )
    conn.execute(stmt, values)


def save_activity(conn, activity: dict, laps: list[dict], samples: list[dict]) -> None:
    with conn.transaction():
        activity_id = activity["activity_id"]
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (activity_id,))
        updates = ", ".join(f"{column} = EXCLUDED.{column}" for column in activity if column != "activity_id")
        updates += ", collected_at = now()"
        _insert(conn, "garmin_activities", activity, f"ON CONFLICT (activity_id) DO UPDATE SET {updates}")
        for lap in laps:
            columns = [key for key in lap if key not in ("activity_id", "lap_number")]
            preserve = ", ".join(
                f"{column} = COALESCE(EXCLUDED.{column}, garmin_laps.{column})"
                for column in columns if column != "raw_json"
            )
            preserve += ", raw_json = garmin_laps.raw_json || jsonb_strip_nulls(EXCLUDED.raw_json)"
            _insert(conn, "garmin_laps", lap,
                    f"ON CONFLICT (activity_id, lap_number) DO UPDATE SET {preserve}")
        for sample in samples:
            columns = [key for key in sample if key not in ("activity_id", "sample_index")]
            preserve = ", ".join(
                f"{column} = COALESCE(EXCLUDED.{column}, garmin_samples.{column})"
                for column in columns if column != "raw_json"
            )
            preserve += ", raw_json = garmin_samples.raw_json || jsonb_strip_nulls(EXCLUDED.raw_json)"
            _insert(conn, "garmin_samples", sample,
                    f"ON CONFLICT (activity_id, sample_index) DO UPDATE SET {preserve}")
        conn.execute("DELETE FROM garmin_failed_activities WHERE activity_id = %s", (activity_id,))
