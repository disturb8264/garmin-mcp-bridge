#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
cd "$project_dir/runtime/gateway"
umask 077
mkdir -p secrets
chmod 700 secrets

install -m 600 "${INBODY_TOKEN_SOURCE:-/home/disturb/projects/inbody/data/mcp_internal_token}" secrets/inbody_token
install -m 600 "${GARMIN_TOKEN_SOURCE:-$project_dir/runtime/garmin/data/mcp_internal_token}" secrets/garmin_token

echo "Copied InBody and Garmin tokens into secrets/"
