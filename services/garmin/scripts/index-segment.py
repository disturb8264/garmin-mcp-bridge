"""Populate one segment's cached efforts from saved GPS, in bounded batches."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.segment_store import refresh_segment


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("segment_id", type=int)
    parser.add_argument("--batch-size", type=int, default=20)
    args = parser.parse_args(argv)
    if args.segment_id <= 0 or not 1 <= args.batch_size <= 20:
        parser.error("Invalid segment_id or batch-size")
    while True:
        result = refresh_segment(args.segment_id, args.batch_size)
        print(f"status={result['status']} scanned={result.get('scanned_activities', 0)} "
              f"remaining={result.get('remaining_activities', '?')} "
              f"skipped={result.get('skipped_activities', 0)}")
        if result["status"] in ("busy", "not_found"):
            return 2
        if result["remaining_activities"] == 0:
            return 0 if result["status"] == "complete" else 1
        if result["scanned_activities"] == 0:
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
