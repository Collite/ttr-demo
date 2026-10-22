#!/usr/bin/env bash
# The label columns, CHAR(n) → VARCHAR(n), trimmed (labels.sql has why and which). Step 2c of the data build
# (data/README.md): after localize-cz/ and calendar/, before catalog/ — any order works (the step only retypes), but a
# rebuild from tpc-ds-1g brings the CHAR columns back, so it is on the rebuild recipe too.
#
# ONE transaction, as the postgres superuser over the pod-local socket (the run-redate.sh path). Idempotent: a second
# run changes nothing. Refuses `tpc-ds-1g` — the pristine source stays as dsdgen wrote it.
#
# Usage: ./run-labels.sh <kube-context> <database> [pod]
#        `just labels-data <us|cz> [ctx]` wraps it with the world's database and the pod.
set -euo pipefail
CTX="${1:?usage: run-labels.sh <kube-context> <database> [pod]}"; DB="${2:?database}"
POD="${3:-hartland-pg-1}"; NS="${EXTEND_NS:-data}"
DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=../extend/lib.sh
source "$DIR/../extend/lib.sh"

if [ "$DB" = "tpc-ds-1g" ]; then
  echo "refusing to retype tpc-ds-1g — the pristine source must stay as dsdgen wrote it" >&2; exit 2
fi

echo "== the label columns of $DB on context=$CTX"
pg "$DB" -1 -f - < "$DIR/labels.sql"
pg "$DB" -q -c "ANALYZE item; ANALYZE reason; ANALYZE promotion; ANALYZE household_demographics; ANALYZE date_dim"
