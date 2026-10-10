#!/usr/bin/env bash
# Demo-TPCDS Q-1 data recon — read-only aggregate battery against `tpc-ds-1g` on the dsk cluster.
#
# Usage:   ./run-recon.sh [kube-context] [database] [pod] [role]
#          (defaults: dsk, tpc-ds-1g, test-pg-1, tpcds_readonly)
#          post-surgery baselines: ./run-recon.sh dsk hartland
#          the hartland-pg fixture:  ./run-recon.sh dsk hartland_cz hartland-pg-1 hartland_cz_readonly
#          one query only:           RECON_ONLY=r14_extended_months ./run-recon.sh …
# Access:  kubectl exec into the CNPG pod `test-pg-1` (ns `data`), psql over the local socket,
#          SET ROLE tpcds_readonly — the same path the WS-T1 runbook / MP-2 smoke used.
# Output:  ./results/rNN_*.csv (small aggregates, all committable). Commit results/ so the
#          design session can analyze them. Expected total runtime: a few minutes at SF1.
set -euo pipefail
CTX="${1:-dsk}"; DB="${2:-tpc-ds-1g}"; NS="data"; POD="${3:-test-pg-1}"; ROLE="${4:-tpcds_readonly}"
DIR="$(cd "$(dirname "$0")" && pwd)"; OUT="$DIR/results"; mkdir -p "$OUT"

q() { # q <name>  (SQL on stdin)
  local name="$1"
  if [ -n "${RECON_ONLY:-}" ] && [ "$name" != "$RECON_ONLY" ]; then cat > /dev/null; return; fi
  printf '== %s ' "$name"
  { echo "SET ROLE $ROLE;"; cat; } |
    kubectl --context "$CTX" -n "$NS" exec -i "$POD" -c postgres -- \
      psql -q --csv -v ON_ERROR_STOP=1 -d "$DB" -f - > "$OUT/$name.csv"
  printf -- '-> %s lines\n' "$(wc -l < "$OUT/$name.csv" | tr -d ' ')"
}

# ---------------------------------------------------------------- r00 sanity
q r00_rowcounts <<'SQL'
SELECT 'store_sales' t, count(*) n FROM store_sales
UNION ALL SELECT 'store_returns', count(*) FROM store_returns
UNION ALL SELECT 'catalog_sales', count(*) FROM catalog_sales
UNION ALL SELECT 'catalog_returns', count(*) FROM catalog_returns
UNION ALL SELECT 'web_sales', count(*) FROM web_sales
UNION ALL SELECT 'web_returns', count(*) FROM web_returns
UNION ALL SELECT 'inventory', count(*) FROM inventory
UNION ALL SELECT 'customer', count(*) FROM customer
UNION ALL SELECT 'item', count(*) FROM item
UNION ALL SELECT 'promotion', count(*) FROM promotion
UNION ALL SELECT 'warehouse', count(*) FROM warehouse
UNION ALL SELECT 'store', count(*) FROM store
UNION ALL SELECT 'call_center', count(*) FROM call_center
UNION ALL SELECT 'web_site', count(*) FROM web_site
UNION ALL SELECT 'reason', count(*) FROM reason
ORDER BY 1;
SQL

# ------------------------------------------------- r01 channel × year trends
# Does the web grow? Does catalog decline? The slump's natural substrate.
q r01_channel_year <<'SQL'
SELECT 'store' AS channel, d.d_year, count(*) AS line_items,
       count(DISTINCT ss_ticket_number) AS orders, sum(ss_quantity) AS qty,
       round(sum(ss_ext_sales_price)::numeric) AS revenue,
       round(sum(ss_net_profit)::numeric) AS net_profit
FROM store_sales JOIN date_dim d ON ss_sold_date_sk = d.d_date_sk
GROUP BY d.d_year
UNION ALL
SELECT 'catalog', d.d_year, count(*), count(DISTINCT cs_order_number), sum(cs_quantity),
       round(sum(cs_ext_sales_price)::numeric), round(sum(cs_net_profit)::numeric)
FROM catalog_sales JOIN date_dim d ON cs_sold_date_sk = d.d_date_sk
GROUP BY d.d_year
UNION ALL
SELECT 'web', d.d_year, count(*), count(DISTINCT ws_order_number), sum(ws_quantity),
       round(sum(ws_ext_sales_price)::numeric), round(sum(ws_net_profit)::numeric)
