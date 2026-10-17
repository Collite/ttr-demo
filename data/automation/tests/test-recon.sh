#!/usr/bin/env bash
# AU-hartland P1·S1.3 T1 (added) — R-A against its baseline: no baseline exits 2, a written one matches itself
# (exit 0), and a changed row in the world shows as drift (exit 3, the diff printed) — `check-model`'s contract.
# Works on a throwaway copy of <db>, with the baseline in a temp directory:   test-recon.sh <ctx> <db> [pod]
set -uo pipefail
CTX="${1:?usage: test-recon.sh <ctx> <db> [pod]}"; SRC="${2:?db}"; POD="${3:-hartland-pg-1}"; NS="${EXTEND_NS:-data}"
source "$(dirname "$0")/lib-test.sh"
S="${SRC}_au_recon"
B="$(mktemp -d "${TMPDIR:-/tmp}/au-recon.XXXXXX")"

echo "== R-A, on a scratch copy of $SRC ($S)"
scratch_copy "$SRC" "$S"
run_automation "$S"; expect "the build exits 0" "$?" -eq 0
expect "the build printed R-A" "$(grep -c '^# R-A — the automation extension of' "$(log_of build "$S")")" -eq 1

# run-recon.sh keeps its baseline beside it (recon/R-A-<world>.md): point it at a temp copy of the directory
mkdir -p "$B/automation"; cp -R "$AUTO_DIR/." "$B/automation/"; rm -rf "$B/automation/recon"
ln -s "$AUTO_DIR/../extend" "$B/extend"
R="$B/automation/run-recon.sh"
"$R" "$CTX" "$S" us "$POD" > /dev/null 2>&1; expect "no baseline: exit 2" "$?" -eq 2
AUTOMATION_RECON_WRITE=1 "$R" "$CTX" "$S" us "$POD" > /dev/null 2>&1; expect "AUTOMATION_RECON_WRITE=1 writes it" "$?" -eq 0
expect "the baseline pins the plants and the tables" "$(grep -cE '^\| (release:short|decide:late|sales_line|_automation_events) \|' "$B/automation/recon/R-A-us.md")" -eq 4
"$R" "$CTX" "$S" us "$POD" > /dev/null 2>&1; expect "the same world matches its baseline: exit 0" "$?" -eq 0
pgq "$S" "UPDATE sales_line SET sl_quantity = sl_quantity + 1 WHERE (sl_order_number, sl_line_no) = (SELECT sl_order_number, sl_line_no FROM sales_line ORDER BY 1, 2 LIMIT 1)" > /dev/null
"$R" "$CTX" "$S" us "$POD" > "$(log_of recon "$S")" 2>&1; expect "one changed line drifts: exit 3" "$?" -eq 3
expect "the diff names the table" "$(grep -c '^[-+]| sales_line |' "$(log_of recon "$S")")" -eq 2

rm -rf "$B"
drop_scratch "$S"
finish
