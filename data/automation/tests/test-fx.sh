#!/usr/bin/env bash
# AU-hartland P1·S1.2 T1 — the CZ world: every money parameter of the plants is the US value × threshold_scale_cz
# (automation.conf: 25 — 1 250 000 Kč for the confirmation threshold, a round figure, not the FX rate). The scratch
# copy is turned into a CZ world by localize-cz's guard row (`_localize_meta` czk_fx), which is how the runner tells.
# Works on a throwaway copy of <db>:   test-fx.sh <ctx> <db> [pod]
set -uo pipefail
CTX="${1:?usage: test-fx.sh <ctx> <db> [pod]}"; SRC="${2:?db}"; POD="${3:-hartland-pg-1}"; NS="${EXTEND_NS:-data}"
source "$(dirname "$0")/lib-test.sh"
S="${SRC}_au_fx"
q() { pgq "$S" "$1"; }

echo "== the CZ world's scale, on a scratch copy of $SRC ($S)"
scratch_copy "$SRC" "$S"
# A US source becomes a CZ world the way localize-cz makes one: money columns widened (00-widen-money-columns.sql),
# scaled by the FX rate and rounded to a believable price (02-czk-fx.sql), and the guard row written.
if [ "$(q "SELECT to_regclass('public._localize_meta') IS NULL")" = t ]; then
  fx=$(awk '$1 == "\\set" && $2 == "fx" { print $3 }' "$AUTO_DIR/../localize-cz/fx.conf")
  czk() { echo "$1 = CASE WHEN $1 IS NULL THEN NULL WHEN abs($1 * $fx) < 100 THEN round($1 * $fx, 2) ELSE round($1 * $fx / 10.0) * 10 END"; }
  q "ALTER TABLE web_sales ALTER ws_sales_price TYPE numeric(10,2), ALTER ws_ext_sales_price TYPE numeric(10,2);
     ALTER TABLE catalog_sales ALTER cs_sales_price TYPE numeric(10,2), ALTER cs_ext_sales_price TYPE numeric(10,2);
     ALTER TABLE web_returns ALTER wr_return_amt TYPE numeric(10,2);
     ALTER TABLE catalog_returns ALTER cr_return_amount TYPE numeric(10,2);
     ALTER TABLE item ALTER i_current_price TYPE numeric(10,2);
     UPDATE web_sales SET $(czk ws_sales_price), $(czk ws_ext_sales_price);
     UPDATE catalog_sales SET $(czk cs_sales_price), $(czk cs_ext_sales_price);
     UPDATE web_returns SET $(czk wr_return_amt);
     UPDATE catalog_returns SET $(czk cr_return_amount);
     UPDATE item SET $(czk i_current_price);
     CREATE TABLE _localize_meta (step text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now(), detail text);
     INSERT INTO _localize_meta (step, detail) VALUES ('czk_fx', 'test-fx.sh');" >/dev/null
fi
run_automation "$S"; rc=$?
expect "the build exits 0" "$rc" -eq 0
expect "the runner took it for the CZ world" "$(grep -c '(cz; single transaction)' "$(log_of build "$S")")" -eq 1
k=$(conf threshold_scale_cz)
expect "the scale is 25" "$k" -eq 25
for p in confirmation_threshold care_threshold small_value; do
  want=$(q "SELECT ($(param $p) * $k)::numeric")
  expect "$p in the plan notes = $(param $p) × $k" "$(q "SELECT count(*) FROM _automation_plan WHERE note LIKE '%$p $want%'")" -gt 0
  expect "no plan note quotes the US $p" "$(q "SELECT count(*) FROM _automation_plan WHERE note ~ '$p $(param $p)([^0-9]|$)'")" -eq 0
done
expect "the release_confirmed orders are above 1 250 000" "$(q "SELECT count(*) FROM _automation_plan p JOIN sales_order o ON o.so_order_number = CASE WHEN p.key ~ '^[0-9]+$' THEN p.key::int END
    WHERE p.kind = 'release:confirm' AND o.so_value > $(param confirmation_threshold) * $k")" -eq 2

drop_scratch "$S"
finish