FROM web_sales JOIN date_dim d ON ws_sold_date_sk = d.d_date_sk
GROUP BY d.d_year
ORDER BY channel, d_year;
SQL

# --------------------------------------------- r02 monthly seasonality shape
q r02_channel_month <<'SQL'
SELECT 'store' AS channel, d.d_year, d.d_moy,
       round(sum(ss_ext_sales_price)::numeric) AS revenue
FROM store_sales JOIN date_dim d ON ss_sold_date_sk = d.d_date_sk
GROUP BY d.d_year, d.d_moy
UNION ALL
SELECT 'catalog', d.d_year, d.d_moy, round(sum(cs_ext_sales_price)::numeric)
FROM catalog_sales JOIN date_dim d ON cs_sold_date_sk = d.d_date_sk
GROUP BY d.d_year, d.d_moy
UNION ALL
SELECT 'web', d.d_year, d.d_moy, round(sum(ws_ext_sales_price)::numeric)
FROM web_sales JOIN date_dim d ON ws_sold_date_sk = d.d_date_sk
GROUP BY d.d_year, d.d_moy
ORDER BY channel, d_year, d_moy;
SQL

# ------------------------------------------------- r03 returns volume by year
q r03_returns_year <<'SQL'
SELECT 'store' AS channel, d.d_year, count(*) AS return_lines,
       round(sum(sr_return_amt)::numeric) AS return_amt,
       round(sum(sr_net_loss)::numeric) AS net_loss
FROM store_returns JOIN date_dim d ON sr_returned_date_sk = d.d_date_sk
GROUP BY d.d_year
UNION ALL
SELECT 'catalog', d.d_year, count(*), round(sum(cr_return_amount)::numeric),
       round(sum(cr_net_loss)::numeric)
FROM catalog_returns JOIN date_dim d ON cr_returned_date_sk = d.d_date_sk
GROUP BY d.d_year
UNION ALL
SELECT 'web', d.d_year, count(*), round(sum(wr_return_amt)::numeric),
       round(sum(wr_net_loss)::numeric)
FROM web_returns JOIN date_dim d ON wr_returned_date_sk = d.d_date_sk
GROUP BY d.d_year
ORDER BY channel, d_year;
SQL

# --------------------------------------------------- r04 return-reason mix
q r04_reason_mix <<'SQL'
SELECT 'store' AS channel, r.r_reason_desc, count(*) AS lines,
       round(sum(sr_return_amt)::numeric) AS amt
FROM store_returns JOIN reason r ON sr_reason_sk = r.r_reason_sk
GROUP BY r.r_reason_desc
UNION ALL
SELECT 'catalog', r.r_reason_desc, count(*), round(sum(cr_return_amount)::numeric)
FROM catalog_returns JOIN reason r ON cr_reason_sk = r.r_reason_sk
GROUP BY r.r_reason_desc
UNION ALL
SELECT 'web', r.r_reason_desc, count(*), round(sum(wr_return_amt)::numeric)
FROM web_returns JOIN reason r ON wr_reason_sk = r.r_reason_sk
GROUP BY r.r_reason_desc
ORDER BY channel, amt DESC;
SQL

# ------------------------------------- r05 category × channel × year revenue
q r05_category_channel_year <<'SQL'
SELECT 'store' AS channel, coalesce(i.i_category,'(null)') AS category, d.d_year,
       round(sum(ss_ext_sales_price)::numeric) AS revenue
FROM store_sales JOIN date_dim d ON ss_sold_date_sk = d.d_date_sk
                 JOIN item i ON ss_item_sk = i.i_item_sk
GROUP BY 2, d.d_year
UNION ALL
SELECT 'catalog', coalesce(i.i_category,'(null)'), d.d_year,
       round(sum(cs_ext_sales_price)::numeric)
FROM catalog_sales JOIN date_dim d ON cs_sold_date_sk = d.d_date_sk
                   JOIN item i ON cs_item_sk = i.i_item_sk
GROUP BY 2, d.d_year
UNION ALL
SELECT 'web', coalesce(i.i_category,'(null)'), d.d_year,
       round(sum(ws_ext_sales_price)::numeric)
