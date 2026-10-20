#!/usr/bin/env bash
# The calendar correction's suite, on a throwaway local Postgres (data/automation/tests/pg-local.sh — no Docker,
# no cluster). It builds a date_dim the way dsdgen gets it wrong — quarters cut on a 366-day year, a
# Friday-and-Saturday weekend, 01-01 / 07-05 / 12-26 in non-leap years, two odd weekdays — for 2020–2027 (two
# leap years), corrects it as each world and checks the result against the published calendars.
#
#   tests/test-calendar.sh          `just calendar-test`
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CAL_DIR="$(cd "$HERE/.." && pwd)"
# shellcheck source=../../automation/tests/pg-local.sh
source "$CAL_DIR/../automation/tests/pg-local.sh"
pg_local_start || exit 1
trap pg_local_stop EXIT
# shellcheck source=../../extend/tests/lib-test.sh
source "$CAL_DIR/../extend/tests/lib-test.sh"

createdb cal_us || exit 1
pg cal_us -q -f - <<'SQL'
CREATE TABLE date_dim (
  d_date_sk      integer PRIMARY KEY,
  d_date         date,
  d_year         integer,
  d_dow          integer,
  d_moy          integer,
  d_dom          integer,
  d_qoy          integer,
  d_day_name     char(9),
  d_quarter_name char(6),
  d_holiday      char(1),
  d_weekend      char(1)
);
INSERT INTO date_dim
SELECT (d - DATE '1900-01-02') + 2415022, d, y,
       extract(dow FROM d)::int + odd, extract(month FROM d)::int, extract(day FROM d)::int,
       extract(quarter FROM d - qshift)::int, to_char(d + odd, 'FMDay'), to_char(d - qshift, 'YYYY"Q"Q'),
       CASE WHEN to_char(d, 'MM-DD') = '01-01' OR to_char(d - hshift, 'MM-DD') IN ('07-04', '12-25') THEN 'Y' ELSE 'N' END,
       CASE WHEN extract(isodow FROM d) IN (5, 6) THEN 'Y' ELSE 'N' END
FROM generate_series(DATE '2020-01-01', DATE '2027-12-31', interval '1 day') g(t),
     LATERAL (SELECT t::date AS d, extract(year FROM t)::int AS y) x,
     LATERAL (SELECT (y % 4 = 0 AND (y % 100 <> 0 OR y % 400 = 0)) AS leap) l,
     LATERAL (SELECT CASE WHEN NOT leap AND to_char(d, 'MM-DD') IN ('04-01', '07-01', '10-01') THEN 1 ELSE 0 END AS qshift,
                     CASE WHEN NOT leap THEN 1 ELSE 0 END AS hshift,
                     CASE WHEN d IN (DATE '2021-03-03', DATE '2025-06-11') THEN 1 ELSE 0 END AS odd) s;
SQL
pgq postgres "CREATE DATABASE cal_cz TEMPLATE cal_us" >/dev/null
pg cal_cz -q -c "CREATE TABLE _localize_meta (step text PRIMARY KEY, detail text);
                 INSERT INTO _localize_meta VALUES ('czk_fx', 'test-calendar.sh')"

wrong() { # wrong <db> — the rows whose quarter, weekday or weekend disagrees with d_date
  pgq "$1" "SELECT count(*) FROM date_dim WHERE d_qoy <> extract(quarter FROM d_date) OR d_dow <> extract(dow FROM d_date)
              OR d_quarter_name <> to_char(d_date, 'YYYY\"Q\"Q') OR rtrim(d_day_name) <> to_char(d_date, 'FMDay')
              OR (d_weekend = 'Y') <> (extract(isodow FROM d_date) IN (6, 7))"
}
holidays() { # holidays <db> <year>
  pgq "$1" "SELECT string_agg(to_char(d_date, 'MM-DD'), ' ' ORDER BY d_date) FROM date_dim WHERE d_year = $2 AND d_holiday = 'Y'"
}
fp() { pgq "$1" "SELECT md5(string_agg(x::text, '|' ORDER BY d_date_sk)) FROM date_dim x"; }
run() { bash "$CAL_DIR/run-calendar.sh" local "$1" "$2" - 2>&1; }

