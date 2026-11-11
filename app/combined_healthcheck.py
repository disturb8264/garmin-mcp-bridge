"""Check the MCP server and, when enabled, the tunnel."""

import urllib.request

from app.mcp_healthcheck import main as check_mcp
from app.combined import tunnel_enabled


def main() -> None:
    check_mcp()
    if tunnel_enabled():
        with urllib.request.urlopen("http://127.0.0.1:8080/readyz", timeout=2) as response:
            if response.status != 200 or response.read().strip() != b"ready":
                raise SystemExit(1)


if __name__ == "__main__":
    main()
