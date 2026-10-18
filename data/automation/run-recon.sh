#!/usr/bin/env bash
# AU-hartland P1 · S1.3 — R-A: print the automation extension's recon (90-recon.sql) for a built world and diff it
# against the committed baseline recon/R-A-<world>.md (README.md "Recon"). Read-only.
#
# Usage: ./run-recon.sh <kube-context> <database> <us|cz> [pod]
#        `just automation-recon <us|cz> [ctx]` wraps it.
# Exit: 0 = matches the baseline · 3 = drift (the diff is printed; the `check-model` convention) · 2 = no baseline.
# AUTOMATION_RECON_WRITE=1 writes the print as the new baseline instead (after a deliberate change — README).
set -euo pipefail
CTX="${1:?usage: run-recon.sh <kube-context> <database> <us|cz> [pod]}"; DB="${2:?database}"; WORLD="${3:?world}"
POD="${4:-hartland-pg-1}"; NS="${EXTEND_NS:-data}"
DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
source "$DIR/lib.sh"
BASE="$DIR/recon/R-A-$WORLD.md"

now="$(pg "$DB" -q -f - < "$DIR/90-recon.sql")"
if [ "${AUTOMATION_RECON_WRITE:-0}" = 1 ]; then
  mkdir -p "$DIR/recon"; printf '%s\n' "$now" > "$BASE"; echo "wrote $BASE"; exit 0
fi
if [ ! -f "$BASE" ]; then
  printf '%s\n' "$now"; echo "no baseline $BASE — write one with AUTOMATION_RECON_WRITE=1" >&2; exit 2
fi
if diff -u "$BASE" <(printf '%s\n' "$now"); then
  echo "R-A matches $BASE"
else
  echo "R-A drifted from $BASE (above: - baseline, + now)" >&2; exit 3
fi
