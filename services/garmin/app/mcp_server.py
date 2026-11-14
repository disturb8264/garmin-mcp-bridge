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
    """Use for '최근 러닝 5개' or other latest saved activities; sport filters and limit is 1-20 (default 5). Do not use for dates, oldest records, or distance filters; use search_activities instead. No Garmin sync."""
    return _read_query(mcp_data.list_activities, limit, sport)


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_activity(activity_id: Annotated[int, Field(gt=0)]) -> dict[str, Any]:
    """Use for '이 운동의 심박·거리 분석' when activity_id is known: saved summary, HR zones, and lap/sample counts. Use get_activity_laps for lap splits or get_activity_samples for time-series; do not fetch them for a summary alone."""
    return _read_query(mcp_data.activity_details, activity_id)


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_activity_laps(activity_id: Annotated[int, Field(gt=0)]) -> dict[str, Any]:
    """Use for '이 러닝의 구간별 페이스' with a known activity_id; returns ordered saved laps. Use get_activity for the overall summary; do not use laps for second-by-second samples or GPS routes."""
    return _read_query(mcp_data.activity_laps, activity_id)


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_activity_samples(
    activity_id: Annotated[int, Field(gt=0)],
    offset: Annotated[int, Field(ge=0)] = 0,
    limit: Annotated[int, Field(ge=1, le=200)] = 100,
) -> dict[str, Any]:
    """Use only for sample-level questions such as '이 활동의 심박 165 이상 구간' with a known activity_id. Returns saved time-series, not GPS coordinates; offset starts at 0, limit is 1-200 (default 100), and next_offset pages more. Large output: do not page whole activities for summaries or GPS routes; use get_activity, get_activity_laps, or get_activity_route for those needs."""
    return _read_query(mcp_data.activity_samples, activity_id, offset, limit)


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_sync_status() -> dict[str, Any]:
    """Use for '방금 한 운동이 수집됐어?' to check the last Garmin collector run and newest saved activity. It does not collect data; do not call before routine historical searches or use it for activity details."""
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
    """Use for '첫 수영 기록'(sport=swimming, sort=oldest, limit=1), '2016년 사이클', or distance-filtered activities. Dates are inclusive local YYYY-MM-DD; distance is m, duration is s; sort=newest/oldest orders dates descending/ascending, distance/duration orders values descending. offset and limit (1-100, default 20) page results. Saved DB only: first saved record is not proven sport start; whole-activity times are not exact-distance split PBs. For totals use get_sport_history; do not call the collecting date tool for saved-only searches."""
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
    """Use for '지난달 총 몇 km 뛰었어?' or '연도별 수영 거리': SQL summary, first/last saved date, totals, best saved activity, and grouped periods. Inclusive local YYYY-MM-DD dates; group_by=year/month/week, period_offset and period_limit (1-120) page periods. Do not use for only the first saved activity (search_activities oldest, limit=1) or pace/HR changes (get_sport_progress). Coverage limits claims about actual sport start; no Garmin sync."""
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
    """Use for '최근 3개월 러닝 페이스가 좋아졌어?' or monthly HR/power trends. Inclusive local YYYY-MM-DD dates; group_by=year/month/week, period_offset and period_limit (1-120) page SQL summaries. Distinguishes arithmetic vs distance-weighted averages and missing metrics. Do not use for totals/first date (get_sport_history), raw samples, or exact splits; saved DB only, so check coverage."""
    return _read_query(mcp_analysis.get_sport_progress, sport, start_date, end_date,
                       group_by, period_offset, period_limit)


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_activity_route(
    activity_id: Annotated[int, Field(gt=0)],
    sample_interval: Annotated[int | None, Field(ge=1, le=10000)] = None,
    max_points: Annotated[int, Field(ge=2, le=1000)] = 500,
) -> dict[str, Any]:
    """Use for '이 활동의 GPS 경로' with a known activity_id. Returns saved coordinates and metrics or explicit no-GPS status; max_points is 2-1000 (default 500), sample_interval is optional sample-index stride. GPS output can be large: request fewer points for an overview. Do not use raw routes for registered course rankings; use get_segment_best_efforts. No Garmin sync."""
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
    """Use for '남산 업힐 최고 기록' only after that running/cycling segment is registered and indexed. Provide exactly one of segment_id or segment_name plus sport; inclusive local YYYY-MM-DD dates and limit 1-50 (default 10) bound cached GPS pass rankings. If indexing_required, use refresh_segment. Do not infer a PB from missing GPS or use this for a whole-activity record."""
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
    """Use when asked to define a running/cycling course, e.g. '이 좌표로 남산 구간 등록', with user-supplied start/end coordinates. radius_m is checkpoint tolerance 5-200m (default 30); optional waypoints are up to 8 ordered latitude/longitude pairs. Writes a segment definition, not efforts: do not guess coordinates or call for a ranking; index afterward with refresh_segment."""
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
    """Use after register_segment or when get_segment_best_efforts says indexing_required, e.g. '등록한 구간 기록 계산해줘'. segment_id identifies the course; batch_size 1-20 (default 10) bounds one indexing pass, so repeat only while pending. Writes cached efforts from saved GPS, without Garmin API; do not call for routine rankings or during active collection."""
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
    """Use for '어제 운동 뭐 했어?' when a local YYYY-MM-DD date is known; start_date/end_date are inclusive and sport filters results. Reads saved PostgreSQL first, but uncovered dates can trigger external Garmin collection. For historical saved-only date/range searches use search_activities; do not use this merely to refresh data or before every other query."""
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