FROM web_sales JOIN date_dim d ON ws_sold_date_sk = d.d_date_sk
               JOIN item i ON ws_item_sk = i.i_item_sk
GROUP BY 2, d.d_year
ORDER BY channel, category, d_year;
SQL

# ------------------------------------------------ r06 geography (two lenses)
q r06a_store_state_year <<'SQL'
SELECT s.s_state, d.d_year, round(sum(ss_ext_sales_price)::numeric) AS revenue,
       count(DISTINCT s.s_store_sk) AS stores
FROM store_sales JOIN date_dim d ON ss_sold_date_sk = d.d_date_sk
                 JOIN store s ON ss_store_sk = s.s_store_sk
GROUP BY s.s_state, d.d_year ORDER BY s.s_state, d.d_year;
SQL

q r06b_customer_state_year <<'SQL'
SELECT 'catalog' AS channel, ca.ca_state, d.d_year,
       round(sum(cs_ext_sales_price)::numeric) AS revenue
FROM catalog_sales JOIN date_dim d ON cs_sold_date_sk = d.d_date_sk
     JOIN customer c ON cs_bill_customer_sk = c.c_customer_sk
     JOIN customer_address ca ON c.c_current_addr_sk = ca.ca_address_sk
GROUP BY ca.ca_state, d.d_year
UNION ALL
SELECT 'web', ca.ca_state, d.d_year, round(sum(ws_ext_sales_price)::numeric)
FROM web_sales JOIN date_dim d ON ws_sold_date_sk = d.d_date_sk
     JOIN customer c ON ws_bill_customer_sk = c.c_customer_sk
     JOIN customer_address ca ON c.c_current_addr_sk = ca.ca_address_sk
GROUP BY ca.ca_state, d.d_year
ORDER BY channel, ca_state, d_year;
SQL

# ------------------------------- r07 cross-channel customer overlap per year
q r07_channel_overlap <<'SQL'
WITH u AS (
  SELECT ss_customer_sk AS c, d.d_year, 's' AS ch
  FROM store_sales JOIN date_dim d ON ss_sold_date_sk = d.d_date_sk
  WHERE ss_customer_sk IS NOT NULL
  UNION ALL
  SELECT cs_bill_customer_sk, d.d_year, 'c'
  FROM catalog_sales JOIN date_dim d ON cs_sold_date_sk = d.d_date_sk
  WHERE cs_bill_customer_sk IS NOT NULL
  UNION ALL
  SELECT ws_bill_customer_sk, d.d_year, 'w'
  FROM web_sales JOIN date_dim d ON ws_sold_date_sk = d.d_date_sk
  WHERE ws_bill_customer_sk IS NOT NULL
), buyers AS (
  SELECT c, d_year, bool_or(ch='s') AS in_store, bool_or(ch='c') AS in_catalog,
         bool_or(ch='w') AS in_web
  FROM u GROUP BY c, d_year
)
SELECT d_year, in_store, in_catalog, in_web, count(*) AS customers
FROM buyers GROUP BY 1,2,3,4 ORDER BY 1,2,3,4;
SQL

# ----------------------------------------------- r08 inventory / stockouts
q r08a_inventory_zero_share <<'SQL'
SELECT d.d_year, count(*) AS snapshot_rows,
       count(*) FILTER (WHERE inv_quantity_on_hand = 0) AS zero_rows,
       round(100.0 * count(*) FILTER (WHERE inv_quantity_on_hand = 0) / count(*), 2)
         AS zero_pct
FROM inventory JOIN date_dim d ON inv_date_sk = d.d_date_sk
GROUP BY d.d_year ORDER BY d.d_year;
SQL

q r08b_warehouse_zero_weeks <<'SQL'
SELECT w.w_warehouse_name, d.d_year,
       count(*) FILTER (WHERE inv_quantity_on_hand = 0) AS zero_rows,
       count(DISTINCT inv_item_sk) FILTER (WHERE inv_quantity_on_hand = 0)
         AS items_with_zero
FROM inventory JOIN date_dim d ON inv_date_sk = d.d_date_sk
               JOIN warehouse w ON inv_warehouse_sk = w.w_warehouse_sk
