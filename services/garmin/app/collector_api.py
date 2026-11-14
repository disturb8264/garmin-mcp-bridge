"""Private collection bridge; Garmin and writer credentials stay outside MCP."""

import asyncio
import hmac
import json
import os
import stat
import sys
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.date_query import validate_range
from app import segment_store


WORKER_TIMEOUT_SECONDS = 80


def load_token() -> str:
    path = Path(os.environ["COLLECTOR_TOKEN_FILE"])
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise RuntimeError("Collector token file must be private (mode 600)")
    token = path.read_text(encoding="ascii").strip()
    if len(token) < 32:
        raise RuntimeError("Collector token is missing or too short")
    return token


def create_app(token: str | None = None) -> Starlette:
    expected = (token or load_token()).encode("ascii")

    def authorized(request: Request) -> bool:
        supplied = request.headers.get("X-Collector-Internal-Token", "").encode("ascii", "ignore")
        return hmac.compare_digest(supplied, expected)

    async def collect_range(request: Request):
        if not authorized(request):
            return JSONResponse({"status": "unauthorized"}, status_code=401)
        try:
            body = await request.json()
            start, end = validate_range(body.get("start_date"), body.get("end_date"))
        except (ValueError, AttributeError):
            return JSONResponse({"status": "invalid_request"}, status_code=400)

        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "app.collect_range_worker",
            start.isoformat(), end.isoformat(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            output, _ = await asyncio.wait_for(process.communicate(), WORKER_TIMEOUT_SECONDS)
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            process.kill()
            await process.wait()
            if isinstance(exc, asyncio.CancelledError):
                raise
            return JSONResponse({"status": "timeout", "message": "Date collection exceeded 80 seconds"})
        try:
            result = json.loads(output)
            if process.returncode != 0 or not isinstance(result, dict) or "status" not in result:
                raise ValueError
        except (ValueError, TypeError):
            return JSONResponse({"status": "api_error", "message": "Collector worker failed"})
        return JSONResponse(result)

    async def register_segment(request: Request):
        if not authorized(request):
            return JSONResponse({"status": "unauthorized"}, status_code=401)
        try:
            body = await request.json()
            result = await asyncio.to_thread(
                segment_store.register_segment,
                body["name"], body["sport"], body["start_latitude"],
                body["start_longitude"], body["end_latitude"], body["end_longitude"],
                body.get("radius_m", 30), body.get("waypoints"),
            )
        except (ValueError, TypeError, KeyError, AttributeError):
            return JSONResponse({"status": "invalid_request"}, status_code=400)
        except Exception:
            return JSONResponse({"status": "database_error", "message": "Segment registration failed"})
        return JSONResponse(result)

    async def refresh_segment(request: Request):
        if not authorized(request):
            return JSONResponse({"status": "unauthorized"}, status_code=401)
        try:
            body = await request.json()
            result = await asyncio.to_thread(
                segment_store.refresh_segment, body["segment_id"], body.get("batch_size", 10)
            )
        except (ValueError, TypeError, KeyError, AttributeError):
            return JSONResponse({"status": "invalid_request"}, status_code=400)
        except Exception:
            return JSONResponse({"status": "database_error", "message": "Segment indexing failed"})
        return JSONResponse(result)

    return Starlette(routes=[
        Route("/collect-range", collect_range, methods=["POST"]),
        Route("/register-segment", register_segment, methods=["POST"]),
        Route("/refresh-segment", refresh_segment, methods=["POST"]),
    ])


def main() -> None:
    uvicorn.run(
        create_app(),
        host=os.getenv("COLLECTOR_API_HOST", "127.0.0.1"),
        port=int(os.getenv("COLLECTOR_API_PORT", "8766")),
        access_log=False,
    )


if __name__ == "__main__":
    main()
