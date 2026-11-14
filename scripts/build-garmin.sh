#!/bin/sh
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
IMAGE_TAG=$(python3 "$PROJECT_DIR/scripts/read-image-tag.py" GARMIN_IMAGE)
docker build --tag "$IMAGE_TAG" "$PROJECT_DIR/services/garmin"
