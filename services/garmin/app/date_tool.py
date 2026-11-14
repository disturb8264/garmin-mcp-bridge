"""MCP date lookup with an on-demand, private collector fallback."""

import os
import stat
from pathlib import Path

import httpx2 as httpx
import psycopg

from app import mcp_data
from app.date_query import validate_range


def _collector_token() -> str:
    path = Path(os.environ["MCP_COLLECTOR_TOKEN_FILE"])
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise RuntimeError("Collector token file must be private (mode 600)")
    return path.read_text(encoding="ascii").strip()


async def get_activities_by_date(start_date: str, end_date: str | None = None,
                                 sport: str = "all") -> dict:
    try:
        start, end = validate_range(start_date, end_date, sport)
    except ValueError as exc:
        return {"status": "invalid_request", "source": "database", "activities": [],
                "message": str(exc)}

    try:
        cached = mcp_data.activities_by_date(start, end, sport)
    except (psycopg.Error, RuntimeError):
        return {"status": "database_error", "source": "database", "activities": [],
                "message": "Date lookup database is unavailable"}

    # A single saved day follows the requested DB-first fast path. For ranges,
    # a row on one day does not prove the other days were collected.
    if cached["activities"] and (start == end or cached["coverage_complete"]):
        return {"status": "success", "source": "database",
                "activities": cached["activities"],
                "coverage_complete": cached["coverage_complete"]}
    if cached["coverage_complete"]:
        return {"status": "not_found", "source": "garmin", "activities": [],
                "coverage_complete": True}

    try:
        result = await _collect_range(start, end)
    except httpx.TimeoutException:
        return {"status": "timeout", "source": "garmin", "activities": [],
                "message": "Private collector did not finish within 85 seconds"}
    except (httpx.HTTPError, ValueError, OSError, KeyError, RuntimeError):
        return {"status": "service_error", "source": "garmin", "activities": [],
                "message": "Private collector request failed"}

    if result["status"] != "success":
        return {"status": result["status"], "source": "garmin", "activities": [],
                "message": result.get("message", "Collection failed")}
    try:
        fresh = mcp_data.activities_by_date(start, end, sport)
    except (psycopg.Error, RuntimeError):
        return {"status": "database_error", "source": "database", "activities": [],
                "message": "Saved activities could not be read"}
    if fresh["activities"]:
        return {"status": "success", "source": "garmin",
                "activities": fresh["activities"],
                "coverage_complete": fresh["coverage_complete"]}
    if fresh["coverage_complete"]:
        return {"status": "not_found", "source": "garmin", "activities": [],
                "coverage_complete": True}
    return {"status": "database_error", "source": "database", "activities": [],
            "message": "Collection finished without a coverage record"}


async def _collect_range(start, end) -> dict:
    url = os.getenv("MCP_COLLECTOR_URL", "")
    if not url:
        raise RuntimeError("Private collector is not configured")
    token = _collector_token()
    timeout = httpx.Timeout(85.0, connect=3.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            url,
            headers={"X-Collector-Internal-Token": token},
            json={"start_date": start.isoformat(), "end_date": end.isoformat()},
        )
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict) or "status" not in result:
        raise ValueError("Invalid collector result")
    return result
