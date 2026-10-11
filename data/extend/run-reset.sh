#!/usr/bin/env bash
# LR (2026-10-11, ruling 11) — undo the extension of a world: delete every row extend.sql wrote, keep
# the originals and each fact's recorded base end, empty `_extend_meta`. Then `run-extend.sh` copies
# every week again from the base — the way to apply a changed `extend.conf` (order_offset) to a world
# that was already extended.
#
# Runs reset.sql as ONE transaction, as the postgres superuser over the pod-local socket (the
# run-extend.sh path), then VACUUMs and ANALYZEs the seven facts and prints each fact's last date.
#
# Usage: ./run-reset.sh <kube-context> <database> [pod]
#        `just extend-reset <us|cz> [ctx]` wraps it with the world's database and the pod.
# Refuses `tpc-ds-1g`, which is never extended.
set -euo pipefail
CTX="${1:?usage: run-reset.sh <kube-context> <database> [pod]}"; DB="${2:?database}"; POD="${3:-hartland-pg-1}"
NS="${EXTEND_NS:-data}"
DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
source "$DIR/lib.sh"

if [ "$DB" = "tpc-ds-1g" ]; then
  echo "refusing to touch tpc-ds-1g — it is never extended" >&2; exit 2
fi

echo "== resetting the extension of $DB on $CTX/$POD (single transaction) =="
t0=$(date +%s)
pg "$DB" -q -1 -f - < "$DIR/reset.sql"
t1=$(date +%s)

# VACUUM, not just ANALYZE: the delete leaves every copied row behind as a dead tuple, and on the CZ
# world a reset deleted less than autovacuum's 20 % threshold of each fact, so nothing reclaimed them —
# after the first reset (2026-10-11) `inventory` alone carried 1.97 M dead rows, which every scan read
# past until a manual VACUUM (69 s for the facts). Outside the transaction — VACUUM cannot run inside
# one — and after it, so a failed reset vacuums nothing.
echo "== VACUUM (ANALYZE) =="
pg "$DB" -q -c "VACUUM (ANALYZE) store_sales, catalog_sales, web_sales, store_returns, catalog_returns, web_returns, inventory;"

echo "== each fact's last date (= its base end after a reset) =="
pg "$DB" -P footer=off -f - <<'SQL'
SELECT b.fact, b.base_end,
       CASE b.fact
         WHEN 'store_sales'   THEN (SELECT max(d.d_date) FROM store_sales   JOIN date_dim d ON d.d_date_sk = ss_sold_date_sk)
         WHEN 'catalog_sales' THEN (SELECT max(d.d_date) FROM catalog_sales JOIN date_dim d ON d.d_date_sk = cs_sold_date_sk)
         WHEN 'web_sales'     THEN (SELECT max(d.d_date) FROM web_sales     JOIN date_dim d ON d.d_date_sk = ws_sold_date_sk)
         WHEN 'inventory'     THEN (SELECT max(d.d_date) FROM inventory     JOIN date_dim d ON d.d_date_sk = inv_date_sk)
       END AS last_date
FROM _extend_base b ORDER BY b.fact;
SELECT count(*) AS extended_weeks_left FROM _extend_meta;
SQL
echo "Done in $((t1 - t0)) s (transaction). Extend again with run-extend.sh / just extend-data."
