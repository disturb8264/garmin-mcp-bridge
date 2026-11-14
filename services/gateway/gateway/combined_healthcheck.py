"""Docker healthcheck for the gateway and local tunnel."""

import os
from pathlib import Path
from gateway.app import load_config
from gateway.combined import gateway_ready, tunnel_ready


def main() -> None:
    config, _, token = load_config(Path(os.environ.get("GATEWAY_CONFIG", "/app/gateway.yaml")))
    if not gateway_ready(int(config.get("listen_port", 18767)), token):
        raise SystemExit(1)
    if not tunnel_ready():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
