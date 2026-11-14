"""Check the MCP server."""

from app.mcp_healthcheck import main as check_mcp


def main() -> None:
    check_mcp()


if __name__ == "__main__":
    main()
