"""Command line entry point."""

import argparse
import logging
import sys
from datetime import date

from app import database
from app.collector import collect
from app.config import load_config
from app.garmin_client import GarminReader, MFARequired


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Collect Garmin running, cycling, swimming and multisport activities")
    parser.add_argument("--mode", choices=("recent", "range", "sync"), required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit must be positive")
    if args.mode == "range" and (args.start is None or args.end is None):
        parser.error("--mode range requires --start and --end")
    if args.start and args.end and args.start > args.end:
        parser.error("--start must be on or before --end")
    if args.mode == "sync" and args.dry_run:
        parser.error("--mode sync requires PostgreSQL and cannot use --dry-run")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        config = load_config()
        logging.basicConfig(level=getattr(logging, config.log_level, logging.INFO),
                            format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        logging.getLogger("garminconnect").setLevel(logging.ERROR)
        if not args.dry_run and not config.db_ready:
            raise ValueError("Set PGHOST, PGDATABASE, PGUSER and PGPASSWORD in .env, or use --dry-run")
        reader = GarminReader(config)
        reader.login()
        if args.dry_run:
            _, _, failed = collect(reader, args.mode, args.limit, args.start, args.end,
                                   True, None, config.lookback_days)
        else:
            with database.connect(config) as conn:
                database.ensure_schema(conn)
                _, _, failed = collect(reader, args.mode, args.limit, args.start, args.end,
                                       False, conn, config.lookback_days)
        return 1 if failed else 0
    except (ValueError, MFARequired, RuntimeError) as exc:
        logging.error("%s", exc)
        return 2
    except Exception as exc:
        logging.error("Collection failed: %s", type(exc).__name__)
        return 1


if __name__ == "__main__":
    sys.exit(main())
