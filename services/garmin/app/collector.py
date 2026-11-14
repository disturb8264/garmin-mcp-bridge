"""Run collection and keep failures isolated by activity."""

import logging
import time
from datetime import date, timedelta

from app import database
from app.garmin_client import GarminReader
from app.models import activity_row, classify_activity, lap_rows, sample_rows, sport_groups
from garminconnect import GarminConnectAuthenticationError, GarminConnectTooManyRequestsError


LOG = logging.getLogger(__name__)


def select_summaries(reader: GarminReader, mode: str, limit: int, start: date | None,
                     end: date | None, conn, lookback_days: int) -> list[dict]:
    if mode == "recent":
        return reader.recent(limit)
    if mode == "range":
        return reader.date_range(start.isoformat(), end.isoformat())
    latest = database.latest_activity_date(conn)
    today = date.today()
    first_day = (min(latest, today) if latest else today) - timedelta(days=lookback_days)
    LOG.info("Syncing Garmin activities from %s through %s", first_day, today)
    current = reader.date_range(first_day.isoformat(), today.isoformat())
    pending = database.pending_summaries(conn)
    by_id = {item["activityId"]: item for item in pending + current}
    return list(by_id.values())


def collect(reader: GarminReader, mode: str, limit: int, start: date | None,
            end: date | None, dry_run: bool, conn, lookback_days: int,
            strict: bool = False, groups: dict | None = None,
            pause_seconds: float = 0) -> tuple[int, int, int]:
    history_id = None
    if conn is not None:
        history_id = database.start_history(conn, mode)
    found = saved = failed = 0
    try:
        summaries = select_summaries(reader, mode, limit, start, end, conn, lookback_days)
        groups = groups if groups is not None else sport_groups(reader.activity_types()) if summaries else {}
        supported = [(item, classify_activity(item, groups)) for item in summaries]
        supported = [(item, group) for item, group in supported if group]
        found = len(supported)
        LOG.info("Found %s supported activities among %s activities", found, len(summaries))
        for index, (summary, group) in enumerate(supported):
            if index and pause_seconds:
                time.sleep(pause_seconds)
            activity_id = summary.get("activityId")
            try:
                activity = reader.activity(activity_id)
                details = reader.details(activity_id)
                laps_response = reader.laps(activity_id)
                zones = reader.heart_rate_zones(activity_id)
                row = activity_row(summary, activity, zones, details, group)
                laps = lap_rows(activity_id, laps_response, group)
                samples = sample_rows(activity_id, details)
                if not samples:
                    LOG.info("No time series samples for activity %s", activity_id)
                if dry_run:
                    print(f"{activity_id} | {group} | {row['name']} | {row['start_local']} | "
                          f"{row['distance_m']} m | laps={len(laps)} | samples={len(samples)}")
                else:
                    database.save_activity(conn, row, laps, samples)
                saved += 1
            except (GarminConnectAuthenticationError, GarminConnectTooManyRequestsError):
                raise
            except Exception:
                failed += 1
                if conn is not None and activity_id is not None:
                    database.record_failure(conn, summary)
                LOG.error("Failed to collect activity %s; it can be retried on the next run", activity_id)
                if strict:
                    raise
        if history_id is not None:
            database.finish_history(conn, history_id, "partial" if failed else "completed",
                                    found, saved, failed)
        return found, saved, failed
    except Exception:
        if history_id is not None:
            database.finish_history(conn, history_id, "failed", found, saved, failed,
                                    "Collection stopped before completion")
        raise
