#!/usr/bin/env bash
# AU-hartland P1 (contracts §1, §5) — build the automation extension of a world: the H-1/H-2 ERP tables derived
# from its TPC-DS facts (README.md has the per-table derivation spec) and the demo day they are built for.
# Step 9 of the data build (data/README.md).
#
# ONE transaction, as the postgres superuser over the pod-local socket (the run-extend.sh path); the scripts
# create the tables as the owner of the facts. Guarded by `_automation_meta`: a world already built at this
# as_of is a no-op, a world built at another as_of is refused — reset first (run-reset.sh). Ends with ANALYZE
# and a summary.
#
# Usage: ./run-automation.sh <kube-context> <database> [as-of] [pod]
#        as-of defaults to the Monday of the world's last extended week; pod to hartland-pg-1.
#        `just automation-data <us|cz> [as-of] [ctx]` wraps it with the world's database and the pod.
# Refuses `tpc-ds-1g`, and a world that was never extended (the extension's demo day lies in the extended year).
set -euo pipefail
CTX="${1:?usage: run-automation.sh <kube-context> <database> [as-of] [pod]}"; DB="${2:?database}"
AS_OF="${3:-}"; POD="${4:-hartland-pg-1}"
NS="${EXTEND_NS:-data}"
DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
source "$DIR/lib.sh"

# The build, in order. Every script records its step in `_automation_meta`; 45-verify replays the recipes over
# the plants and fails the build on any disagreement; the views come after the tables they read, the keys after
# the data (one validating scan each, not a trigger check per inserted row).
STEPS="10-ddl 20-orders 21-pricing 22-invoices 23-outages 24-centers 25-calendar 26-stock 30-returns 31-receipts 32-settlement 40-plant 45-verify 50-expected 60-events"
VIEWS="return_request document_flow"
KEYS="80-keys"

if [ "$DB" = "tpc-ds-1g" ]; then
  echo "refusing to build into tpc-ds-1g — the pristine source must stay as dsdgen wrote it" >&2; exit 2
fi
if [ -n "$AS_OF" ] && ! [[ "$AS_OF" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "as-of must be YYYY-MM-DD, got '$AS_OF'" >&2; exit 2
fi

# A query naming a missing table fails at parse time, CASE or not: ask whether it exists first.
has() { [ "$(pgq "$DB" "SELECT to_regclass('public.$1') IS NOT NULL")" = t ]; }

weeks=0; has _extend_meta && weeks=$(pgq "$DB" "SELECT count(*) FROM _extend_meta")
if [ "$weeks" -eq 0 ]; then
  echo "refusing: $DB was never extended (no _extend_meta weeks) — run data/extend first (just extend-data)" >&2; exit 2
fi
if [ -z "$AS_OF" ]; then
  AS_OF=$(pgq "$DB" "SELECT d_date FROM date_dim WHERE d_week_seq = (SELECT max(target_week_seq) FROM _extend_meta)
                     AND extract(isodow FROM d_date) = 1")
fi

# The world's currency: CZ ⇔ localize-cz scaled the facts (its guard row). Its FX rate comes from the one file
# that defines it; the US world's is 1.
if has _localize_meta && [ "$(pgq "$DB" "SELECT EXISTS (SELECT 1 FROM _localize_meta WHERE step = 'czk_fx')")" = t ]; then
  LOCALE=cz; FX_CONF="$(cat "$DIR/../localize-cz/fx.conf")"
else
  LOCALE=us; FX_CONF='\set fx 1'
fi

# The seeds and the timeline leave the database as files: expected/<world>/<recipe>.csv and events/<world>.csv
# (committed from the certification runs). AUTOMATION_OUT moves them (the suite writes under $TMPDIR).
OUT="${AUTOMATION_OUT:-$DIR}"
export_files() {
  mkdir -p "$OUT/expected/$LOCALE" "$OUT/events"
  local r
  for r in release_order decide_return monitor_inbound settle reorder_proposals winback; do
    pg "$DB" -q -c "\copy (SELECT key, route, verdict_reason_template, detail_count FROM _automation_expected WHERE recipe = '$r' ORDER BY lpad(key, 24, '0'), route) TO STDOUT WITH (FORMAT csv, HEADER)" \
      > "$OUT/expected/$LOCALE/$r.csv"
  done
  pg "$DB" -q -c "SET TIME ZONE 'Europe/Prague'" \
              -c "\copy (SELECT seq, kind, at, payload, demo FROM _automation_events ORDER BY seq) TO STDOUT WITH (FORMAT csv, HEADER)" \
    > "$OUT/events/$LOCALE.csv"
  echo "== wrote $OUT/expected/$LOCALE/*.csv and $OUT/events/$LOCALE.csv"
}

built=""; has _automation_meta && built=$(pgq "$DB" "SELECT as_of FROM _automation_meta WHERE step = 'build'")
if [ -n "$built" ]; then
  if [ "$built" = "$AS_OF" ]; then
    echo "== $DB: the automation extension is already built as of $AS_OF — nothing to do"
    export_files; exit 0
  fi
  echo "refusing: $DB was built as of $built, not $AS_OF — reset first (run-reset.sh / just automation-reset)" >&2; exit 2
fi

echo "== building the automation extension of $DB on $CTX as of $AS_OF ($LOCALE; single transaction) =="
t0=$(date +%s)
{
  echo "$FX_CONF"
  cat "$DIR/automation.conf"
  for s in $STEPS; do cat "$DIR/$s.sql"; done
  for v in $VIEWS; do cat "$DIR/../views/$v.sql"; done
  for s in $KEYS; do cat "$DIR/$s.sql"; done
  echo "INSERT INTO _automation_meta (step, as_of, rows) VALUES ('build', :'as_of', NULL);"
} | pg "$DB" -q -1 -v as_of="$AS_OF" -v locale="$LOCALE" -f -
t1=$(date +%s)

echo "== ANALYZE =="
pg "$DB" -q -c "ANALYZE sales_order, sales_line, price_list, customer_price, invoice, warehouse_outage, return_request_hdr,
                       return_request_line, return_receipt, credit_note, refund_payment, replacement_shipment, customer, date_dim;"

echo "== _automation_meta =="
pg "$DB" -P footer=off -c "SELECT step, as_of, rows FROM _automation_meta ORDER BY step = 'build', step;"
export_files
echo "== R-A (90-recon.sql; just automation-recon diffs it against recon/R-A-$LOCALE.md) =="
pg "$DB" -q -f - < "$DIR/90-recon.sql"
echo "Done in $((t1 - t0)) s (transaction) — $DB is built as of $AS_OF."
