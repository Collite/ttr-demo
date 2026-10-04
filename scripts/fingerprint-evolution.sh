#!/usr/bin/env bash
# IA-P4·S4.2·T5 — `just fingerprint-evolution`: the `investment-evolution:v2` workbook a client receives, held
# against the book (IA-C51).
#
# ## What it proves that nothing else does
#
# kantheon's suites prove the renderer assembles the period evolution right on a hand-worked fixture. This opens the
# workbook a person downloads — rendered through studio-bff exactly as the Studio's Evolution tab downloads it — and
# compares its Periods and its Summary, cell by cell, with the same evolution computed ON THE BOOK by
# `scripts/sql/evolution-reference.sql`: plain PostgreSQL, a recursive CTE for the average cost, no door, no shared
# code. Agreement means the door's answers, the assembly, the conversion, POI and the template all held.
#
# ## Limits, said rather than hidden
#
#   * AVERAGE cost only — the reference does not implement FIFO; a FIFO estate's workbook is refused, not compared.
#   * A window with an amount no rate converts is refused: the renderer leaves such sums empty (never a guessed rate),
#     and two empties agreeing proves nothing. Pick a window the rates cover.
#   * The reference refuses what the renderer refuses (a ledger holding units the provider does not — `incomplete_ledger`).
#
# Env:
#   IE_FP_BFF         base URL of studio-bff (e.g. http://studio-bff.kantheon.svc.cluster.local:7330)
#   IE_FP_DSN         psql DSN for the `entry` database (the book)
#   IE_FP_PORTFOLIO   the portfolio
#   IE_FP_AS_OF       the window's last day (default: today, UTC)
#   IE_FP_FROM        the window's first month (default: the first day of the month 11 months before IE_FP_AS_OF)
#   IE_FP_GRAIN       month | quarter (default month)
#   IE_FP_SQL         the reference (default scripts/sql/evolution-reference.sql)
#   IE_FP_TOLERANCE   money tolerance per cell (default 0.01, IA-C51)
#   IE_FP_RETURN_TOLERANCE  the plain return's, in percentage points (default 0.0001, IA-C51)
#   the bearer: IE_FP_BEARER, or IE_FP_OIDC_TOKEN_URL + _CLIENT_ID + _CLIENT_SECRET (lib/estate-token.sh)
#
# Flags:
#   --save   print the workbook's rows as a fingerprint block, and write them to IE_FP_SAVE_DIR if set — ⛔ never
#            inside this repository: it is public, and a fingerprint is a real portfolio's balances (S3.3·D8).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/estate-token.sh
. "$HERE/lib/estate-token.sh"

fail() { printf '\n\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
step() { printf '\n\033[1m── %s\033[0m\n' "$*"; }

SAVE=""
while [ $# -gt 0 ]; do
    case "$1" in
        --save) SAVE=1; shift ;;
        *) fail "unknown argument '$1' (--save)" ;;
    esac
done

BFF="${IE_FP_BFF:?IE_FP_BFF is required (studio-bff base URL)}"
DSN="${IE_FP_DSN:?IE_FP_DSN is required (psql DSN for the entry database)}"
PORTFOLIO="${IE_FP_PORTFOLIO:?IE_FP_PORTFOLIO is required — name the portfolio explicitly}"
AS_OF="${IE_FP_AS_OF:-$(date -u +%F)}"
GRAIN="${IE_FP_GRAIN:-month}"
SQL="${IE_FP_SQL:-$HERE/sql/evolution-reference.sql}"
TOLERANCE="${IE_FP_TOLERANCE:-0.01}"
RETURN_TOLERANCE="${IE_FP_RETURN_TOLERANCE:-0.0001}"
ENGINE="$HERE/lib/evolution_fingerprint.py"
TEMPLATE="investment-evolution:v2"

