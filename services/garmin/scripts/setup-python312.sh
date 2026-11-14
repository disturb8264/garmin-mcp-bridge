#!/usr/bin/env bash
set -euo pipefail

# Ubuntu 22.04: build a private CPython without changing /usr/bin/python3.
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
python_version="3.12.16"
python_prefix="$project_root/.python/$python_version"
python_bin="$python_prefix/bin/python3.12"
archive_sha256="b5796915dc45ff745cfb4e990a7e7c93d6f546328a102ce31448d69ebc37575c"

if [[ "${EUID}" -eq 0 ]]; then
    echo "Run as your normal user: bash services/garmin/scripts/setup-python312.sh [--test-auth]" >&2
    echo "The script uses sudo only if build dependencies are missing." >&2
    exit 2
fi
if [[ "${1:-}" != "" && "${1:-}" != "--test-auth" ]] || [[ "$#" -gt 1 ]]; then
    echo "Usage: bash services/garmin/scripts/setup-python312.sh [--test-auth]" >&2
    exit 2
fi

if [[ ! -x "$python_bin" ]]; then
    packages=(build-essential ca-certificates curl xz-utils libssl-dev zlib1g-dev
              libbz2-dev libreadline-dev libsqlite3-dev libffi-dev liblzma-dev
              libgdbm-dev libncursesw5-dev uuid-dev libexpat1-dev)
    missing=()
    for package in "${packages[@]}"; do
        if ! dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -qx 'install ok installed'; then
            missing+=("$package")
        fi
    done
    if (( ${#missing[@]} > 0 )); then
        echo "Installing missing build packages: ${missing[*]}"
        sudo apt-get update
        sudo apt-get install -y --no-install-recommends "${missing[@]}"
    fi

    build_dir="$(mktemp -d "${TMPDIR:-/tmp}/garmin-python312.XXXXXXXX")"
    trap 'rm -rf -- "$build_dir"' EXIT
    archive="$build_dir/Python-$python_version.tar.xz"
    echo "Downloading CPython $python_version from python.org"
    curl --fail --location --retry 3 --proto '=https' --tlsv1.2 \
        "https://www.python.org/ftp/python/$python_version/Python-$python_version.tar.xz" \
        --output "$archive"
    printf '%s  %s\n' "$archive_sha256" "$archive" | sha256sum --check --status
    echo "Source SHA-256 verified"

    tar -xJf "$archive" -C "$build_dir"
    cd "$build_dir/Python-$python_version"
    ./configure --prefix="$python_prefix" --with-ensurepip=install
    jobs="$(nproc)"
    if (( jobs > 4 )); then jobs=4; fi
    make -j "$jobs"
    make altinstall
fi

"$python_bin" -c 'import ssl, sqlite3, venv; assert ssl.OPENSSL_VERSION'
echo "Private interpreter: $("$python_bin" --version)"
cd "$project_root"
if [[ -e .venv ]]; then
    if ! .venv/bin/python -c 'import sys; assert sys.version_info[:2] == (3, 12)' 2>/dev/null; then
        echo "Existing .venv is not Python 3.12; move it aside before rerunning." >&2
        exit 2
    fi
else
    "$python_bin" -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r services/garmin/requirements.txt
PYTHONPATH=services/garmin .venv/bin/python -m unittest discover -s services/garmin/tests -v
echo "Python 3.12 environment is ready."

if [[ "${1:-}" == "--test-auth" ]]; then
    PYTHONPATH=services/garmin .venv/bin/python -m app.main --mode recent --limit 5 --dry-run
fi
