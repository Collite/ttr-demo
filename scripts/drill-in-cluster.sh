#!/usr/bin/env bash
# IE-P3·S3.3 — run a drill FROM INSIDE the cluster, because from outside it does not finish.
#
# ## Why this exists
#
# Both drills need two things at once: studio-bff (HTTP) and the `entry` book (psql). From a laptop
# that means two port-forwards, and on this estate a forward drops mid-run — which is exactly how
# S3.0·T7 failed twice before it was run this way. Inside the cluster both are ordinary service calls.
#
# It also removes the other reason a drill could not be run unattended: the bearer. The Job mints its
# own token from the `estate-drill` service account (olymp: realm client + `estate-drill-oidc`), so
# nothing has to be copied out of a browser within five minutes of using it.
#
# ⚑ Namespace `ttr-server` — that is where BOTH secrets are materialised: `pg-entry-ro-cred` (the
# book's read credential, by design: "ttr-server ONLY") and `estate-drill-oidc`. A Job needs both.
#
# Use:
#   just drill-in-cluster dod                 # the read drill (IE_DOD_MODE=readonly)
#   just drill-in-cluster fingerprint         # render the report and hold it against the book
#   just drill-in-cluster fingerprint investment-evolution:v2   # the period evolution against the book (IA-P4·S4.2)
#   just drill-in-cluster fingerprint portfolio-statement:v1    # …and the five overviews (IA-P4·S4.3):
#   just drill-in-cluster fingerprint client-overview:v1        #    client-overview:v1 · distributor-overview:v1 ·
#                                                               #    price-sheet:v1 · sync-run-changes:v1
#
# Env (all optional except where the drill itself requires one):
#   IE_CTX          kube context           (default: hartland)
#   IE_NS           namespace              (default: ttr-server)
#   IE_PORTFOLIO    the portfolio          (default: conseq:200791223 — the 838-movement book)
#   IE_AS_OF        the fingerprint's as-of date (default: today; v1 refuses a quarter end, S3.1·D2)
#   IE_FROM         v2's first month (default: 11 months before IE_AS_OF)
#   IE_GRAIN        v2's grain, month | quarter (default: month)
#   IE_CLIENT       client-overview's client (no default — name it)
#   IE_MONTHS       price-sheet's month-ends back (default: 24)
#   IE_RUN          sync-run-changes' run (no default — a COMMITTED run). ⚑ Its reference reads the substrate's
#                   journal, which the drill's read-only role does not see, and no journal-reading credential is
#                   materialised in this namespace — in the Job the run is refused, naming why. Run that one from a
#                   laptop instead (IA-P4·S4.4): `fingerprint-overview.sh sync-run-changes:v1` with IE_FP_BFF = the
#                   Studio's origin, a person's bearer, and IE_FP_JOURNAL_PSQL = a `kubectl exec … psql` prefix (the
#                   session is made read-only first) — the script's header has the line.
#   IE_TOP_N        the estate's row cap   (default: 200)
#   IE_IMAGE        the runner image       (default: postgres:16-alpine — psql, plus apk for the rest)
#   IE_KEEP         1 to leave the Job and its ConfigMap behind for inspection
#   IE_FINGERPRINTS_DIR  where a `--save`d fingerprint is written (default: the private project repo beside
#                   this checkout). ⛔ Never inside this repository — it is public (S3.3·D8).
#
# ⛔ Read drills only. `IE_DOD_MODE=full` writes three permanent rows to an append-only ledger, and the
# drill client is deliberately audienced at `studio` alone — it cannot write through entry-substrate
# even if someone asked it to. A write drill stays a person's decision, with a person's bearer.

set -euo pipefail

DRILL="${1:?usage: drill-in-cluster.sh <dod|fingerprint> [args…]}"
shift
CTX="${IE_CTX:-hartland}"
NS="${IE_NS:-ttr-server}"
PORTFOLIO="${IE_PORTFOLIO:-conseq:200791223}"
AS_OF="${IE_AS_OF:-$(date -u +%F)}"
TOP_N="${IE_TOP_N:-200}"
IMAGE="${IE_IMAGE:-postgres:16-alpine}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