for tool in curl jq psql python3; do command -v "$tool" >/dev/null || fail "$tool is not on PATH"; done
[ -f "$SQL" ] || fail "no reference at $SQL"
[[ "$AS_OF" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || fail "IE_FP_AS_OF must be YYYY-MM-DD, not '$AS_OF'"
case "$GRAIN" in month|quarter) ;; *) fail "IE_FP_GRAIN must be month or quarter, not '$GRAIN'" ;; esac
FROM="${IE_FP_FROM:-$(python3 -c '
import sys
from datetime import date
d = date.fromisoformat(sys.argv[1])
m = d.year * 12 + d.month - 1 - 11
print(date(m // 12, m % 12 + 1, 1).isoformat())' "$AS_OF")}"
[[ "$FROM" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || fail "IE_FP_FROM must be YYYY-MM-DD, not '$FROM'"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

BEARER="$(estate_token IE_FP)" || fail "no bearer for studio-bff"

# ── 1. render it, the way the Evolution tab's download does ──────────────────────────────────────────────────────────

step "1. render $TEMPLATE through studio-bff ($PORTFOLIO, $FROM … $AS_OF, by $GRAIN)"

ARGS="$(jq -nc --arg p "$PORTFOLIO" --arg g "$GRAIN" --arg f "$FROM" --arg a "$AS_OF" \
    '{scope: "portfolio", id: $p, grain: $g, from: $f, as_of: $a}')"
# the bearer through a pipe, never on the command line (a process list shows argv)
http="$(printf 'authorization: Bearer %s\n' "$BEARER" | curl -sS -o "$WORK/render.json" -w '%{http_code}' -X POST "$BFF/api/reports/render" \
    -H @- -H 'content-type: application/json' \
    --data "$(jq -nc --arg t "$TEMPLATE" --argjson args "$ARGS" '{templateId: $t, args: $args}')" || true)"
if [ "$http" != "200" ]; then
    # the renderer's own code and sentence survive the hop — `evolution_unbalanced` names the period
    fail "render failed: HTTP $http $(jq -r '.code // "?"' "$WORK/render.json" 2>/dev/null) — $(jq -r '.message // ""' "$WORK/render.json" 2>/dev/null)"
fi
ARTIFACT="$(jq -r '.artifactId // empty' "$WORK/render.json")"
[ -n "$ARTIFACT" ] || fail "the render answered no artifactId: $(head -c 400 "$WORK/render.json")"
http="$(printf 'authorization: Bearer %s\n' "$BEARER" | curl -sS -o "$WORK/report.xlsx" -w '%{http_code}' \
    "$BFF/api/reports/artifacts/$ARTIFACT?asOf=$AS_OF" -H @- || true)"
[ "$http" = "200" ] || fail "downloading the artifact failed: HTTP $http"
head -c 2 "$WORK/report.xlsx" | grep -q 'PK' || fail "the artifact is not a zip — $(head -c 200 "$WORK/report.xlsx")"
ok "downloaded $(wc -c <"$WORK/report.xlsx" | tr -d ' ') bytes"

python3 "$ENGINE" sheet "$WORK/report.xlsx" "$PORTFOLIO" >"$WORK/workbook.json" || fail "could not read the workbook"
ok "the Periods hold $(jq '.rows | length' "$WORK/workbook.json") periods of $PORTFOLIO, costed $(jq -r '.facts["Cost basis"] // "?"' "$WORK/workbook.json"), in $(jq -r '.facts.Currency // "?"' "$WORK/workbook.json")"

# ── 2. the same evolution, computed on the book ──────────────────────────────────────────────────────────────────────

step "2. the reference, on the book"

# psql quotes `:'name'` itself — the values reach the SQL as literals, never as text spliced in
psql "$DSN" -X -q --csv -v ON_ERROR_STOP=1 \
    -v portfolio="$PORTFOLIO" -v from="$FROM" -v as_of="$AS_OF" -v grain="$GRAIN" \
    -f "$SQL" >"$WORK/reference.csv" || fail "the reference did not run on the book"
python3 "$ENGINE" reference "$WORK/reference.csv" >"$WORK/reference.json" || fail "the reference answered a shape this cannot read"
refused="$(jq -r '.refused' "$WORK/reference.json")"
[ -z "$refused" ] || fail "the book cannot be compared: $refused"
ok "the book answers $(jq '.rows | length' "$WORK/reference.json") periods"

# ── 3. do they agree? ────────────────────────────────────────────────────────────────────────────────────────────────

step "3. the workbook against the book"

python3 "$ENGINE" compare "$WORK/workbook.json" "$WORK/reference.json" \
    --tolerance "$TOLERANCE" --return-tolerance "$RETURN_TOLERANCE" \
    || fail "the evolution a client receives does not match the book"

inside_this_repo() {
    local target repo
    target="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$1")"
    repo="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$HERE/..")"
    case "$target/" in "$repo"/*) return 0 ;; esac
    return 1
}

if [ -n "$SAVE" ]; then
    slug="$(printf '%s' "$TEMPLATE" | tr ':' '-')-$(printf '%s' "$PORTFOLIO" | tr ':' '-')-$GRAIN-$AS_OF.json"
    # ⛔ S3.3·D8: a fingerprint is a real portfolio's balances and this repository is PUBLIC — printed always (the
    # in-cluster run lifts it out of the log), written only where IE_FP_SAVE_DIR points, and never in here.
    if [ -n "${IE_FP_SAVE_DIR:-}" ]; then
        dest="$IE_FP_SAVE_DIR/$slug"
        if inside_this_repo "$dest"; then
            fail "IE_FP_SAVE_DIR ($IE_FP_SAVE_DIR) is inside this repository, which is PUBLIC — a fingerprint holds a real portfolio's balances (S3.3·D8)"
        fi
        mkdir -p "$(dirname "$dest")"
        cp "$WORK/workbook.json" "$dest"
        ok "fingerprint saved: $dest"
    fi
    printf -- '-----BEGIN FINGERPRINT %s-----\n' "$slug"
    jq -c '{rows, summary}' "$WORK/workbook.json"
    printf -- '-----END FINGERPRINT-----\n'
fi

printf '\n\033[32mthe evolution matches the book — %s, %s … %s by %s\033[0m\n' "$PORTFOLIO" "$FROM" "$AS_OF" "$GRAIN"
