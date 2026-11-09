#!/bin/bash
set -euo pipefail

mode="${1:-public}"
root=/tmp/bitemporal-pg
data="$root/data"
socket="$root/socket"
port=55439
mkdir -p "$root" "$socket"
chown -R postgres:postgres "$root"

if [ ! -s "$data/PG_VERSION" ]; then
  runuser -u postgres -- /usr/lib/postgresql/16/bin/initdb -D "$data" --no-locale --encoding=UTF8 --auth=trust >/dev/null
fi
if ! runuser -u postgres -- /usr/lib/postgresql/16/bin/pg_ctl -D "$data" status >/dev/null 2>&1; then
  runuser -u postgres -- /usr/lib/postgresql/16/bin/pg_ctl -D "$data" -o "-F -k $socket -p $port -h ''" -w start >/dev/null
fi

export PGHOST="$socket" PGPORT="$port" PGUSER=postgres PGDATABASE=postgres
trap 'runuser -u postgres -- /usr/lib/postgresql/16/bin/pg_ctl -D "$data" -m fast -w stop >/dev/null 2>&1 || true' EXIT
psql -X -v ON_ERROR_STOP=1 -q -f /app/files/schema.sql

if [ "$mode" = public ]; then
  python3 -m pytest -q /app/files/tests.py
elif [ "$mode" = hidden ]; then
  python3 -m pytest -q /app/hidden/hidden_tests.py
else
  printf 'usage: %s public|hidden\n' "$0" >&2
  exit 2
fi
