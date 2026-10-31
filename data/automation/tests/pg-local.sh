# A throwaway local Postgres for the data/automation suite — no Docker, no cluster (plan.md S1.1: an embedded
# `postgres` via `uv run --with pgserver`, the harness's one dev dependency). pgserver ships the server
# binaries inside a wheel (macOS arm64/x86_64, manylinux), so the same lines run on a laptop and in CI.
#
#   source pg-local.sh; pg_local_start      → initdb + start; exports PGHOST/PGPORT/PGUSER and CTX=local
#   pg_local_stop                           → stop it and delete its directory
#
# The server listens on a Unix socket only, in a fresh temp directory, trusts every local connection and
# is gone after pg_local_stop. Never point CTX=local at a shared database.

PGSERVER_VERSION="${PGSERVER_VERSION:-0.1.4}"   # Postgres 16.2
# pgserver 0.1.4 ships wheels for CPython 3.9–3.11 only. Without a pin, uv picks the newest CPython it can get (3.14 on
# the CI runner since late October 2026) and finds no wheel, so the suite cannot start.
PG_LOCAL_PYTHON="${PG_LOCAL_PYTHON:-3.11}"

pg_local_bin() {
  uv run --python "$PG_LOCAL_PYTHON" --quiet --with "pgserver==$PGSERVER_VERSION" python3 -I -c \
    'import pathlib, pgserver; print(pathlib.Path(pgserver.__file__).parent / "pginstall" / "bin")'
}

pg_local_start() {
  PG_LOCAL_BIN="$(pg_local_bin)" || { echo "pg-local: cannot fetch pgserver $PGSERVER_VERSION with uv" >&2; return 1; }
  # A short path: a Unix socket's path is capped near 104 bytes on macOS.
  PG_LOCAL_DIR="$(mktemp -d "${TMPDIR:-/tmp}/aupg.XXXXXX")"
  "$PG_LOCAL_BIN/initdb" -D "$PG_LOCAL_DIR/data" -U postgres --auth=trust -E UTF8 --locale=C >/dev/null || return 1
  "$PG_LOCAL_BIN/pg_ctl" -D "$PG_LOCAL_DIR/data" -l "$PG_LOCAL_DIR/server.log" -w \
    -o "-k $PG_LOCAL_DIR -c listen_addresses= -F" start >/dev/null || { cat "$PG_LOCAL_DIR/server.log" >&2; return 1; }
  export PGHOST="$PG_LOCAL_DIR" PGPORT=5432 PGUSER=postgres CTX=local
  # The server's own client tools first: psql, pg_dump and the server then agree on the version.
  export PATH="$PG_LOCAL_BIN:$PATH"
  export PG_LOCAL_DIR PG_LOCAL_BIN
}

pg_local_stop() {
  [ -n "${PG_LOCAL_DIR:-}" ] || return 0
  "$PG_LOCAL_BIN/pg_ctl" -D "$PG_LOCAL_DIR/data" -m fast -w stop >/dev/null 2>&1
  rm -rf "$PG_LOCAL_DIR"
  unset PG_LOCAL_DIR
}
