#!/usr/bin/env bash
# IA-P4·S4.3·T6 — `just fingerprint-overview <template>`: one of the five overview workbooks a client receives, held
# against the book (IA-C51).
#
#   portfolio-statement:v1    Transactions and Cash against `sql/statement-reference.sql`, and its Evolution sheet (it
#                             IS investment-evolution:v2's Periods) against `sql/evolution-reference.sql`
#   client-overview:v1        each portfolio's market value, cash, value now and at the last quarter end, and the
#                             change, against `sql/overview-reference.sql` for the client
#   distributor-overview:v1   the same for every open portfolio of the book, and the Book's counts
#   price-sheet:v1            every instrument × month-end price against `sql/price-sheet-reference.sql`
#   sync-run-changes:v1       the movements and prices a COMMITTED run changed against `sql/sync-run-changes-reference.sql`
#                             — on the substrate's journal, which the book's read-only role does not see
#
# ## What it proves that nothing else does
#
# kantheon's suites prove the renderer lays each workbook out from its model, cell by cell. This opens the workbook a
# person downloads — rendered through studio-bff as the Studio's buttons render it — and compares its tables with the
# same figures computed ON THE BOOK in plain PostgreSQL, written from the contracts' rules and sharing no code with the
# renderer or with the door's programs. Agreement means the programs, the assembly, the conversion and the template all
# held.
#
# ## Limits, said rather than hidden
#
#   * The statement's Evolution is held as v2's is (average cost only; a window with an amount no rate converts is not
#     fingerprinted — `fingerprint-evolution.sh`'s rules).
#   * The run's change log: a committed run only (a held batch's changes are a preview the journal never records),
#     committed WITH ROWS (a batch committed with counts only is counted but never listed — refused), that changed
#     something (0 = 0 holds nothing — refused); and its movements and prices (the Structure sheet attributes rows to
#     portfolios; the journal does not). A correction counts as a changed movement, as the journal counts it.
#
# Env:
#   IE_FP_TEMPLATE    the template (or the first argument)
#   IE_FP_BFF         base URL of studio-bff (e.g. http://studio-bff.kantheon.svc.cluster.local:7330)
#   IE_FP_DSN         psql DSN for the `entry` database (the book)
#   IE_FP_JOURNAL_DSN sync-run-changes only: a DSN whose role may read `journal_batch` and `entry_record`
#                     (default IE_FP_DSN — the drill's read-only role cannot, and the run is refused, naming why)
#   IE_FP_JOURNAL_PSQL sync-run-changes only, instead of IE_FP_JOURNAL_DSN: a psql command PREFIX that reaches the
#                     journal (the reference goes to its stdin), e.g. on hartland, from a laptop:
#                       'kubectl --context hartland -n data exec -i postgres-1 -c postgres -- psql -U postgres -d entry'
#                     The session is made read-only first (`SET default_transaction_read_only = on`), whatever the role.
#   IE_FP_AS_OF       the day (default: today, UTC)
#   IE_FP_PORTFOLIO   portfolio-statement: the portfolio
#   IE_FP_FROM        portfolio-statement: the window's first month (default: the as_of's month and the 11 before)
#   IE_FP_LABELS      portfolio-statement: the classification table its Evolution's reference classifies fees and
#                     income with (IA-C55, IA-P4b·S4b.2; default model/investment/income-labels.yaml, synced with the model)
#   IE_FP_CLIENT      client-overview: the client
#   IE_FP_MONTHS      price-sheet: month-ends back (default 24)
#   IE_FP_RUN         sync-run-changes: the run
#   IE_FP_TOLERANCE   money tolerance per cell (default 0.01, IA-C51)
#   the bearer: IE_FP_BEARER, or IE_FP_OIDC_TOKEN_URL + _CLIENT_ID + _CLIENT_SECRET (lib/estate-token.sh)
#
# Options (after the template):
#   --save   print the book's answer the workbook was held to (the reference CSV — on a pass, the workbook's figures)
#            as a fingerprint block, which `drill-in-cluster` lifts into the PRIVATE project repo, and write it to
#            IE_FP_SAVE_DIR if set — ⛔ never inside this repository: it is public, and the figures are real (S3.3·D8).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/estate-token.sh
. "$HERE/lib/estate-token.sh"

