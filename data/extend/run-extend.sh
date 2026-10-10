#!/usr/bin/env bash
# LR-P4 (contracts C-8) — extend a world's facts to <until-date> by copying the template year
# (2024) forward, week by week. Idempotent and incremental: re-run with a later date before a show
# ("prolong") and only the new weeks are added; the same date again is a no-op. README.md has the
# per-table copy spec.
#
# Runs extend.sql as ONE transaction, as the postgres superuser over the pod-local socket (the
# run-redate.sh path), then ANALYZEs the seven facts and prints the _extend_meta summary.
#
# Usage: ./run-extend.sh [kube-context] [database] [until-date] [pod]
#        defaults:        dsk            hartland_us today        hartland-pg-1
#        `just extend-data <us|cz> <until> [ctx]` wraps it with the world's database and the pod.
# Refuses `tpc-ds-1g` — the pristine source stays pristine.
set -euo pipefail
CTX="${1:-dsk}"; DB="${2:-hartland_us}"; UNTIL="${3:-$(date +%F)}"; POD="${4:-hartland-pg-1}"
NS="${EXTEND_NS:-data}"
DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
source "$DIR/lib.sh"

if [ "$DB" = "tpc-ds-1g" ]; then
  echo "refusing to extend tpc-ds-1g — the pristine source must stay as dsdgen wrote it" >&2; exit 2
fi
if ! [[ "$UNTIL" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "until-date must be YYYY-MM-DD, got '$UNTIL'" >&2; exit 2
fi

echo "== extending $DB on $CTX/$POD to $UNTIL (single transaction) =="
t0=$(date +%s)
# extend.conf first, then the script without its \ir (the pod has neither file)
{ cat "$DIR/extend.conf"; grep -v '^\\ir ' "$DIR/extend.sql"; } |
  pg "$DB" -q -1 -v until="$UNTIL" -f -
t1=$(date +%s)

echo "== ANALYZE =="
pg "$DB" -q -c "ANALYZE store_sales, catalog_sales, web_sales, store_returns, catalog_returns, web_returns, inventory;"

echo "== _extend_meta summary =="
pg "$DB" -P footer=off -f - <<'SQL'
SELECT count(*) AS weeks,
       (SELECT min(d_date) FROM date_dim WHERE d_week_seq = min(m.target_week_seq)) AS first_day,
       (SELECT max(d_date) FROM date_dim WHERE d_week_seq = max(m.target_week_seq)) AS last_day,
       sum((rows->>'store_sales')::bigint)     AS store_sales,
       sum((rows->>'catalog_sales')::bigint)   AS catalog_sales,
       sum((rows->>'web_sales')::bigint)       AS web_sales,
       sum((rows->>'store_returns')::bigint)   AS store_returns,
       sum((rows->>'catalog_returns')::bigint) AS catalog_returns,
       sum((rows->>'web_returns')::bigint)     AS web_returns,
       sum((rows->>'inventory')::bigint)       AS inventory
FROM _extend_meta m;
SELECT 'store_sales' AS fact, max(d.d_date) AS last_date FROM store_sales JOIN date_dim d ON d.d_date_sk = ss_sold_date_sk
UNION ALL SELECT 'catalog_sales', max(d.d_date) FROM catalog_sales JOIN date_dim d ON d.d_date_sk = cs_sold_date_sk
UNION ALL SELECT 'web_sales', max(d.d_date) FROM web_sales JOIN date_dim d ON d.d_date_sk = ws_sold_date_sk
UNION ALL SELECT 'inventory', max(d.d_date) FROM inventory JOIN date_dim d ON d.d_date_sk = inv_date_sk;
SQL
echo "Done in $((t1 - t0)) s (transaction) — data now runs to the end of the week holding $UNTIL."
