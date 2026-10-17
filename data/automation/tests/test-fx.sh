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
if [ "$(q "SELECT to_regclass('public._localize_meta') IS NULL")" = t ]; then
  q "CREATE TABLE _localize_meta (step text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now(), detail text);
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
expect "the release_confirmed orders are above 1 250 000" "$(q "SELECT count(*) FROM _automation_plan p JOIN sales_order o ON o.so_order_number = p.key::int
    WHERE p.kind = 'release:confirm' AND o.so_value > $(param confirmation_threshold) * $k")" -eq 2

drop_scratch "$S"
finish