fail() { printf '\n\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# The arguments travel a long way: into a `sh -c` string, inside a JSON array, inside YAML piped to
# `kubectl apply`. `$*` lost them at the first hop — `--expect "/p with space/e.json"` arrived as two
# arguments — and a `"` in one produced a malformed JSON array, so the Job died on a parse error
# instead of naming the bad argument. So: refuse what cannot survive the hop, by name, and quote the
# rest with `printf %q` (spaces, tabs and shell metacharacters included).
PASSTHROUGH=""
for arg in "$@"; do
    case "$arg" in
        *'"'*|*'`'*|*'$'*|*'\'*|*$'\n'*)
            fail "the argument '$arg' carries a double quote, backtick, \$, backslash or newline — none of those survives the trip into the Job's command; drop it, or set the drill's IE_* variable instead"
            ;;
    esac
    PASSTHROUGH="$PASSTHROUGH $(printf '%q' "$arg")"
done

# `fingerprint` names its template first when it is not v1's: `fingerprint investment-evolution:v2 [--save]`
FINGERPRINT="report-fingerprint.sh"
case "${1:-}" in
    investment-evolution:v2)
        FINGERPRINT="fingerprint-evolution.sh"
        PASSTHROUGH="${PASSTHROUGH# investment-evolution:v2}"
        ;;
    investment-evolution:v1)
        PASSTHROUGH="${PASSTHROUGH# investment-evolution:v1}"
        ;;
    # IA-P4·S4.3: the template stays the script's first argument
    portfolio-statement:v1 | client-overview:v1 | distributor-overview:v1 | price-sheet:v1 | sync-run-changes:v1)
        FINGERPRINT="fingerprint-overview.sh"
        ;;
esac
case "$DRILL" in
    dod)         COMMAND="bash /drill/investment-dod.sh$PASSTHROUGH" ;;
    fingerprint) COMMAND="bash /drill/$FINGERPRINT$PASSTHROUGH" ;;
    *) fail "the drill is 'dod' or 'fingerprint', not '$DRILL'" ;;
esac

JOB="estate-drill-$DRILL"
kubectl --context "$CTX" -n "$NS" delete job "$JOB" --ignore-not-found >/dev/null

# The scripts themselves, from THIS checkout — so a drill runs the code in front of you rather than
# whatever was baked into an image.
kubectl --context "$CTX" -n "$NS" create configmap estate-drill-scripts \
    --from-file="$HERE/investment-dod.sh" \
    --from-file="$HERE/report-fingerprint.sh" \
    --from-file="$HERE/fingerprint-evolution.sh" \
    --from-file="$HERE/fingerprint-overview.sh" \
    --from-file=estate-token.sh="$HERE/lib/estate-token.sh" \
    --from-file=fingerprint.py="$HERE/lib/fingerprint.py" \
    --from-file=evolution_fingerprint.py="$HERE/lib/evolution_fingerprint.py" \
    --from-file=overview_fingerprint.py="$HERE/lib/overview_fingerprint.py" \
    --from-file=income_labels.py="$HERE/lib/income_labels.py" \
    --from-file=evolution-reference.sql="$HERE/sql/evolution-reference.sql" \
    --from-file=statement-reference.sql="$HERE/sql/statement-reference.sql" \
    --from-file=overview-reference.sql="$HERE/sql/overview-reference.sql" \
    --from-file=price-sheet-reference.sql="$HERE/sql/price-sheet-reference.sql" \
    --from-file=sync-run-changes-reference.sql="$HERE/sql/sync-run-changes-reference.sql" \
    --dry-run=client -o yaml | kubectl --context "$CTX" -n "$NS" apply -f - >/dev/null

# The model file the fingerprint lifts the reference query out of (the SYNCED one, which is what the
# estate serves) — mounted rather than fetched, so the comparison uses this checkout's model too. And the
# classification table synced beside it (IA-P4b·S4b.2): the evolution reference classifies with it.
kubectl --context "$CTX" -n "$NS" create configmap estate-drill-model \
    --from-file="$HERE/../model/investment/queries/q_investment.ttrm" \
    --from-file="$HERE/../model/investment/income-labels.yaml" \
    --dry-run=client -o yaml | kubectl --context "$CTX" -n "$NS" apply -f - >/dev/null

