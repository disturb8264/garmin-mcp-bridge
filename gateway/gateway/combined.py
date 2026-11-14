"""Run the gateway and tunnel in one container, starting the tunnel after MCP is ready."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

from gateway.app import load_config


def gateway_ready(port: int, token: str) -> bool:
    request = Request(f"http://127.0.0.1:{port}/health",
                      headers={"X-MCP-Internal-Token": token})
    try:
        with urlopen(request, timeout=2) as response:
            return response.status == 200
    except OSError:
        return False


def tunnel_ready() -> bool:
    try:
        with urlopen("http://127.0.0.1:8080/readyz", timeout=2) as response:
            return response.status == 200 and response.read().strip() == b"ready"
    except OSError:
        return False


def main() -> None:
    # Keep tunnel credentials in the gateway-specific env file.
    os.environ["CONTROL_PLANE_TUNNEL_ID"] = os.environ["TUNNEL_ID"]
    config_path = Path(os.environ.get("GATEWAY_CONFIG", "/app/gateway.yaml"))
    config, _, token = load_config(config_path)
    port = int(config.get("listen_port", 18767))
    processes: list[tuple[str, subprocess.Popen]] = []
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        gateway = subprocess.Popen([sys.executable, "-m", "gateway.app"], start_new_session=True)
        processes.append(("gateway", gateway))
        deadline = time.monotonic() + 45
        while not stopping and time.monotonic() < deadline:
            if gateway.poll() is not None:
                raise RuntimeError("gateway exited during startup")
            if gateway_ready(port, token):
                break
            time.sleep(1)
        else:
            if not stopping:
                raise RuntimeError("gateway did not become ready")
        if stopping:
            return
        tunnel = subprocess.Popen(["/usr/bin/tunnel-client", "run"], start_new_session=True)
        processes.append(("tunnel", tunnel))
        deadline = time.monotonic() + 60
        while not stopping and time.monotonic() < deadline:
            if tunnel.poll() is not None:
                raise RuntimeError("tunnel exited during startup")
            if tunnel_ready():
                break
            time.sleep(1)
        else:
            if not stopping:
                raise RuntimeError("tunnel did not become ready")
        if stopping:
            return
        while not stopping:
            for name, process in processes:
                code = process.poll()
                if code is not None:
                    raise RuntimeError(f"{name} exited with status {code}")
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