fail() { printf '\n\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
step() { printf '\n\033[1m── %s\033[0m\n' "$*"; }

TEMPLATE="${IE_FP_TEMPLATE:-}"
SAVE=""
while [ $# -gt 0 ]; do
    case "$1" in
        --save) SAVE=1; shift ;;
        -*) fail "unknown option '$1' (--save)" ;;
        *) TEMPLATE="$1"; shift ;;
    esac
done
BFF="${IE_FP_BFF:?IE_FP_BFF is required (studio-bff base URL)}"
DSN="${IE_FP_DSN:?IE_FP_DSN is required (psql DSN for the entry database)}"
AS_OF="${IE_FP_AS_OF:-$(date -u +%F)}"
TOLERANCE="${IE_FP_TOLERANCE:-0.01}"
ENGINE="$HERE/lib/overview_fingerprint.py"
SQLDIR="$HERE/sql"

for tool in curl jq psql python3; do command -v "$tool" >/dev/null || fail "$tool is not on PATH"; done
[[ "$AS_OF" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || fail "IE_FP_AS_OF must be YYYY-MM-DD, not '$AS_OF'"

# what each template is rendered with, and the reference it is held to (psql `-v` pairs, quoted by psql itself)
case "$TEMPLATE" in
    portfolio-statement:v1)
        PORTFOLIO="${IE_FP_PORTFOLIO:?IE_FP_PORTFOLIO is required — name the portfolio explicitly}"
        FROM="${IE_FP_FROM:-$(python3 -c '
import sys
from datetime import date
d = date.fromisoformat(sys.argv[1])
m = d.year * 12 + d.month - 1 - 11
print(date(m // 12, m % 12 + 1, 1).isoformat())' "$AS_OF")}"
        ARGS="$(jq -nc --arg p "$PORTFOLIO" --arg f "$FROM" --arg a "$AS_OF" '{portfolio_id: $p, from: $f, as_of: $a}')"
        SQL="statement-reference.sql"; VARS=(-v "portfolio=$PORTFOLIO" -v "from=$FROM" -v "as_of=$AS_OF"); REF_DSN="$DSN"
        ;;
    client-overview:v1)
        CLIENT="${IE_FP_CLIENT:?IE_FP_CLIENT is required — name the client explicitly}"
        ARGS="$(jq -nc --arg c "$CLIENT" --arg a "$AS_OF" '{client_id: $c, as_of: $a}')"
        SQL="overview-reference.sql"; VARS=(-v "client=$CLIENT" -v "as_of=$AS_OF"); REF_DSN="$DSN"
        ;;
    distributor-overview:v1)
        ARGS="$(jq -nc --arg a "$AS_OF" '{as_of: $a}')"
        SQL="overview-reference.sql"; VARS=(-v "client=" -v "as_of=$AS_OF"); REF_DSN="$DSN"
        ;;
    price-sheet:v1)
        MONTHS="${IE_FP_MONTHS:-24}"
        [[ "$MONTHS" =~ ^[0-9]+$ ]] && [ "$MONTHS" -ge 1 ] && [ "$MONTHS" -le 24 ] || fail "IE_FP_MONTHS must be 1..24, not '$MONTHS'"
        ARGS="$(jq -nc --arg m "$MONTHS" --arg a "$AS_OF" '{months: $m, as_of: $a}')"
        SQL="price-sheet-reference.sql"; VARS=(-v "as_of=$AS_OF" -v "months=$MONTHS"); REF_DSN="$DSN"
        ;;
    sync-run-changes:v1)
        RUN="${IE_FP_RUN:?IE_FP_RUN is required — name the (committed) run explicitly}"
        ARGS="$(jq -nc --arg r "$RUN" '{run_id: $r}')"
        SQL="sync-run-changes-reference.sql"; VARS=(-v "run=$RUN"); REF_DSN="${IE_FP_JOURNAL_DSN:-$DSN}"
        ;;
    *) fail "the template is one of portfolio-statement:v1 client-overview:v1 distributor-overview:v1 price-sheet:v1 sync-run-changes:v1, not '$TEMPLATE'" ;;
