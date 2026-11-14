"""Import Garmin activity history by month and resume from DB coverage."""

import argparse
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import database
from app.collector import collect
from app.config import load_config
from app.garmin_client import GarminReader
from app.models import sport_groups


LOG = logging.getLogger("backfill")


def months(start: date, end: date):
    current = start
    while current <= end:
        next_month = date(current.year + (current.month == 12), current.month % 12 + 1, 1)
        finish = min(end, next_month - timedelta(days=1))
        yield current, finish
        current = finish + timedelta(days=1)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Backfill supported Garmin activities into PostgreSQL")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2000, 1, 1))
    today = datetime.now(ZoneInfo(os.getenv("TZ", "Asia/Seoul"))).date()
    parser.add_argument("--end", type=date.fromisoformat, default=today - timedelta(days=1))
    parser.add_argument("--pause", type=float, default=1.0, help="Seconds between activity detail requests")
    parser.add_argument("--max-months", type=int, help="Stop after this many newly processed months")
    args = parser.parse_args(argv)
    if args.end >= today:
        parser.error("Backfill end must be before today; use the MCP date tool for today's activities")
    if args.end < args.start or args.pause < 0 or (args.max_months is not None and args.max_months < 1):
        parser.error("Invalid date range, pause, or max-months")

    config = load_config()
    if not config.db_ready:
        parser.error("Set PGHOST, PGDATABASE, PGUSER and PGPASSWORD for the writer role")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    reader = GarminReader(config)
    reader.login()
    groups = sport_groups(reader.activity_types())
    processed = total_found = total_saved = 0
    with database.connect(config) as conn:
        database.ensure_schema(conn)
        for start, end in months(args.start, args.end):
            if database.date_range_covered(conn, start, end):
                LOG.info("Already covered %s to %s", start, end)
                continue
            LOG.info("Collecting %s to %s", start, end)
            try:
                found, saved, _ = collect(
                    reader, "range", 0, start, end, False, conn, config.lookback_days,
                    strict=True, groups=groups, pause_seconds=args.pause,
                )
            except Exception as exc:
                LOG.error("Stopped at %s to %s (%s); rerun to resume", start, end, type(exc).__name__)
                return 1
            database.mark_date_coverage(conn, start, end)
            processed += 1
            total_found += found
            total_saved += saved
            LOG.info("Completed %s to %s: %s supported, %s saved", start, end, found, saved)
            if args.max_months is not None and processed >= args.max_months:
                break
    LOG.info("Backfill finished: %s months, %s supported, %s saved", processed, total_found, total_saved)
    return 0


if __name__ == "__main__":
    sys.exit(main())