GROUP BY w.w_warehouse_name, d.d_year ORDER BY w.w_warehouse_name, d.d_year;
SQL

# --------------------------------------------------- r09 promo participation
q r09_promo_share <<'SQL'
SELECT 'store' AS channel, d.d_year,
       round(100.0 * count(ss_promo_sk) / count(*), 2) AS promo_line_pct,
       round(100.0 * sum(ss_ext_sales_price) FILTER (WHERE ss_promo_sk IS NOT NULL)
             / nullif(sum(ss_ext_sales_price),0), 2) AS promo_rev_pct
FROM store_sales JOIN date_dim d ON ss_sold_date_sk = d.d_date_sk
GROUP BY d.d_year
UNION ALL
SELECT 'catalog', d.d_year,
       round(100.0 * count(cs_promo_sk) / count(*), 2),
       round(100.0 * sum(cs_ext_sales_price) FILTER (WHERE cs_promo_sk IS NOT NULL)
             / nullif(sum(cs_ext_sales_price),0), 2)
FROM catalog_sales JOIN date_dim d ON cs_sold_date_sk = d.d_date_sk
GROUP BY d.d_year
UNION ALL
SELECT 'web', d.d_year,
       round(100.0 * count(ws_promo_sk) / count(*), 2),
       round(100.0 * sum(ws_ext_sales_price) FILTER (WHERE ws_promo_sk IS NOT NULL)
             / nullif(sum(ws_ext_sales_price),0), 2)
FROM web_sales JOIN date_dim d ON ws_sold_date_sk = d.d_date_sk
GROUP BY d.d_year
ORDER BY channel, d_year;
SQL

# ------------------------------------------- r10 buyer demographics by channel
q r10a_buyer_age_year <<'SQL'
SELECT 'store' AS channel, d.d_year, count(DISTINCT ss_customer_sk) AS buyers,
       round(avg(2003 - c.c_birth_year), 1) AS avg_age_2003
FROM store_sales JOIN date_dim d ON ss_sold_date_sk = d.d_date_sk
     JOIN customer c ON ss_customer_sk = c.c_customer_sk
WHERE c.c_birth_year IS NOT NULL GROUP BY d.d_year
UNION ALL
SELECT 'catalog', d.d_year, count(DISTINCT cs_bill_customer_sk),
       round(avg(2003 - c.c_birth_year), 1)
FROM catalog_sales JOIN date_dim d ON cs_sold_date_sk = d.d_date_sk
     JOIN customer c ON cs_bill_customer_sk = c.c_customer_sk
WHERE c.c_birth_year IS NOT NULL GROUP BY d.d_year
UNION ALL
SELECT 'web', d.d_year, count(DISTINCT ws_bill_customer_sk),
       round(avg(2003 - c.c_birth_year), 1)
FROM web_sales JOIN date_dim d ON ws_sold_date_sk = d.d_date_sk
     JOIN customer c ON ws_bill_customer_sk = c.c_customer_sk
WHERE c.c_birth_year IS NOT NULL GROUP BY d.d_year
ORDER BY channel, d_year;
SQL

q r10b_income_band_mix <<'SQL'
SELECT 'catalog' AS channel, ib.ib_lower_bound, ib.ib_upper_bound,
       count(DISTINCT cs_bill_customer_sk) AS buyers
FROM catalog_sales
     JOIN customer c ON cs_bill_customer_sk = c.c_customer_sk
     JOIN household_demographics hd ON c.c_current_hdemo_sk = hd.hd_demo_sk
     JOIN income_band ib ON hd.hd_income_band_sk = ib.ib_income_band_sk
GROUP BY 2, 3
UNION ALL
SELECT 'web', ib.ib_lower_bound, ib.ib_upper_bound,
       count(DISTINCT ws_bill_customer_sk)
FROM web_sales
     JOIN customer c ON ws_bill_customer_sk = c.c_customer_sk
     JOIN household_demographics hd ON c.c_current_hdemo_sk = hd.hd_demo_sk
     JOIN income_band ib ON hd.hd_income_band_sk = ib.ib_income_band_sk
GROUP BY 2, 3
ORDER BY channel, ib_lower_bound;
SQL

