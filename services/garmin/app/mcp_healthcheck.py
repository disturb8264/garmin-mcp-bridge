"""Check that the private MCP endpoint can serve a tools/list request."""

import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen


def main() -> None:
    token = Path(os.getenv("MCP_TOKEN_FILE", "/run/secrets/mcp_internal_token")).read_text(encoding="ascii").strip()
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode()
    port = int(os.getenv("MCP_PORT", "8765"))
    request = Request(
        f"http://127.0.0.1:{port}/mcp", data=payload,
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream",
                 "X-MCP-Internal-Token": token},
    )
    with urlopen(request, timeout=2) as response:
        result = json.load(response)
    if "tools" not in result.get("result", {}):
        sys.exit(1)


if __name__ == "__main__":
    main()
