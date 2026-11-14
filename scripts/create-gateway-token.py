"""Create the gateway's own internal token on the host if missing."""

import os
import secrets
from pathlib import Path


RUNTIME = Path(__file__).resolve().parent.parent / "runtime" / "gateway"


def create_private(path: Path, content: str) -> bool:
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(content)
    return True


def main() -> None:
    RUNTIME.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    secret_dir = RUNTIME / "secrets"
    secret_dir.mkdir(mode=0o700, exist_ok=True)
    os.chmod(RUNTIME.parent, 0o700)
    os.chmod(RUNTIME, 0o700)
    os.chmod(secret_dir, 0o700)
    token = secret_dir / "gateway_token"
    if create_private(token, secrets.token_urlsafe(48) + "\n"):
        print("Created runtime/gateway/secrets/gateway_token")
    else:
        print("Existing gateway token kept")


if __name__ == "__main__":
    main()