cat <<YAML | kubectl --context "$CTX" apply -f - >/dev/null
apiVersion: batch/v1
kind: Job
metadata: { name: $JOB, namespace: $NS }
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 3600
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: drill
          image: $IMAGE
          command: ["sh", "-c", "apk add -q --no-cache bash curl jq python3 && mkdir -p /drill/lib /drill/sql && cp /scripts/estate-token.sh /scripts/fingerprint.py /scripts/evolution_fingerprint.py /scripts/overview_fingerprint.py /scripts/income_labels.py /drill/lib/ && cp /scripts/*.sql /drill/sql/ && cp /scripts/*.sh /drill/ && $COMMAND"]
          env:
            - { name: IE_DOD_MODE, value: readonly }
            - { name: IE_DOD_PORTFOLIO, value: "$PORTFOLIO" }
            - { name: IE_DOD_TOP_N, value: "$TOP_N" }
            - { name: IE_DOD_BFF, value: "http://studio-bff.kantheon.svc.cluster.local:7330" }
            - { name: IE_DOD_DSN, value: "host=postgres-rw.data.svc.cluster.local port=5432 dbname=entry user=entry_readonly" }
            - { name: IE_DOD_OIDC_TOKEN_URL, value: "https://keycloak.hartland.collite.cz/realms/kantheon/protocol/openid-connect/token" }
            - { name: IE_DOD_OIDC_CLIENT_ID, value: estate-drill }
            - name: IE_DOD_OIDC_CLIENT_SECRET
              valueFrom: { secretKeyRef: { name: estate-drill-oidc, key: ESTATE_DRILL_CLIENT_SECRET } }
            - { name: IE_FP_PORTFOLIO, value: "$PORTFOLIO" }
            - { name: IE_FP_AS_OF, value: "$AS_OF" }
            - { name: IE_FP_FROM, value: "${IE_FROM:-}" }
            - { name: IE_FP_GRAIN, value: "${IE_GRAIN:-month}" }
            - { name: IE_FP_CLIENT, value: "${IE_CLIENT:-}" }
            - { name: IE_FP_MONTHS, value: "${IE_MONTHS:-24}" }
            - { name: IE_FP_RUN, value: "${IE_RUN:-}" }
            - { name: IE_FP_BFF, value: "http://studio-bff.kantheon.svc.cluster.local:7330" }
            - { name: IE_FP_DSN, value: "host=postgres-rw.data.svc.cluster.local port=5432 dbname=entry user=entry_readonly" }
            - { name: IE_FP_MODEL, value: /model/q_investment.ttrm }
            # the classification table the evolution reference classifies fees and income with (IA-P4b·S4b.2) — this
            # checkout's synced copy, like the model file beside it
            - { name: IE_FP_LABELS, value: /model/income-labels.yaml }
            - { name: IE_FP_OIDC_TOKEN_URL, value: "https://keycloak.hartland.collite.cz/realms/kantheon/protocol/openid-connect/token" }
            - { name: IE_FP_OIDC_CLIENT_ID, value: estate-drill }
            - name: IE_FP_OIDC_CLIENT_SECRET
              valueFrom: { secretKeyRef: { name: estate-drill-oidc, key: ESTATE_DRILL_CLIENT_SECRET } }
            # The book's read credential — psql takes the password from the environment, so the DSN
            # above carries no secret and neither does this file.
            - name: PGPASSWORD
              valueFrom: { secretKeyRef: { name: pg-entry-ro-cred, key: password } }
          volumeMounts:
            - { name: scripts, mountPath: /scripts }
            - { name: model, mountPath: /model }
      volumes:
        - { name: scripts, configMap: { name: estate-drill-scripts } }
        - { name: model, configMap: { name: estate-drill-model } }
YAML

