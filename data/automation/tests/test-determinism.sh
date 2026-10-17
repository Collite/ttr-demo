#!/usr/bin/env bash
# AU-hartland P1·S1.1 T1 — the build is deterministic: two fresh copies of the same world, built at the same
# as_of, hold byte-identical rows in every table the build writes (the extension's, its internals bar the
# timestamps, and the base tables it changes).   test-determinism.sh <ctx> <db> [pod] [as-of]
set -uo pipefail
CTX="${1:?usage: test-determinism.sh <ctx> <db> [pod] [as-of]}"; SRC="${2:?db}"; POD="${3:-hartland-pg-1}"; NS="${EXTEND_NS:-data}"
AS_OF="${4:-}"
source "$(dirname "$0")/lib-test.sh"
A="${SRC}_au_det_a"; B="${SRC}_au_det_b"

echo "== determinism, on two scratch copies of $SRC"
scratch_copy "$SRC" "$A"; scratch_copy "$SRC" "$B"
run_automation "$A" "$AS_OF"; rc1=$?
run_automation "$B" "$AS_OF"; rc2=$?
expect "copy A builds (exit 0)" "$rc1" -eq 0
expect "copy B builds (exit 0)" "$rc2" -eq 0

fa=$(fp_build "$A" 2>/dev/null); fb=$(fp_build "$B" 2>/dev/null)
for t in $AU_TABLES $AU_INTERNALS $BASE_CHANGED; do
  expect "$t: identical rows (md5, rows)" "$(echo "$fb" | awk -v t="$t" '$1 == t {print $2, $3}')" = \
    "$(echo "$fa" | awk -v t="$t" '$1 == t {print $2, $3}')"
done
expect "the build wrote rows" "$(echo "$fa" | awk '$1 == "sales_line" {print $3 + 0}')" -gt 0

drop_scratch "$A"; drop_scratch "$B"
finish
