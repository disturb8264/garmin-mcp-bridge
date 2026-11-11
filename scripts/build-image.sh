#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
docker build --tag disturb8264/garmin-mcp-bridge:latest "$PROJECT_DIR"
