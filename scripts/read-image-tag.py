"""Read one Docker image tag from the root Compose .env without executing it."""

import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"GARMIN_IMAGE", "GATEWAY_IMAGE"}:
        raise SystemExit("Usage: read-image-tag.py GARMIN_IMAGE|GATEWAY_IMAGE")

    env_path = Path(__file__).resolve().parent.parent / ".env"
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        raise SystemExit("Create the root .env from .env.example before building") from None

    values = []
    for line in lines:
        key, separator, value = line.partition("=")
        if separator and key.strip() == sys.argv[1]:
            values.append(value.strip())
    if len(values) != 1 or not values[0] or any(char.isspace() for char in values[0]):
        raise SystemExit(f"Set exactly one valid {sys.argv[1]} value in the root .env")
    print(values[0])


if __name__ == "__main__":
    main()
