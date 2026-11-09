#!/bin/bash
set -euo pipefail

psql -X -v ON_ERROR_STOP=1 --csv -qt -f /app/files/query.sql
