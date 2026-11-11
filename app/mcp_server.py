"""Private Streamable HTTP MCP server for saved and on-demand Garmin activities."""

import hmac
import asyncio
import os
import stat
from pathlib import Path
from typing import Annotated, Any, Literal

import uvicorn
import psycopg
import httpx2 as httpx
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.responses import JSONResponse

from app import date_tool, mcp_analysis, mcp_data, mcp_route, segment_store, segment_tool
from app.config import ROOT


READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
COLLECTS_DATA = ToolAnnotations(readOnlyHint=False, openWorldHint=True)
WRITES_DB = ToolAnnotations(readOnlyHint=False, openWorldHint=False)
mcp = MCPServer(
    "Garmin Activities",
    instructions=(
        "Search saved Garmin running, cycling, swimming and multisport activities in PostgreSQL. "
        "Use get_sync_status to check freshness when a user asks about a just-finished activity. "
        "Distances are meters, durations and paces are seconds (per km for running, per 100m for swimming), and speeds are m/s. "
        "get_activities_by_date checks saved data first and can collect missing dates from Garmin."
        " Search and history tools use only saved PostgreSQL data; check coverage before treating a first record or trend as complete."
        " Segment registration and indexing change only the local database and do not call Garmin."
    ),
)


def _read_query(function, *args):
    try:
        return function(*args)
    except (RuntimeError, ValueError) as exc:
        raise ToolError(str(exc)) from None
    except psycopg.Error:
        raise ToolError("Garmin database is unavailable or the schema is missing") from None


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def list_activities(
    limit: Annotated[int, Field(ge=1, le=20)] = 5,
    sport: Literal["all", "running", "cycling", "swimming", "multisport"] = "all",
) -> dict[str, Any]:
    """List up to 20 recent activities, optionally filtered by sport, with distance and key metrics."""
    return _read_query(mcp_data.list_activities, limit, sport)


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_activity(activity_id: Annotated[int, Field(gt=0)]) -> dict[str, Any]:
    """Get one saved activity summary, heart-rate zones, and lap/sample counts by Garmin Activity ID."""
    return _read_query(mcp_data.activity_details, activity_id)


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_activity_laps(activity_id: Annotated[int, Field(gt=0)]) -> dict[str, Any]:
    """Get ordered lap splits for a saved activity by Garmin Activity ID."""
    return _read_query(mcp_data.activity_laps, activity_id)


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_activity_samples(
    activity_id: Annotated[int, Field(gt=0)],
    offset: Annotated[int, Field(ge=0)] = 0,
    limit: Annotated[int, Field(ge=1, le=200)] = 100,
) -> dict[str, Any]:
    """Get a bounded page of original time-series samples; use next_offset for more."""
    return _read_query(mcp_data.activity_samples, activity_id, offset, limit)


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_sync_status() -> dict[str, Any]:
    """Get the last collector run and newest saved activity to check data freshness."""
    return _read_query(mcp_data.sync_status)


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def search_activities(
    sport: Literal["all", "running", "cycling", "swimming", "multisport"] = "all",
    start_date: str | None = None,
    end_date: str | None = None,
    name: str | None = None,
    min_distance_m: float | None = None,
    max_distance_m: float | None = None,
    min_duration_s: float | None = None,
    max_duration_s: float | None = None,
    sort: Literal["newest", "oldest", "distance", "duration"] = "newest",
    offset: Annotated[int, Field(ge=0, le=100000)] = 0,
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    """Search saved activities with filters, sort order, and bounded pages; never calls Garmin."""
    return _read_query(mcp_analysis.search_activities, sport, start_date, end_date, name,
                       min_distance_m, max_distance_m, min_duration_s, max_duration_s,
                       sort, offset, limit)


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_sport_history(
    sport: Literal["all", "running", "cycling", "swimming", "multisport"],
    start_date: str | None = None,
    end_date: str | None = None,
    group_by: Literal["year", "month", "week"] = "year",
    period_offset: Annotated[int, Field(ge=0, le=100000)] = 0,
    period_limit: Annotated[int, Field(ge=1, le=120)] = 120,
) -> dict[str, Any]:
    """Summarize saved sport history in PostgreSQL, including first recorded date and grouped totals."""
    return _read_query(mcp_analysis.get_sport_history, sport, start_date, end_date,
                       group_by, period_offset, period_limit)


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_sport_progress(
    sport: Literal["all", "running", "cycling", "swimming", "multisport"],
    start_date: str | None = None,
    end_date: str | None = None,
    group_by: Literal["year", "month", "week"] = "month",
    period_offset: Annotated[int, Field(ge=0, le=100000)] = 0,
    period_limit: Annotated[int, Field(ge=1, le=120)] = 120,
) -> dict[str, Any]:
    """Analyze saved activity trends with arithmetic and distance-weighted metrics and missing-data counts."""
    return _read_query(mcp_analysis.get_sport_progress, sport, start_date, end_date,
                       group_by, period_offset, period_limit)


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_activity_route(
    activity_id: Annotated[int, Field(gt=0)],
    sample_interval: Annotated[int | None, Field(ge=1, le=10000)] = None,
    max_points: Annotated[int, Field(ge=2, le=1000)] = 500,
) -> dict[str, Any]:
    """Get a bounded page of saved GPS points for an activity; reports missing GPS explicitly."""
    return _read_query(mcp_route.get_activity_route, activity_id, sample_interval, max_points)


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_segment_best_efforts(
    sport: Literal["running", "cycling"],
    segment_id: int | None = None,
    segment_name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: Annotated[int, Field(ge=1, le=50)] = 10,
) -> dict[str, Any]:
    """Rank cached complete GPS passes of a user-defined segment; never estimates from non-GPS data."""
    return _read_query(segment_store.get_segment_best_efforts,
                       segment_id, segment_name, sport, start_date, end_date, limit)


@mcp.tool(annotations=WRITES_DB, structured_output=True)
async def register_segment(
    name: str,
    sport: Literal["running", "cycling"],
    start_latitude: Annotated[float, Field(ge=-90, le=90)],
    start_longitude: Annotated[float, Field(ge=-180, le=180)],
    end_latitude: Annotated[float, Field(ge=-90, le=90)],
    end_longitude: Annotated[float, Field(ge=-180, le=180)],
    radius_m: Annotated[float, Field(ge=5, le=200)] = 30,
    waypoints: list[dict[str, float]] | None = None,
) -> dict[str, Any]:
    """Register a start, optional ordered waypoints, and end supplied by the user."""
    try:
        return await segment_tool.register_segment(name, sport, start_latitude, start_longitude,
                                                   end_latitude, end_longitude, radius_m, waypoints)
    except (httpx.HTTPError, ValueError, RuntimeError, OSError):
        return {"status": "service_error", "message": "Private segment registration failed"}


@mcp.tool(annotations=WRITES_DB, structured_output=True)
async def refresh_segment(
    segment_id: Annotated[int, Field(gt=0)],
    batch_size: Annotated[int, Field(ge=1, le=20)] = 10,
) -> dict[str, Any]:
    """Index a bounded batch of saved GPS activities for a registered segment; no Garmin calls."""
    try:
        return await segment_tool.refresh_segment(segment_id, batch_size)
    except (httpx.HTTPError, ValueError, RuntimeError, OSError):
        return {"status": "service_error", "message": "Private segment indexing failed"}


@mcp.tool(annotations=COLLECTS_DATA, structured_output=True)
async def get_activities_by_date(
    start_date: str,
    end_date: str | None = None,
    sport: Literal["running", "cycling", "swimming", "multisport", "all"] = "all",
) -> dict[str, Any]:
    """Get activities by inclusive local dates; collect missing date ranges from Garmin when needed."""
    try:
        return await asyncio.wait_for(
            date_tool.get_activities_by_date(start_date, end_date, sport), timeout=115
        )
    except TimeoutError:
        return {"status": "timeout", "source": "garmin", "activities": [],
                "message": "Date lookup exceeded 115 seconds"}


def load_internal_token() -> str:
    path = Path(os.getenv("MCP_TOKEN_FILE", str(ROOT / "data" / "mcp_internal_token")))
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise RuntimeError("MCP token file must be a private regular file (mode 600)")
    token = path.read_text(encoding="ascii").strip()
    if len(token) < 32:
        raise RuntimeError("MCP token file is missing or too short")
    return token


class TokenGuard:
    """Require a tunnel-injected secret before any MCP HTTP request."""

    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            supplied = next(
                (value for name, value in scope.get("headers", [])
                 if name.lower() == b"x-mcp-internal-token"),
                b"",
            )
            if not hmac.compare_digest(supplied, self.token.encode("ascii")):
                await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_app(token: str | None = None):
    host = os.getenv("MCP_HOST", "127.0.0.1")
    inner = mcp.streamable_http_app(
        stateless_http=True,
        json_response=True,
        host=host,
    )
    return TokenGuard(inner, token or load_internal_token())


def main() -> None:
    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_PORT", "8765"))
    if not 1 <= port <= 65535:
        raise ValueError("MCP_PORT must be between 1 and 65535")
    uvicorn.run(create_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