esac
[ -f "$SQLDIR/$SQL" ] || fail "no reference at $SQLDIR/$SQL"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

BEARER="$(estate_token IE_FP)" || fail "no bearer for studio-bff"

# ── 1. render it, the way the Studio's download buttons do ───────────────────────────────────────────────────────────

step "1. render $TEMPLATE through studio-bff ($ARGS)"
# the bearer through a pipe, never on the command line (a process list shows argv)
http="$(printf 'authorization: Bearer %s\n' "$BEARER" | curl -sS -o "$WORK/render.json" -w '%{http_code}' -X POST "$BFF/api/reports/render" \
    -H @- -H 'content-type: application/json' \
    --data "$(jq -nc --arg t "$TEMPLATE" --argjson args "$ARGS" '{templateId: $t, args: $args}')" || true)"
if [ "$http" != "200" ]; then
    fail "render failed: HTTP $http $(jq -r '.code // "?"' "$WORK/render.json" 2>/dev/null) — $(jq -r '.message // ""' "$WORK/render.json" 2>/dev/null)"
fi
ARTIFACT="$(jq -r '.artifactId // empty' "$WORK/render.json")"
[ -n "$ARTIFACT" ] || fail "the render answered no artifactId: $(head -c 400 "$WORK/render.json")"
http="$(printf 'authorization: Bearer %s\n' "$BEARER" | curl -sS -o "$WORK/report.xlsx" -w '%{http_code}' \
    "$BFF/api/reports/artifacts/$ARTIFACT?asOf=$AS_OF" -H @- || true)"
[ "$http" = "200" ] || fail "downloading the artifact failed: HTTP $http"
head -c 2 "$WORK/report.xlsx" | grep -q 'PK' || fail "the artifact is not a zip — $(head -c 200 "$WORK/report.xlsx")"
ok "downloaded $(wc -c <"$WORK/report.xlsx" | tr -d ' ') bytes ($(jq -r '.fileName // "unnamed"' "$WORK/render.json"))"

# ── 2. the same figures, on the book ─────────────────────────────────────────────────────────────────────────────────

step "2. the reference on the book ($SQL)"
reference() {
    if [ "$TEMPLATE" = "sync-run-changes:v1" ] && [ -n "${IE_FP_JOURNAL_PSQL:-}" ]; then
        # a command PREFIX, word-split on purpose (as studio-dod-browse's PSQL); the reference on its stdin, after a
        # line that makes the session read-only — the role this reaches may be able to write
        # shellcheck disable=SC2086
        { printf 'SET default_transaction_read_only = on;\n'; cat "$SQLDIR/$SQL"; } \
            | $IE_FP_JOURNAL_PSQL -X -q --csv -v ON_ERROR_STOP=1 "${VARS[@]}" -f -
    else
        psql "$REF_DSN" -X -q --csv -v ON_ERROR_STOP=1 "${VARS[@]}" -f "$SQLDIR/$SQL"
    fi
}
if ! reference >"$WORK/reference.csv" 2>"$WORK/psql.err"; then
    if grep -q 'permission denied' "$WORK/psql.err"; then
        fail "the reference may not read what it needs ($(head -1 "$WORK/psql.err")) — sync-run-changes reads the substrate's journal: set IE_FP_JOURNAL_DSN to a role that may, or IE_FP_JOURNAL_PSQL to a psql that reaches it"
    fi
    fail "the reference did not run on the book: $(head -3 "$WORK/psql.err")"
fi
ok "the book answers $(($(wc -l <"$WORK/reference.csv") - 1)) rows"

# ── 3. do they agree? ────────────────────────────────────────────────────────────────────────────────────────────────

