#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
python3 - "$project_root/runtime/garmin/data/mcp_internal_token" "$project_root/runtime/garmin/data/collector_internal_token" <<'PY'
import os
import secrets
import sys

for path in sys.argv[1:]:
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print(f"{os.path.basename(path)} already exists; keeping it")
    else:
        try:
            os.write(fd, secrets.token_hex(32).encode("ascii"))
        finally:
            os.close(fd)
        print(f"{os.path.basename(path)} created with mode 600")
PY
