#!/usr/bin/env bash
# Benchmark target app lifecycle. Usage: bench/app/conduit.sh up|reset|down|logs
#   up     build + start; on first run, seed through the API and snapshot as template conduit_seed
#   reset  restore the seeded state (CREATE DATABASE conduit TEMPLATE conduit_seed) — run before each test run
#   down   stop containers (data kept); add -v to remove the volume: conduit.sh down -v
set -euo pipefail
cd "$(dirname "$0")"
URL=${TESTO_TARGET_URL:-http://localhost:4100}
dc() { docker compose "$@"; }
psql_db() { dc exec -T db psql -v ON_ERROR_STOP=1 -U conduit -d postgres -qtAc "$1"; }

wait_ready() {
  for _ in $(seq 1 60); do
    curl -fsS "$URL/api/tags" >/dev/null 2>&1 && return 0
    sleep 1
  done
  echo "app did not become ready at $URL" >&2; dc logs --tail 30 app >&2; exit 1
}

case "${1:-}" in
  up)
    dc up -d --build db
    dc exec -T db sh -c 'until pg_isready -U conduit -q; do sleep 1; done'
    if [ "$(psql_db "SELECT 1 FROM pg_database WHERE datname = 'conduit_seed'")" != "1" ]; then
      psql_db "DROP DATABASE IF EXISTS conduit" && psql_db "CREATE DATABASE conduit"
      dc up -d --build app && wait_ready
      node seed.mjs "$URL"
      dc stop app
      psql_db "CREATE DATABASE conduit_seed TEMPLATE conduit"
      echo "template conduit_seed created"
    fi
    "$0" reset
    ;;
  reset)
    dc stop app >/dev/null 2>&1 || true
    psql_db "DROP DATABASE IF EXISTS conduit WITH (FORCE)"
    psql_db "CREATE DATABASE conduit TEMPLATE conduit_seed"
    dc up -d app && wait_ready
    echo "conduit reset to seed — $URL"
    ;;
  down) shift; dc down "$@" ;;
  logs) dc logs -f app ;;
  *) echo "usage: $0 up|reset|down|logs" >&2; exit 2 ;;
esac
