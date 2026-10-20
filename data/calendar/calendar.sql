-- The calendar correction (data/README.md step 2b) — date_dim as dsdgen wrote it, corrected from d_date itself.
-- run-calendar.sh runs it in ONE transaction as the postgres superuser, with -v world=us|cz.
--
-- What dsdgen gets wrong (the audit of hartland_cz and hartland_us, 2026-10-20 — both worlds alike):
--   * d_qoy / d_quarter_name: the quarters are cut on a 366-day year, so in every non-leap year 04-01, 07-01
--     and 10-01 belong to the quarter before (450 days, 1900–2100). "Q3 2025" through the calendar was
--     07-02 … 10-01.
--   * d_weekend: Friday and Saturday; Sunday was a working day.
--   * d_holiday: three days a year, two of them a day late in non-leap years (2025: 01-01, 07-05, 12-26).
--   * d_dow / d_day_name: 59 scattered days between 1900 and 2100.
-- The holidays become the world's own public holidays, today's rules on every year of the table:
--   cz — the 13 days off of zákon 245/2000 Sb.: 01-01, Good Friday, Easter Monday, 05-01, 05-08, 07-05, 07-06,
--        09-28, 10-28, 11-17, 12-24, 12-25, 12-26 (no substitute day when one falls on a weekend);
--   us — the 11 federal holidays (5 U.S.C. 6103): 01-01, MLK Day, Washington's Birthday, Memorial Day, 06-19,
--        07-04, Labor Day, Columbus Day, 11-11, Thanksgiving, 12-25; a fixed one on a Saturday is also observed
--        the Friday before, on a Sunday the Monday after — both days are marked.
-- d_working_day (the automation extension's column) is NOT touched here: it is derived from these flags by
-- data/automation/25-calendar.sql, so the runner refuses a world whose extension is built (reset it first).
-- The TPC-DS columns no model maps (d_quarter_seq, d_fy_*, d_following_holiday, d_same_day_*, d_current_*) stay
-- as dsdgen wrote them.
--
-- Idempotent: every UPDATE writes only the rows that differ, so a second run prints UPDATE 0 six times.

SELECT set_config('calendar.world', :'world', false);
DO $$ BEGIN
  IF current_setting('calendar.world') NOT IN ('us', 'cz') THEN
    RAISE EXCEPTION 'world must be us or cz, got %', current_setting('calendar.world');
  END IF;
END $$;

-- ---- the quarter, the weekday, the weekend: from d_date --------------------------------------------------------
\echo '-- d_qoy'
UPDATE date_dim SET d_qoy = extract(quarter FROM d_date)::int
 WHERE d_date IS NOT NULL AND d_qoy IS DISTINCT FROM extract(quarter FROM d_date)::int;
\echo '-- d_quarter_name'
UPDATE date_dim SET d_quarter_name = to_char(d_date, 'YYYY"Q"Q')
 WHERE d_date IS NOT NULL AND d_quarter_name IS DISTINCT FROM to_char(d_date, 'YYYY"Q"Q');
\echo '-- d_dow'
UPDATE date_dim SET d_dow = extract(dow FROM d_date)::int
 WHERE d_date IS NOT NULL AND d_dow IS DISTINCT FROM extract(dow FROM d_date)::int;
\echo '-- d_day_name'
UPDATE date_dim SET d_day_name = to_char(d_date, 'FMDay')
 WHERE d_date IS NOT NULL AND rtrim(d_day_name) IS DISTINCT FROM to_char(d_date, 'FMDay');
\echo '-- d_weekend'
UPDATE date_dim SET d_weekend = CASE WHEN extract(isodow FROM d_date) IN (6, 7) THEN 'Y' ELSE 'N' END
 WHERE d_date IS NOT NULL
   AND d_weekend IS DISTINCT FROM CASE WHEN extract(isodow FROM d_date) IN (6, 7) THEN 'Y' ELSE 'N' END;

-- ---- the world's public holidays ----------------------------------------------------------------------------------
-- pg_temp.cal_nth(y, m, w, n): the n-th ISO weekday w (1 = Monday) of month m; n = -1 the last.
CREATE FUNCTION pg_temp.cal_nth(y int, m int, w int, n int) RETURNS date LANGUAGE sql IMMUTABLE AS $f$
  SELECT CASE WHEN n > 0
    THEN make_date(y, m, 1) + (w - extract(isodow FROM make_date(y, m, 1))::int + 7) % 7 + 7 * (n - 1)
    ELSE (make_date(y, m, 1) + interval '1 month')::date - 1
         - (extract(isodow FROM (make_date(y, m, 1) + interval '1 month')::date - 1)::int - w + 7) % 7
  END $f$;
-- pg_temp.cal_easter(y): Easter Sunday, the anonymous Gregorian algorithm (Meeus/Jones/Butcher).
CREATE FUNCTION pg_temp.cal_easter(y int) RETURNS date LANGUAGE sql IMMUTABLE AS $f$
  SELECT make_date(y, (h + l - 7 * m + 114) / 31, (h + l - 7 * m + 114) % 31 + 1)
  FROM (SELECT y % 19 AS a, y / 100 AS b, y % 100 AS c) s1,
       LATERAL (SELECT b / 4 AS d, b % 4 AS e, (b + 8) / 25 AS f) s2,
       LATERAL (SELECT (19 * a + b - d - (b - f + 1) / 3 + 15) % 30 AS h, c / 4 AS i, c % 4 AS k) s3,
       LATERAL (SELECT (32 + 2 * e + 2 * i - h - k) % 7 AS l) s4,
       LATERAL (SELECT (a + 11 * h + 22 * l) / 451 AS m) s5 $f$;

-- One year either side of the table, so 01-01 on a Saturday reaches back to the 31st before it.
CREATE TEMP TABLE _cal_year AS
SELECT generate_series(min(d_year) - 1, max(d_year) + 1) AS y FROM date_dim;

CREATE TEMP TABLE _cal_holiday AS
SELECT DISTINCT d FROM (
  -- cz: the fixed days, Good Friday, Easter Monday
  SELECT make_date(y, f.m, f.dd) AS d
    FROM _cal_year, (VALUES (1, 1), (5, 1), (5, 8), (7, 5), (7, 6), (9, 28), (10, 28), (11, 17),
                            (12, 24), (12, 25), (12, 26)) f(m, dd)
   WHERE :'world' = 'cz'
  UNION ALL SELECT pg_temp.cal_easter(y) + x FROM _cal_year, (VALUES (-2), (1)) e(x) WHERE :'world' = 'cz'
  -- us: the fixed days, and the weekday each is observed on
  UNION ALL SELECT o.d
    FROM _cal_year, (VALUES (1, 1), (6, 19), (7, 4), (11, 11), (12, 25)) f(m, dd),
         LATERAL (SELECT make_date(y, f.m, f.dd) AS day) h,
         LATERAL (SELECT h.day AS d
                  UNION ALL SELECT h.day + CASE extract(isodow FROM h.day) WHEN 6 THEN -1 WHEN 7 THEN 1 END
                   WHERE extract(isodow FROM h.day) IN (6, 7)) o
   WHERE :'world' = 'us'
  -- us: the Mondays and Thanksgiving
  UNION ALL SELECT pg_temp.cal_nth(y, f.m, f.w, f.n)
    FROM _cal_year, (VALUES (1, 1, 3), (2, 1, 3), (5, 1, -1), (9, 1, 1), (10, 1, 2), (11, 4, 4)) f(m, w, n)
   WHERE :'world' = 'us'
) x;

\echo '-- d_holiday'
UPDATE date_dim SET d_holiday = CASE WHEN d_date IN (SELECT d FROM _cal_holiday) THEN 'Y' ELSE 'N' END
 WHERE d_date IS NOT NULL
   AND d_holiday IS DISTINCT FROM CASE WHEN d_date IN (SELECT d FROM _cal_holiday) THEN 'Y' ELSE 'N' END;

\echo '-- the world''s holidays this year and next'
SELECT :'world' AS world, d_year, count(*) AS holidays, string_agg(to_char(d_date, 'MM-DD'), ' ' ORDER BY d_date) AS days
  FROM date_dim
 WHERE d_holiday = 'Y' AND d_year BETWEEN extract(year FROM current_date)::int AND extract(year FROM current_date)::int + 1
 GROUP BY d_year ORDER BY d_year;