printf 'running %s in %s/%s …\n' "$JOB" "$CTX" "$NS"
# Wait for EITHER end by polling the Job's counts: `kubectl wait --for=condition=complete` sat out its whole timeout on
# a Job that had FAILED in seconds — a fingerprint's differences read as ten silent minutes. `/` keeps an empty
# `succeeded` from shifting `failed` into its place.
deadline=$((SECONDS + 600))
while :; do
    IFS=/ read -r ok bad <<<"$(kubectl --context "$CTX" -n "$NS" get job "$JOB" -o jsonpath='{.status.succeeded}/{.status.failed}' 2>/dev/null || true)"
    [ "${ok:-0}" -ge 1 ] 2>/dev/null && break
    [ "${bad:-0}" -ge 1 ] 2>/dev/null && break
    [ "$SECONDS" -ge "$deadline" ] && { printf '%s did not finish in 600 s — its log so far:\n' "$JOB"; break; }
    sleep 2
done
LOG="$(mktemp)"
# The WHOLE log (`--tail=-1`): a fingerprint block is printed whole and lifted from here, and a price sheet's runs
# to instruments × month-ends lines — a tail of a few hundred cut its BEGIN line off and the save found nothing.
kubectl --context "$CTX" -n "$NS" logs "job/$JOB" --tail=-1 >"$LOG" 2>&1 || true
cat "$LOG"

# A fingerprint printed by a run in a pod is the only copy — the Job's filesystem goes with it. Lift it
# out of the log into the PRIVATE project repo.
#
# ⛔ RULED by Bora 2026-09-14 (S3.3·D8): never into THIS repository — it is public, and a fingerprint is a
# real portfolio's quarterly balances. The default is the project repo beside this checkout (the
# collite-gh layout); IE_FINGERPRINTS_DIR overrides it, and a destination inside this repo is refused.
# A refusal is RECORDED rather than fatal here, so the Job and its ConfigMaps are still cleaned up below.
FP_ERROR=""
slug="$(sed -n 's/^-----BEGIN FINGERPRINT \(.*\)-----$/\1/p' "$LOG" | head -1)"
# A run ASKED to save and producing no block is a silent no-save: nothing below would fire, and the
# script would report success having written nothing.
case "$PASSTHROUGH" in
    *--save*) [ -n "$slug" ] || FP_ERROR="the run was asked to --save and printed no fingerprint block — nothing was written; its log is above" ;;
esac
if [ -n "$slug" ]; then
    dir="${IE_FINGERPRINTS_DIR:-$HERE/../../project/kantheon/features/midas/investment-estate/fingerprints}"
    repo="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$HERE/..")"
    real="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$dir")"
    case "$real/" in
        "$repo"/*)
            FP_ERROR="the fingerprint destination $dir is inside this PUBLIC repository (S3.3·D8) — set IE_FINGERPRINTS_DIR to the private project repo; the fingerprint is in the log above"
            ;;
        *)
            if [ -d "$(dirname "$real")" ]; then
                mkdir -p "$real"
                sed -n '/^-----BEGIN FINGERPRINT /,/^-----END FINGERPRINT-----$/p' "$LOG" | sed '1d;$d' >"$real/$slug"
                printf '\nfingerprint written: %s (%s rows) — commit it in the PROJECT repo, by path\n' \
                    "$real/$slug" "$(($(wc -l <"$real/$slug") - 1))"
            else
                FP_ERROR="no private project repo at $(dirname "$real") — set IE_FINGERPRINTS_DIR; the fingerprint is in the log above, nothing was written"
            fi
            ;;
    esac
fi
rm -f "$LOG"

state="$(kubectl --context "$CTX" -n "$NS" get job "$JOB" -o jsonpath='{.status.succeeded}' 2>/dev/null || true)"
if [ -z "${IE_KEEP:-}" ]; then
    kubectl --context "$CTX" -n "$NS" delete job "$JOB" --ignore-not-found >/dev/null
    kubectl --context "$CTX" -n "$NS" delete configmap estate-drill-scripts estate-drill-model --ignore-not-found >/dev/null
fi
[ "$state" = "1" ] || fail "$JOB did not succeed (its log is above)"
[ -z "$FP_ERROR" ] || fail "$FP_ERROR"
printf '\n\033[32m%s succeeded\033[0m\n' "$JOB"