echo "== as dsdgen wrote it"
expect "dsdgen's Q3 2025 is 07-02 … 10-01" "$(pgq cal_us "SELECT min(d_date) || ' ' || max(d_date) FROM date_dim WHERE d_year = 2025 AND d_qoy = 3")" = "2025-07-02 2025-10-01"
expect "the leap years' quarters are right" "$(pgq cal_us "SELECT count(*) FROM date_dim WHERE d_year IN (2020, 2024) AND d_qoy <> extract(quarter FROM d_date)")" -eq 0
expect "rows that disagree with d_date (Fridays, Sundays, quarter starts)" "$(wrong cal_us)" -gt 800

echo "== the us world"
out="$(run cal_us us)"; rc=$?
expect "run-calendar.sh exits 0" "$rc" -eq 0
expect "nothing disagrees with d_date" "$(wrong cal_us)" -eq 0
expect "Q3 2025 is 07-01 … 09-30" "$(pgq cal_us "SELECT min(d_date) || ' ' || max(d_date) FROM date_dim WHERE d_year = 2025 AND d_qoy = 3")" = "2025-07-01 2025-09-30"
expect "the weekend is Saturday and Sunday" "$(pgq cal_us "SELECT string_agg(DISTINCT extract(isodow FROM d_date)::text, ',' ORDER BY extract(isodow FROM d_date)::text) FROM date_dim WHERE d_weekend = 'Y'")" = "6,7"
expect "2025: the 11 federal holidays" "$(holidays cal_us 2025)" = "01-01 01-20 02-17 05-26 06-19 07-04 09-01 10-13 11-11 11-27 12-25"
expect "2026: 07-04 is a Saturday, observed Friday 07-03" "$(holidays cal_us 2026)" = "01-01 01-19 02-16 05-25 06-19 07-03 07-04 09-07 10-12 11-11 11-26 12-25"
expect "2027: Saturdays back to Friday, Sunday on to Monday, 2028-01-01 to 12-31" "$(holidays cal_us 2027)" = "01-01 01-18 02-15 05-31 06-18 06-19 07-04 07-05 09-06 10-11 11-11 11-25 12-24 12-25 12-31"
before="$(fp cal_us)"
out="$(run cal_us us)"; rc=$?
expect "a second run exits 0" "$rc" -eq 0
expect "a second run updates nothing" "$(grep -c '^UPDATE 0$' <<<"$out")" -eq 6
expect "a second run leaves date_dim byte-identical" "$(fp cal_us)" = "$before"

echo "== the cz world"
out="$(run cal_us cz)"; rc=$?
expect "the us world named cz is refused" "$rc" -eq 2
out="$(run cal_cz us)"; rc=$?
expect "the cz world named us is refused" "$rc" -eq 2
out="$(run cal_cz cz)"; rc=$?
expect "run-calendar.sh exits 0" "$rc" -eq 0
expect "nothing disagrees with d_date" "$(wrong cal_cz)" -eq 0
expect "2025: the 13 Czech days off (Easter 04-20)" "$(holidays cal_cz 2025)" = "01-01 04-18 04-21 05-01 05-08 07-05 07-06 09-28 10-28 11-17 12-24 12-25 12-26"
expect "2026: Easter 04-05" "$(holidays cal_cz 2026)" = "01-01 04-03 04-06 05-01 05-08 07-05 07-06 09-28 10-28 11-17 12-24 12-25 12-26"
expect "2024 (leap): Easter 03-31" "$(holidays cal_cz 2024)" = "01-01 03-29 04-01 05-01 05-08 07-05 07-06 09-28 10-28 11-17 12-24 12-25 12-26"
expect "no substitute days in cz (2027-05-08 is a Saturday)" "$(pgq cal_cz "SELECT count(*) FROM date_dim WHERE d_date IN (DATE '2027-05-07', DATE '2027-05-10') AND d_holiday = 'Y'")" -eq 0

echo "== a world with the automation extension built"
pg cal_cz -q -c "CREATE TABLE _automation_meta (step text, as_of date, rows bigint); INSERT INTO _automation_meta VALUES ('25-calendar', DATE '2026-10-26', 1)"
out="$(run cal_cz cz)"; rc=$?
expect "is refused (reset it first)" "$rc" -eq 2
expect "and says how" "$(grep -c 'just automation-reset cz' <<<"$out")" -eq 1

finish
