#!/usr/bin/env bash
# LR-P4 T1 — one script, both worlds (C-8·7): the CZ world's extended amounts keep the 10 Kč
# rounding (>= 100 Kč, data/localize-cz/fx.conf); the US world's keep cents and are not 10-rounded.
#   test-world-neutral.sh <ctx> <db> [pod]
set -uo pipefail
CTX="${1:?usage: test-world-neutral.sh <ctx> <db> [pod]}"; DB="${2:?db}"; POD="${3:-hartland-pg-1}"; NS="${EXTEND_NS:-data}"
source "$(dirname "$0")/lib-test.sh"

cz=$(pgq "$DB" "SELECT CASE WHEN to_regclass('public._localize_meta') IS NULL THEN 'f' ELSE (SELECT (count(*) > 0)::text FROM _localize_meta WHERE step = 'czk_fx') END" | cut -c1)
echo "== world rounding on $DB ($( [ "$cz" = t ] && echo CZ || echo US ))"

# every numeric column of the six order facts, over their extended rows
for f in store_sales catalog_sales web_sales store_returns catalog_returns web_returns; do
  cols=$(pgq "$DB" "SELECT string_agg(quote_ident(column_name), ' ') FROM information_schema.columns WHERE table_schema = 'public' AND table_name = '$f' AND data_type = 'numeric'")
  big=""; dec=""; tot=""
  for c in $cols; do
    big+="count(*) FILTER (WHERE abs(x.$c) >= 100 AND x.$c % 10 <> 0) + "
    dec+="count(*) FILTER (WHERE x.$c <> round(x.$c, 2)) + "
    tot+="count(*) FILTER (WHERE abs(x.$c) >= 100) + "
  done
  r=$(pgq "$DB" "SELECT (${big}0) || ' ' || (${dec}0) || ' ' || (${tot}0) FROM ($(extended_rows_sql "$f")) x" 2>/dev/null)
  read -r not10 frac big_n <<<"$r"
  expect "$f: amounts carry at most 2 decimals" "$frac" -eq 0
  expect "$f: has extended amounts >= 100" "$big_n" -gt 0
  if [ "$cz" = t ]; then
    expect "$f: CZ — every extended amount >= 100 Kč is a multiple of 10" "$not10" -eq 0
  else
    expect "$f: US — the 10 Kč rule is not applied (amounts >= 100 not all multiples of 10)" "$not10" -gt 0
  fi
done
finish
