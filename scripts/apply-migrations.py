"""Apply additive PostgreSQL migrations after the historical backfill finishes."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import database
from app.config import load_config


def main() -> int:
    config = load_config()
    if not config.db_ready:
        print("Database writer settings are required", file=sys.stderr)
        return 2
    with database.connect(config, statement_timeout_ms=30000) as conn:
        running = conn.execute("""SELECT count(*) FROM garmin_sync_history
            WHERE status = 'running' AND started_at > now() - interval '24 hours'""").fetchone()[0]
        if running:
            print("Collection is active; retry migrations after it finishes", file=sys.stderr)
            return 2
        database.ensure_schema(conn)
        versions = [row[0] for row in conn.execute(
            "SELECT version FROM garmin_schema_migrations ORDER BY version").fetchall()]
    print("Applied schema versions: " + ", ".join(map(str, versions)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
