"""Private Streamable HTTP MCP server for saved and on-demand Garmin activities."""

import hmac
import asyncio
import os
import stat
from pathlib import Path
from typing import Annotated, Any, Literal

import uvicorn
import psycopg
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.responses import JSONResponse

from app import date_tool, mcp_data
from app.config import ROOT


READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
COLLECTS_DATA = ToolAnnotations(readOnlyHint=False, openWorldHint=True)
mcp = MCPServer(
    "Garmin Activities",
    instructions=(
        "Read-only access to saved Garmin running, cycling, swimming and multisport activities. "
        "Use get_sync_status to check freshness when a user asks about a just-finished activity. "
        "Distances are meters, durations and paces are seconds (per km for running, per 100m for swimming), and speeds are m/s. "
        "get_activities_by_date checks saved data first and can collect missing dates from Garmin."
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
