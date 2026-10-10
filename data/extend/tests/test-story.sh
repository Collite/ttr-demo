#!/usr/bin/env bash
# LR-P4 T1 — the story in extended weeks is the RECOVERED one (C-8·6): the meltdown DC back at
# ~20 % of marketplace revenue, no stockout streak, no late-delivery reason skew, and returns at
# the template year's share of revenue, month for month.   test-story.sh <ctx> <db> [pod]
set -uo pipefail
CTX="${1:?usage: test-story.sh <ctx> <db> [pod]}"; DB="${2:?db}"; POD="${3:-hartland-pg-1}"; NS="${EXTEND_NS:-data}"
source "$(dirname "$0")/lib-test.sh"
DC=5; LATE=3

echo "== story on $DB (extended weeks only)"
expect_between "meltdown DC share of marketplace revenue, %" \
  "$(pgq "$DB" "SELECT round(100.0 * sum(x.cs_ext_sales_price) FILTER (WHERE x.cs_warehouse_sk = $DC) / sum(x.cs_ext_sales_price), 2) FROM ($(extended_rows_sql catalog_sales)) x" 2>/dev/null)" 19 21
expect_between "meltdown DC zero-inventory share, %" \
  "$(pgq "$DB" "SELECT round(100.0 * count(*) FILTER (WHERE x.inv_quantity_on_hand = 0) / count(*), 3) FROM ($(extended_rows_sql inventory)) x WHERE x.inv_warehouse_sk = $DC" 2>/dev/null)" 0 0.2
expect_between "late-delivery reason share among the meltdown DC's extended returns, %" \
  "$(pgq "$DB" "SELECT round(100.0 * count(*) FILTER (WHERE cr_reason_sk = $LATE) / nullif(count(*), 0), 2) FROM catalog_returns WHERE cr_order_number >= 1000000000 AND cr_warehouse_sk = $DC" 2>/dev/null)" 0 5

# Returns vs revenue in the last whole extended month, against the SAME month of the template year.
# The task's "≈ 5 %" is the annual ratio; per month TPC-DS runs 2–12 % (revenue is Q4-heavy and
# returns trail their sales by months), so a fixed 5 % ± 1 pt would fail on honest data. Same
# month of 2024 ± 1 pt is the property that matters: the copied months return like the template.
M=$(pgq "$DB" "SELECT to_char(date_trunc('month', max(d.d_date) + 1) - interval '1 month', 'MM') FROM catalog_sales JOIN date_dim d ON d.d_date_sk = cs_sold_date_sk" 2>/dev/null)
Y=$(pgq "$DB" "SELECT to_char(date_trunc('month', max(d.d_date) + 1) - interval '1 month', 'YYYY') FROM catalog_sales JOIN date_dim d ON d.d_date_sk = cs_sold_date_sk" 2>/dev/null)
ratio() { # ratio <sales> <sale_date> <amount> <returns> <return_date> <return_amount> <year>
  pgq "$DB" "SELECT round(100.0 * (SELECT sum($6) FROM $4 JOIN date_dim d ON d.d_date_sk = $5 WHERE d.d_year = $7 AND d.d_moy = $M)
                              / (SELECT sum($3) FROM $1 JOIN date_dim d ON d.d_date_sk = $2 WHERE d.d_year = $7 AND d.d_moy = $M), 2)" 2>/dev/null
}
for c in store:store_sales:ss_sold_date_sk:ss_ext_sales_price:store_returns:sr_returned_date_sk:sr_return_amt \
         marketplace:catalog_sales:cs_sold_date_sk:cs_ext_sales_price:catalog_returns:cr_returned_date_sk:cr_return_amount \
         web:web_sales:ws_sold_date_sk:ws_ext_sales_price:web_returns:wr_returned_date_sk:wr_return_amt; do
  IFS=: read -r ch st sd sa rt rd ra <<<"$c"
  tmpl=$(ratio "$st" "$sd" "$sa" "$rt" "$rd" "$ra" 2024)
  ext=$(ratio "$st" "$sd" "$sa" "$rt" "$rd" "$ra" "${Y:-0}")
  if [ -n "$tmpl" ]; then
    expect_between "$ch: returns in $Y-$M as % of revenue, vs $tmpl % in 2024-$M" "$ext" \
      "$(python3 -c "print(round($tmpl - 1, 2))")" "$(python3 -c "print(round($tmpl + 1, 2))")"
  else bad "$ch: no 2024-$M baseline"; fi
done
finish
