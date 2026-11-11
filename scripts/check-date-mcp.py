"""Call the live Streamable HTTP MCP date tool without printing the token."""

import argparse
import json
from pathlib import Path

import httpx2
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("start_date")
    parser.add_argument("--end-date")
    parser.add_argument("--sport", choices=("running", "cycling", "swimming", "multisport", "all"), default="all")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    port = dotenv_values(ROOT / ".env").get("MCP_PORT") or "8765"
    token = (ROOT / "data" / "mcp_internal_token").read_text(encoding="ascii").strip()
    parameters = {"start_date": args.start_date, "sport": args.sport}
    if args.end_date:
        parameters["end_date"] = args.end_date
    response = httpx2.post(
        f"http://127.0.0.1:{port}/mcp",
        headers={"X-MCP-Internal-Token": token,
                 "Accept": "application/json, text/event-stream"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": "get_activities_by_date", "arguments": parameters}},
        timeout=118,
    )
    response.raise_for_status()
    result = response.json().get("result", {})
    data = result.get("structuredContent", {})
    if args.json:
        print(json.dumps(data or result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"status": data.get("status"), "source": data.get("source"),
                          "count": len(data.get("activities", [])),
                          "coverage_complete": data.get("coverage_complete"),
                          "message": data.get("message")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
