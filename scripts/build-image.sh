#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
docker build \
  --tag disturb8264/garmin-mcp-bridge:0.3.1 \
  --tag ghcr.io/disturb8264/garmin-mcp-bridge:0.3.1 \
  "$PROJECT_DIR"
