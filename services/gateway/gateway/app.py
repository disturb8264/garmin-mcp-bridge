"""Authenticated, dynamically refreshed MCP tool gateway."""

import asyncio
import hmac
import logging
import os
import re
import stat
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import uvicorn
import yaml
from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

LOG = logging.getLogger("gateway")
ROOT = Path(__file__).resolve().parent.parent
ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def private_token(path: Path) -> str:
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise ValueError(f"token file must be private (mode 600): {path}")
    value = path.read_text(encoding="ascii").strip()
    if len(value) < 32:
        raise ValueError(f"token too short: {path}")
    return value


def resolved_path(config_path: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_path.parent / path


@dataclass(frozen=True)
class Upstream:
    id: str
    url: str
    token: str
    allowed_tools: frozenset[str]


def load_config(path: Path) -> tuple[dict[str, Any], list[Upstream], str]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("gateway config must be a mapping")
    gateway_token = private_token(resolved_path(path, raw["gateway_token_file"]))
    upstreams = []
    seen = set()
    for item in raw["upstreams"]:
        server_id = item["id"]
        if not ID_RE.fullmatch(server_id) or server_id in seen:
            raise ValueError(f"invalid or duplicate upstream id: {server_id}")
        seen.add(server_id)
        if not item["url"].startswith(("http://127.0.0.1:", "http://localhost:", "https://")):
            raise ValueError(f"upstream {server_id} needs loopback HTTP or HTTPS")
        allow = item["allowed_tools"]
        if not isinstance(allow, list) or not allow or not all(isinstance(x, str) for x in allow):
            raise ValueError(f"invalid allowed_tools: {server_id}")
        upstreams.append(Upstream(server_id, item["url"],
                                  private_token(resolved_path(path, item["token_file"])),
                                  frozenset(allow)))
    return raw, upstreams, gateway_token


class Registry:
    def __init__(self, upstreams: list[Upstream]):
        self.upstreams = {s.id: s for s in upstreams}
        self.tools: dict[str, tuple[Upstream, str, types.Tool]] = {}
        self.status = {s.id: {"connected": False, "last_refresh": None, "error": None}
                       for s in upstreams}
        self.lock = asyncio.Lock()

    @asynccontextmanager
    async def session(self, upstream: Upstream):
        async with httpx.AsyncClient(
            headers={"X-MCP-Internal-Token": upstream.token}, timeout=15.0,
            trust_env=False,
        ) as client:
            async with streamable_http_client(upstream.url, http_client=client) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await asyncio.wait_for(session.initialize(), timeout=15)
                    yield session

    async def refresh_one(self, upstream: Upstream):
        try:
            async with self.session(upstream) as session:
                gathered = []
                cursor = None
                while True:
                    result = await asyncio.wait_for(
                        session.list_tools(params=types.PaginatedRequestParams(cursor=cursor) if cursor else None),
                        timeout=15,
                    )
                    gathered.extend(result.tools)
                    cursor = result.next_cursor
                    if not cursor:
                        break
            new = {}
            for tool in gathered:
                if "*" not in upstream.allowed_tools and tool.name not in upstream.allowed_tools:
                    continue
                public_name = f"{upstream.id}_{tool.name}"
                if public_name in new:
                    raise ValueError(f"duplicate tool: {public_name}")
                public_tool = tool.model_copy(update={"name": public_name})
                new[public_name] = (upstream, tool.name, public_tool)
            async with self.lock:
                remaining = {name: entry for name, entry in self.tools.items()
                             if entry[0].id != upstream.id}
                conflicts = remaining.keys() & new.keys()
                if conflicts:
                    raise ValueError(f"public tool collision: {sorted(conflicts)}")
                self.tools = {**remaining, **new}
                self.status[upstream.id] = {"connected": True, "last_refresh": time.time(), "error": None}
            LOG.info("refreshed upstream=%s tools=%d", upstream.id, len(new))
        except Exception as exc:
            self.status[upstream.id]["connected"] = False
            self.status[upstream.id]["error"] = type(exc).__name__
            LOG.warning("refresh failed upstream=%s error=%s", upstream.id, type(exc).__name__)

    async def refresh_all(self):
        await asyncio.gather(*(self.refresh_one(s) for s in self.upstreams.values()))

    async def list_tools(self, _ctx, _params):
        async with self.lock:
            return types.ListToolsResult(tools=[entry[2] for entry in self.tools.values()])

    async def call_tool(self, _ctx, params: types.CallToolRequestParams):
        async with self.lock:
            entry = self.tools.get(params.name)
        if entry is None:
            return types.CallToolResult(content=[types.TextContent(type="text", text="tool_unavailable")], isError=True)
        upstream, original_name, _ = entry
        started = time.monotonic()
        try:
            async with self.session(upstream) as session:
                result = await asyncio.wait_for(
                    session.call_tool(original_name, params.arguments or {}, read_timeout_seconds=30),
                    timeout=35,
                )
                if not isinstance(result, types.CallToolResult):
                    raise ValueError("unsupported upstream tool result")
            LOG.info("call tool=%s upstream=%s ms=%d error=%s", params.name, upstream.id,
                     int((time.monotonic() - started) * 1000), bool(result.is_error))
            return result
        except Exception as exc:
            LOG.warning("call failed tool=%s upstream=%s ms=%d error=%s", params.name,
                        upstream.id, int((time.monotonic() - started) * 1000), type(exc).__name__)
            return types.CallToolResult(content=[types.TextContent(type="text", text="upstream_unavailable")], isError=True)


class TokenGuard:
    def __init__(self, app, token: str):
        self.app = app
        self.token = token.encode("ascii")

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            supplied = next((v for k, v in scope.get("headers", [])
                             if k.lower() == b"x-mcp-internal-token"), b"")
            if not hmac.compare_digest(supplied, self.token):
                await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_app(config_path: Path):
    config, upstreams, token = load_config(config_path)
    registry = Registry(upstreams)
    server = Server("mcp-gateway", on_list_tools=registry.list_tools,
                    on_call_tool=registry.call_tool)
    manager = StreamableHTTPSessionManager(server, json_response=True, stateless=True)
    interval = max(10, int(config.get("refresh_seconds", 60)))

    async def refresh_loop():
        while True:
            await asyncio.sleep(interval)
            await registry.refresh_all()

    @asynccontextmanager
    async def lifespan(_app):
        async with manager.run():
            await registry.refresh_all()
            task = asyncio.create_task(refresh_loop())
            try:
                yield
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def health(_request):
        return JSONResponse({"upstreams": registry.status, "tool_count": len(registry.tools)})

    app = Starlette(routes=[Route("/health", health), Mount("/mcp", app=manager.asgi_app)],
                    lifespan=lifespan)
    return TokenGuard(app, token)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    path = Path(os.getenv("GATEWAY_CONFIG", str(ROOT / "gateway.yaml"))).resolve()
    config, _, _ = load_config(path)
    uvicorn.run(create_app(path), host=config.get("listen_host", "127.0.0.1"),
                port=int(config.get("listen_port", 18767)), log_level="warning")


if __name__ == "__main__":
    main()
