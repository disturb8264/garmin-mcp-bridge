#!/bin/sh
set -eu

gateway_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$gateway_dir"
umask 077
mkdir -p secrets
chmod 700 secrets

install -m 600 "${INBODY_TOKEN_SOURCE:-/home/disturb/projects/inbody/data/mcp_internal_token}" secrets/inbody_token
install -m 600 "${GARMIN_TOKEN_SOURCE:-$gateway_dir/../data/mcp_internal_token}" secrets/garmin_token

echo "Copied InBody and Garmin tokens into secrets/"
