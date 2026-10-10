# Shared by run-extend.sh and tests/*.sh — the one place that knows how to reach psql.
#
#   CTX=<kube-context>       → kubectl exec into $POD (container `postgres`) in $NS, pod-local socket,
#                              as the postgres superuser — the run-redate.sh path.
#   CTX=docker:<container>   → docker exec into a THROWAWAY local Postgres (development/tests only;
#                              never point it at a shared database).
#
# Callers set CTX, POD, NS before sourcing.

pg() { # pg <db> [psql args...]   — stdin passes through (for -f -)
  local db="$1"; shift
  case "$CTX" in
    docker:*) docker exec -i "${CTX#docker:}" psql -U postgres -X -v ON_ERROR_STOP=1 -d "$db" "$@" ;;
    *)        kubectl --context "$CTX" -n "$NS" exec -i "$POD" -c postgres -- \
                psql -X -v ON_ERROR_STOP=1 -d "$db" "$@" ;;
  esac
}

pgq() { # pgq <db> <sql>  — a single unaligned, tuples-only result
  pg "$1" -tAq -c "$2"
}

pgsh() { # pgsh <shell command>  — run a shell command next to the server (pg_dump | pg_restore)
  case "$CTX" in
    docker:*) docker exec -i "${CTX#docker:}" sh -c "$1" ;;
    *)        kubectl --context "$CTX" -n "$NS" exec -i "$POD" -c postgres -- sh -c "$1" ;;
  esac
}
