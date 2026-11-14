"""Run the private collector and MCP server."""

import os
import signal
import socket
import subprocess
import sys
import time


COMMANDS = (
    ("collector", [sys.executable, "-m", "app.collector_api"]),
    ("mcp", [sys.executable, "-m", "app.mcp_server"]),
)


def main() -> None:
    commands = COMMANDS
    collector_port = int(os.getenv("COLLECTOR_API_PORT", "8766"))
    mcp_port = int(os.getenv("MCP_PORT", "8765"))
    os.environ.setdefault("MCP_COLLECTOR_URL", f"http://127.0.0.1:{collector_port}/collect-range")
    os.environ.setdefault("MCP_SERVER_URL", f"http://127.0.0.1:{mcp_port}/mcp")
    processes: list[tuple[str, subprocess.Popen]] = []
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        for name, command in commands:
            processes.append((name, subprocess.Popen(command, start_new_session=True)))
        deadline = time.monotonic() + 30
        while not stopping and time.monotonic() < deadline:
            for name, process in processes:
                if process.poll() is not None:
                    raise RuntimeError(f"{name} exited during startup")
            try:
                with socket.create_connection(("127.0.0.1", collector_port), timeout=1):
                    pass
                result = subprocess.run(
                    [sys.executable, "-m", "app.mcp_healthcheck"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3,
                    check=False,
                )
                if result.returncode == 0:
                    break
            except (OSError, subprocess.TimeoutExpired):
                pass
            time.sleep(1)
        else:
            if not stopping:
                raise RuntimeError(f"Collector on {collector_port} or MCP server on {mcp_port} did not become ready")
        if stopping:
            return
        while not stopping:
            for name, process in processes:
                code = process.poll()
                if code is not None:
                    print(f"{name} exited with status {code}", file=sys.stderr, flush=True)
                    stopping = True
                    break
            if not stopping:
                time.sleep(1)
    finally:
        for _name, process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        deadline = time.monotonic() + 10
        for _name, process in processes:
            remaining = deadline - time.monotonic()
            if remaining > 0:
                try:
                    process.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    pass
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


if __name__ == "__main__":
    main()
