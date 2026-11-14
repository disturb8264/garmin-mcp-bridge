"""Create local gateway configuration and token on first Compose startup."""

import os
import secrets
from pathlib import Path

import yaml

from gateway.app import private_token


def create_defaults(config_path: Path, inbody_url: str, inbody_token_file: str,
                    garmin_url: str = "http://127.0.0.1:18765/mcp",
                    garmin_token_file: str = "secrets/garmin_token") -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    secret_dir = config_path.parent / "secrets"
    secret_dir.mkdir(mode=0o700, exist_ok=True)
    token_path = secret_dir / "gateway_token"
    try:
        fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, "w", encoding="ascii") as file:
            file.write(secrets.token_urlsafe(48) + "\n")
        print(f"created {token_path}")
    private_token(token_path)

    data = {
        "listen_host": "127.0.0.1",
        "listen_port": 18767,
        "gateway_token_file": "secrets/gateway_token",
        "refresh_seconds": 60,
        "upstreams": [
            {
                "id": "inbody",
                "url": inbody_url,
                "token_file": inbody_token_file,
                "allowed_tools": ["*"],
            },
            {
                "id": "garmin",
                "url": garmin_url,
                "token_file": garmin_token_file,
                "allowed_tools": ["*"],
            },
        ],
    }
    try:
        fd = os.open(config_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print(f"using existing {config_path}")
    else:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            yaml.safe_dump(data, file, allow_unicode=True, sort_keys=False)
        print(f"created {config_path}")


if __name__ == "__main__":
    create_defaults(
        Path(os.environ.get("GATEWAY_CONFIG", "/config/gateway.yaml")),
        os.environ.get("INBODY_MCP_URL", "http://127.0.0.1:18766/mcp"),
        os.environ.get("INBODY_TOKEN_FILE", "secrets/inbody_token"),
        os.environ.get("GARMIN_MCP_URL", "http://127.0.0.1:18765/mcp"),
        os.environ.get("GARMIN_TOKEN_FILE", "secrets/garmin_token"),
    )
