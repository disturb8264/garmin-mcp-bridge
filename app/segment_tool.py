"""Send segment write jobs to the private collector process."""

import os

import httpx2 as httpx

from app.date_tool import _collector_token


async def _post(path: str, payload: dict) -> dict:
    collector_url = os.getenv("MCP_COLLECTOR_URL", "")
    if not collector_url.endswith("/collect-range"):
        raise RuntimeError("Private collector is not configured")
    url = collector_url.removesuffix("/collect-range") + path
    async with httpx.AsyncClient(timeout=httpx.Timeout(85.0, connect=3.0)) as client:
        response = await client.post(url, json=payload,
                                     headers={"X-Collector-Internal-Token": _collector_token()})
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict) or "status" not in result:
        raise ValueError("Invalid collector result")
    return result


async def register_segment(name, sport, start_latitude, start_longitude,
                           end_latitude, end_longitude, radius_m=30, waypoints=None):
    return await _post("/register-segment", {
        "name": name, "sport": sport,
        "start_latitude": start_latitude, "start_longitude": start_longitude,
        "end_latitude": end_latitude, "end_longitude": end_longitude,
        "radius_m": radius_m, "waypoints": waypoints or [],
    })


async def refresh_segment(segment_id, batch_size=10):
    return await _post("/refresh-segment", {"segment_id": segment_id,
                                              "batch_size": batch_size})
