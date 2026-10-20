#!/usr/bin/env bash
# The calendar correction — date_dim's quarter, weekday, weekend and the world's public holidays, from d_date
# (calendar.sql has what dsdgen gets wrong and the holiday rules). Step 2b of the data build (data/README.md):
# after localize-cz/, whose `czk_fx` row tells the worlds apart.
#
# ONE transaction, as the postgres superuser over the pod-local socket (the run-redate.sh path). Idempotent: a
# second run changes nothing. Refuses `tpc-ds-1g`, a world that is not the one named (cz ⇔ localize-cz's
# `czk_fx` guard row — the automation runner's rule), and a world whose automation extension is built: its
# d_working_day and due dates come from these flags, so `just automation-reset <world>` first and
# `just automation-data <world>` after.
#
# Usage: ./run-calendar.sh <kube-context> <database> <us|cz> [pod]
#        `just calendar-data <us|cz> [ctx]` wraps it with the world's database and the pod.
set -euo pipefail
CTX="${1:?usage: run-calendar.sh <kube-context> <database> <us|cz> [pod]}"; DB="${2:?database}"; WORLD="${3:?world}"
POD="${4:-hartland-pg-1}"; NS="${EXTEND_NS:-data}"
DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=../extend/lib.sh
source "$DIR/../extend/lib.sh"

case "$WORLD" in us|cz) ;; *) echo "world must be us or cz, got '$WORLD'" >&2; exit 2 ;; esac
if [ "$DB" = "tpc-ds-1g" ]; then
  echo "refusing to correct tpc-ds-1g — the pristine source must stay as dsdgen wrote it" >&2; exit 2
fi

# A query naming a missing table fails at parse time, CASE or not: ask whether it exists first.
has() { [ "$(pgq "$DB" "SELECT to_regclass('public.$1') IS NOT NULL")" = t ]; }

is=us
if has _localize_meta && [ "$(pgq "$DB" "SELECT EXISTS (SELECT 1 FROM _localize_meta WHERE step = 'czk_fx')")" = t ]; then
  is=cz
fi
if [ "$is" != "$WORLD" ]; then
  echo "refusing: $DB is the $is world (localize-cz's czk_fx row), not $WORLD" >&2; exit 2
fi
if has _automation_meta && [ "$(pgq "$DB" "SELECT count(*) FROM _automation_meta")" -gt 0 ]; then
  echo "refusing: $DB has the automation extension built — its working days come from date_dim." >&2
  echo "  just automation-reset $WORLD   then this   then just automation-data $WORLD" >&2; exit 2
fi

echo "== the calendar of $DB ($WORLD world) on context=$CTX"
pg "$DB" -1 -v world="$WORLD" -f - < "$DIR/calendar.sql"
pg "$DB" -q -c "ANALYZE date_dim"