step "3. the workbook against the book"
set +e
python3 "$ENGINE" compare "$TEMPLATE" "$WORK/report.xlsx" "$WORK/reference.csv" --tolerance "$TOLERANCE" \
    ${MONTHS:+--months "$MONTHS"}
rc=$?
set -e
# 2: not compared at all — a refusal, whose reason the engine printed above
[ "$rc" -ne 2 ] || fail "the $TEMPLATE was not compared with the book — the reason is above"
[ "$rc" -eq 0 ] || fail "the $TEMPLATE a client receives does not match the book"

if [ "$TEMPLATE" = "portfolio-statement:v1" ]; then
    # its Evolution sheet IS v2's Periods — held to v2's reference, by month, over the same window
    step "4. the statement's Evolution against the evolution reference"
    labels_yaml="${IE_FP_LABELS:-$HERE/../model/investment/income-labels.yaml}"
    [ -f "$labels_yaml" ] || fail "no classification table at $labels_yaml (IE_FP_LABELS) — the evolution reference classifies fees and income with it"
    labels="$(python3 "$HERE/lib/income_labels.py" sql "$labels_yaml")" || fail "the classification table at $labels_yaml cannot be read"
    psql "$DSN" -X -q --csv -v ON_ERROR_STOP=1 -v "portfolio=$PORTFOLIO" -v "from=$FROM" -v "as_of=$AS_OF" -v grain=month \
        -v "labels=$labels" -f "$SQLDIR/evolution-reference.sql" >"$WORK/evolution.csv" || fail "the evolution reference did not run on the book"
    python3 "$HERE/lib/evolution_fingerprint.py" sheet "$WORK/report.xlsx" "$PORTFOLIO" --sheet Evolution >"$WORK/evolution-wb.json" \
        || fail "could not read the statement's Evolution sheet"
    python3 "$HERE/lib/evolution_fingerprint.py" reference "$WORK/evolution.csv" >"$WORK/evolution-ref.json" \
        || fail "the evolution reference answered a shape this cannot read"
    refused="$(jq -r '.refused' "$WORK/evolution-ref.json")"
    [ -z "$refused" ] || fail "the book cannot be compared: $refused"
    python3 "$HERE/lib/evolution_fingerprint.py" compare "$WORK/evolution-wb.json" "$WORK/evolution-ref.json" --tolerance "$TOLERANCE" \
        || fail "the statement's Evolution does not match the book"
fi

if [ -n "$SAVE" ]; then
    case "$TEMPLATE" in
        portfolio-statement:v1) subject="-$(printf '%s' "$PORTFOLIO" | tr ':' '-')" ;;
        client-overview:v1)     subject="-$(printf '%s' "$CLIENT" | tr ':' '-')" ;;
        price-sheet:v1)         subject="-$MONTHS" ;;
        sync-run-changes:v1)    subject="-$(printf '%s' "$RUN" | tr -c 'A-Za-z0-9._\n-' '-')" ;;
        *)                      subject="" ;;
    esac
    slug="$(printf '%s' "$TEMPLATE" | tr ':' '-')$subject-$AS_OF.csv"
    # ⛔ S3.3·D8: printed always (the in-cluster run lifts it out of the log), written only where IE_FP_SAVE_DIR
    # points, and never in here
    if [ -n "${IE_FP_SAVE_DIR:-}" ]; then
        dest="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$IE_FP_SAVE_DIR")/$slug"
        repo="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$HERE/..")"
        case "$dest" in
            "$repo"/*) fail "IE_FP_SAVE_DIR ($IE_FP_SAVE_DIR) is inside this repository, which is PUBLIC — a fingerprint holds the book's figures (S3.3·D8)" ;;
        esac
        mkdir -p "$(dirname "$dest")"
        cp "$WORK/reference.csv" "$dest"
        ok "fingerprint saved: $dest"
    fi
    printf -- '-----BEGIN FINGERPRINT %s-----\n' "$slug"
    cat "$WORK/reference.csv"
    printf -- '-----END FINGERPRINT-----\n'
fi

printf '\n\033[32mthe %s matches the book — as of %s\033[0m\n' "$TEMPLATE" "$AS_OF"