# --------------------------------------------------------- r11 hygiene facts
q r11_hygiene <<'SQL'
SELECT 'store_sales_dates' AS metric,
       min(d.d_date)::text || ' .. ' || max(d.d_date)::text AS value
FROM store_sales JOIN date_dim d ON ss_sold_date_sk = d.d_date_sk
UNION ALL
SELECT 'catalog_sales_dates', min(d.d_date)::text || ' .. ' || max(d.d_date)::text
FROM catalog_sales JOIN date_dim d ON cs_sold_date_sk = d.d_date_sk
UNION ALL
SELECT 'web_sales_dates', min(d.d_date)::text || ' .. ' || max(d.d_date)::text
FROM web_sales JOIN date_dim d ON ws_sold_date_sk = d.d_date_sk
UNION ALL
SELECT 'inventory_dates', min(d.d_date)::text || ' .. ' || max(d.d_date)::text
FROM inventory JOIN date_dim d ON inv_date_sk = d.d_date_sk
UNION ALL
SELECT 'ss_sold_date_null_pct',
       round(100.0 * count(*) FILTER (WHERE ss_sold_date_sk IS NULL) / count(*), 2)::text
FROM store_sales
UNION ALL
SELECT 'ss_customer_null_pct',
       round(100.0 * count(*) FILTER (WHERE ss_customer_sk IS NULL) / count(*), 2)::text
FROM store_sales
UNION ALL
SELECT 'categories', string_agg(DISTINCT i_category, ' | ') FROM item
UNION ALL
SELECT 'n_classes', count(DISTINCT i_class)::text FROM item
UNION ALL
SELECT 'n_brands', count(DISTINCT i_brand)::text FROM item
ORDER BY metric;
SQL

# ------------------------------------------------- r12 holiday revenue share
q r12_holiday_share <<'SQL'
SELECT 'store' AS channel, d.d_year,
       round(100.0 * sum(ss_ext_sales_price) FILTER (WHERE d.d_holiday = 'Y')
             / nullif(sum(ss_ext_sales_price),0), 2) AS holiday_rev_pct
FROM store_sales JOIN date_dim d ON ss_sold_date_sk = d.d_date_sk
GROUP BY d.d_year
UNION ALL
SELECT 'catalog', d.d_year,
       round(100.0 * sum(cs_ext_sales_price) FILTER (WHERE d.d_holiday = 'Y')
             / nullif(sum(cs_ext_sales_price),0), 2)
FROM catalog_sales JOIN date_dim d ON cs_sold_date_sk = d.d_date_sk
GROUP BY d.d_year
UNION ALL
SELECT 'web', d.d_year,
       round(100.0 * sum(ws_ext_sales_price) FILTER (WHERE d.d_holiday = 'Y')
             / nullif(sum(ws_ext_sales_price),0), 2)
FROM web_sales JOIN date_dim d ON ws_sold_date_sk = d.d_date_sk
GROUP BY d.d_year
ORDER BY channel, d_year;
SQL

# ------------------------- r13 warehouse slice (Q-6: seed calibration for the incident)
q r13_warehouse_share <<'SQL'
SELECT 'catalog' AS channel, coalesce(w.w_warehouse_name,'(null)') AS warehouse, d.d_year,
       count(*) AS line_items, round(sum(cs_ext_sales_price)::numeric) AS revenue
FROM catalog_sales JOIN date_dim d ON cs_sold_date_sk = d.d_date_sk
     LEFT JOIN warehouse w ON cs_warehouse_sk = w.w_warehouse_sk
GROUP BY 2, d.d_year
UNION ALL
SELECT 'web', coalesce(w.w_warehouse_name,'(null)'), d.d_year, count(*),
       round(sum(ws_ext_sales_price)::numeric)
FROM web_sales JOIN date_dim d ON ws_sold_date_sk = d.d_date_sk
     LEFT JOIN warehouse w ON ws_warehouse_sk = w.w_warehouse_sk
GROUP BY 2, d.d_year
ORDER BY channel, warehouse, d_year;
SQL

# ------------------------- r14 the extended months (LR-P4 data/extend, contracts C-8·8 → R1.md)
q r14_extended_months < "$DIR/queries/r14_extended_months.sql"

echo
echo "Done. $(ls "$OUT" | wc -l | tr -d ' ') CSVs in $OUT — commit results/ for analysis."
