#!/usr/bin/env bash
set -euo pipefail

container_name="${1:-}"
if [[ -z "$container_name" ]]; then
  container_name="$(
    docker ps --filter "name=reporeason" --format "{{.Names}}" | head -n 1
  )"
fi

if [[ -z "$container_name" ]]; then
  echo "No running container matching name=reporeason" >&2
  exit 1
fi

docker exec -it "$container_name" sh -lc '
PORT="$(printenv PORT || true)";
OPCODE_PORT="$(printenv OPCODE_PORT || true)";
if [ -z "$PORT" ] && [ -z "$OPCODE_PORT" ]; then
  PORT="$(ss -lntp 2>/dev/null | grep -m1 "opencode serve" | sed -E "s/.*:([0-9]+) .*/\1/")";
fi;
PORT="${PORT:-$OPCODE_PORT}";
opencode attach "http://127.0.0.1:${PORT:-8234}"'
