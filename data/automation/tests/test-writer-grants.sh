#!/usr/bin/env bash
# AU O1 / R276-B: table creation owns column grants, including after reset/rebuild.
# Run only on a scratch fixture: test-writer-grants.sh <ctx> <fixture-db> [pod].
set -euo pipefail
CTX="${1:?context}"; SRC="${2:?fixture database}"; POD="${3:-hartland-pg-1}"; NS="${EXTEND_NS:-data}"
source "$(dirname "$0")/lib-test.sh"
S="${SRC}_au_writer"; W="${S}_writer"
cleanup() {
  drop_scratch "$S"
  pgq postgres "DROP ROLE IF EXISTS \"$W\"" >/dev/null
}
trap cleanup EXIT
scratch_copy "$SRC" "$S"
run_automation "$S"
ok 'build succeeds without a world writer role'
run_reset "$S"
pgq postgres "CREATE ROLE \"$W\" NOLOGIN" >/dev/null
for cycle in first rebuilt; do
  run_automation "$S"
  expect "$cycle: schema usage" "$(pgq "$S" "SELECT has_schema_privilege('$W', 'public', 'USAGE')")" = t
  for table in sales_order return_request_line; do
    expect "$cycle: $table readable" "$(pgq "$S" "SELECT has_table_privilege('$W', 'public.$table', 'SELECT')")" = t
    expect "$cycle: $table no INSERT or DELETE" "$(pgq "$S" "SELECT has_table_privilege('$W', 'public.$table', 'INSERT') OR has_table_privilege('$W', 'public.$table', 'DELETE')")" = f
  done
  expect "$cycle: exactly the four writable columns" "$(pgq "$S" "SELECT string_agg(table_name || '.' || column_name, ',' ORDER BY table_name, column_name) FROM information_schema.columns WHERE table_schema='public' AND has_column_privilege('$W', quote_ident(table_schema) || '.' || quote_ident(table_name), column_name, 'UPDATE')")" = 'return_request_line.rl_state,return_request_line.rl_way,sales_order.so_held_for,sales_order.so_state'
  expect "$cycle: loader internals unreadable" "$(pgq "$S" "SELECT has_table_privilege('$W', 'public._automation_meta', 'SELECT')")" = f
  if [ "$cycle" = first ]; then run_reset "$S"; fi
done
finish
