"""One bounded on-demand collection job; stdout contains only a safe JSON result."""

import json
import sys

import psycopg
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from app import database
from app.collector import collect
from app.config import load_config
from app.date_query import validate_range
from app.garmin_client import (
    GarminAuthError,
    GarminConnectionError,
    GarminRateLimitError,
    GarminReader,
    MFARequired,
)


def run(start_text: str, end_text: str) -> dict:
    try:
        start, end = validate_range(start_text, end_text)
        config = load_config()
        if not config.db_ready:
            return {"status": "database_error", "message": "Collector database is not configured"}
        reader = GarminReader(config)
        reader.login()
        with database.connect(config, statement_timeout_ms=10000) as conn:
            database.ensure_schema(conn)
            found, saved, failed = collect(
                reader, "range", 0, start, end, False, conn, config.lookback_days,
                strict=True,
            )
            if failed:
                return {"status": "api_error", "message": "One or more Garmin activities failed to collect"}
            database.mark_date_coverage(conn, start, end)
        return {"status": "success", "found_count": found, "saved_count": saved}
    except (GarminAuthError, MFARequired, GarminConnectAuthenticationError):
        return {"status": "authentication_error", "message": "Garmin authentication failed or MFA is required"}
    except (GarminRateLimitError, GarminConnectTooManyRequestsError):
        return {"status": "api_error", "message": "Garmin rate limit reached"}
    except (GarminConnectionError, GarminConnectConnectionError):
        return {"status": "api_error", "message": "Garmin API connection failed"}
    except (TimeoutError, psycopg.errors.QueryCanceled):
        return {"status": "timeout", "message": "Garmin or database operation timed out"}
    except psycopg.Error:
        return {"status": "database_error", "message": "Collector database operation failed"}
    except Exception:
        return {"status": "api_error", "message": "Garmin activity collection failed"}


def main() -> None:
    if len(sys.argv) != 3:
        result = {"status": "invalid_request", "message": "Expected start_date and end_date"}
    else:
        result = run(sys.argv[1], sys.argv[2])
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
