#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
docker build --tag "${GATEWAY_IMAGE:-mcp-gateway:local}" "$PROJECT_DIR"
