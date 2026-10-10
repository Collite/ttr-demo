-- LR-P4 (contracts C-8) — extend the facts to :until by copying the template year forward, week
-- by week. The per-table copy spec, and why each choice: README.md (same directory).
--
--   psql -1 -v until=2026-10-31 -f extend.sql        (from this directory, as a superuser)
--
-- run-extend.sh pipes it into the pod with extend.conf prepended (the `\ir` below is skipped there).
-- Single transaction: a failure writes nothing. Incremental: `_extend_meta` holds every week already
-- extended, so a later date adds only the new weeks and the same date again is a no-op.
\set ON_ERROR_STOP on
\ir extend.conf

-- parameters into the session, for the DO block below (\gset swallows the echo)
SELECT set_config('extend.until',         :'until',         false) AS _u,
       set_config('extend.template_year', :'template_year', false) AS _t,
       set_config('extend.jitter_bp',     :'jitter_bp',     false) AS _j,
       set_config('extend.order_offset',  :'order_offset',  false) AS _o \gset
SET client_min_messages = warning;   -- no "already exists, skipping" on a prolong

-- Each fact's last ORIGINAL date, recorded by the first run. A copy is written only after it.
CREATE TABLE IF NOT EXISTS _extend_base (
  fact        text PRIMARY KEY,
  base_end    date NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now()
);

-- One row per extended target week: its template week, the 52-week cycle k, rows per fact.
CREATE TABLE IF NOT EXISTS _extend_meta (
  target_week_seq   int PRIMARY KEY,
  template_week_seq int NOT NULL,
  k                 int NOT NULL,
  applied_at        timestamptz NOT NULL DEFAULT now(),
  rows              jsonb NOT NULL
);

CREATE FUNCTION pg_temp.ext_cols(tbl text) RETURNS text LANGUAGE sql STABLE AS $$
  SELECT string_agg(quote_ident(column_name), ', ' ORDER BY ordinal_position)
  FROM information_schema.columns
  WHERE table_schema = 'public' AND table_name = tbl
$$;

-- The select list that turns template row `a` into its copy, column by column (read from the
-- catalog, so the US numeric(7,2) and the widened CZ numeric(10,2) both work):
--   *_date_sk        + 364·k          (d_date_sk is a day number: 52 weeks later, same weekday)
--   the order key    + order_offset·k (distinct from every original and every other cycle)
--   *quantity*       × j.f, rounded to a whole number
--   numeric (money)  × j.f, rounded per world: CZ as localize-cz/02-czk-fx.sql (10 Kč at >= 100 Kč),
--                    otherwise to the column's scale
--   anything else    verbatim
CREATE FUNCTION pg_temp.ext_exprs(tbl text, a text, kexpr text, okey text, off bigint, cz boolean)
RETURNS text LANGUAGE sql STABLE AS $$
  SELECT string_agg(
    CASE
      WHEN c.column_name LIKE '%\_date\_sk' ESCAPE '\'
        THEN format('%s.%I + 364 * %s', a, c.column_name, kexpr)
      WHEN c.column_name = okey
        THEN format('%s.%I::bigint + %s::bigint * %s', a, c.column_name, off, kexpr)
      WHEN c.column_name LIKE '%quantity%' AND c.data_type IN ('smallint', 'integer', 'bigint')
        THEN format('round(%s.%I * j.f)::%s', a, c.column_name, c.data_type)
      WHEN c.data_type = 'numeric' AND cz
        THEN format('CASE WHEN abs(%1$s.%2$I * j.f) < 100 THEN round(%1$s.%2$I * j.f, 2)'
                    ' ELSE round(%1$s.%2$I * j.f / 10.0) * 10 END', a, c.column_name)
      WHEN c.data_type = 'numeric'
        THEN format('round(%s.%I * j.f, %s)', a, c.column_name, coalesce(c.numeric_scale, 2))
      ELSE format('%s.%I', a, c.column_name)
    END || format(' AS %I', c.column_name),
    ', ' ORDER BY c.ordinal_position)
  FROM information_schema.columns c
  WHERE c.table_schema = 'public' AND c.table_name = tbl
$$;

SET client_min_messages = notice;

DO $body$
DECLARE
  until_d  date   := current_setting('extend.until')::date;
  tyear    int    := current_setting('extend.template_year')::int;
  bp       int    := current_setting('extend.jitter_bp')::int;
  off      bigint := current_setting('extend.order_offset')::bigint;
  cz       boolean := false;
  ws0      int;     -- first week of the template window (52 weeks wholly inside the template year)
  w_from   int;
  w_to     int;
  kmax     int;
  base_sk  int;
  maxord   bigint;
  n        bigint;
  total    bigint := 0;
  f        record;
  r        record;
BEGIN
  -- ---- the world: the CZ rounding applies where the CZK FX scaling was applied ----------------
  IF to_regclass('public._localize_meta') IS NOT NULL THEN
    EXECUTE 'SELECT EXISTS (SELECT 1 FROM _localize_meta WHERE step = ''czk_fx'')' INTO cz;
  END IF;

  -- ---- the template window ---------------------------------------------------------------------
  SELECT min(d.d_week_seq) INTO ws0
  FROM date_dim d
  WHERE d.d_year = tyear
    AND NOT EXISTS (SELECT 1 FROM date_dim o WHERE o.d_week_seq = d.d_week_seq AND o.d_year <> tyear);
  IF ws0 IS NULL OR EXISTS (SELECT 1 FROM date_dim WHERE d_week_seq = ws0 + 51 AND d_year <> tyear) THEN
    RAISE EXCEPTION 'extend: template year % does not hold 52 whole weeks in date_dim', tyear;
  END IF;

  -- ---- base ends: recorded once, before anything is copied -------------------------------------
  IF NOT EXISTS (SELECT 1 FROM _extend_base) THEN
    IF EXISTS (SELECT 1 FROM _extend_meta) THEN
      RAISE EXCEPTION 'extend: _extend_meta lists extended weeks but _extend_base is empty — refusing to guess where the original data ends';
    END IF;
    INSERT INTO _extend_base (fact, base_end)
    SELECT 'store_sales',   max(d.d_date) FROM store_sales   JOIN date_dim d ON d.d_date_sk = ss_sold_date_sk
    UNION ALL
    SELECT 'catalog_sales', max(d.d_date) FROM catalog_sales JOIN date_dim d ON d.d_date_sk = cs_sold_date_sk
    UNION ALL
    SELECT 'web_sales',     max(d.d_date) FROM web_sales     JOIN date_dim d ON d.d_date_sk = ws_sold_date_sk
    UNION ALL
    SELECT 'inventory',     max(d.d_date) FROM inventory     JOIN date_dim d ON d.d_date_sk = inv_date_sk;
    FOR r IN SELECT fact, base_end FROM _extend_base ORDER BY fact LOOP
      RAISE NOTICE 'base end recorded: % = %', r.fact, r.base_end;
    END LOOP;
  END IF;
  IF (SELECT min(base_end) FROM _extend_base)
     <= (SELECT max(d_date) FROM date_dim WHERE d_week_seq = ws0 + 51) THEN
    RAISE EXCEPTION 'extend: the data ends inside the template year % — is this database re-dated (data/redate)?', tyear;
  END IF;

  -- ---- the weeks this run extends --------------------------------------------------------------
  SELECT d_week_seq INTO w_from FROM date_dim WHERE d_date = (SELECT min(base_end) FROM _extend_base) + 1;
  SELECT d_week_seq INTO w_to   FROM date_dim WHERE d_date = until_d;
  IF w_to IS NULL OR NOT EXISTS (SELECT 1 FROM date_dim WHERE d_date = until_d + 7) THEN
    RAISE EXCEPTION 'extend: % is past the end of date_dim', until_d;
  END IF;

  CREATE TEMP TABLE _ext_weeks ON COMMIT DROP AS
  SELECT w AS target_week_seq, ws0 + ((w - ws0) % 52) AS template_week_seq, (w - ws0) / 52 AS k
  FROM generate_series(w_from, w_to) w
  WHERE NOT EXISTS (SELECT 1 FROM _extend_meta m WHERE m.target_week_seq = w);

  IF NOT EXISTS (SELECT 1 FROM _ext_weeks) THEN
    RAISE NOTICE 'extend: nothing to do — every week up to % (week_seq %) is already extended', until_d, w_to;
    RETURN;
  END IF;
  SELECT max(k) INTO kmax FROM _ext_weeks;
  RAISE NOTICE 'extend: % weeks (week_seq % .. %, % .. %), template %, cycles k = % .. %, % rounding',
    (SELECT count(*) FROM _ext_weeks), (SELECT min(target_week_seq) FROM _ext_weeks), w_to,
    (SELECT min(d_date) FROM date_dim WHERE d_week_seq = (SELECT min(target_week_seq) FROM _ext_weeks)),
    (SELECT max(d_date) FROM date_dim WHERE d_week_seq = w_to),
    tyear, (SELECT min(k) FROM _ext_weeks), kmax, CASE WHEN cz THEN 'CZ (10 Kč)' ELSE 'column-scale' END;

  -- ---- order keys must fit their column (they are `integer` in TPC-DS) -------------------------
  FOR f IN SELECT * FROM (VALUES
      ('store_sales', 'ss_ticket_number'), ('catalog_sales', 'cs_order_number'), ('web_sales', 'ws_order_number'),
      ('store_returns', 'sr_ticket_number'), ('catalog_returns', 'cr_order_number'), ('web_returns', 'wr_order_number')
    ) v(tbl, okey)
  LOOP
    IF (SELECT data_type FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = f.tbl AND column_name = f.okey) = 'integer' THEN
      EXECUTE format('SELECT max(%I) FROM %I WHERE %I < %s', f.okey, f.tbl, f.okey, off) INTO maxord;
      IF maxord + off * kmax > 2147483647 THEN
        RAISE EXCEPTION 'extend: %.% is integer and % + % × k=% overflows it (k = % starts %). Lower order_offset in extend.conf (keep it above %) or widen the column.',
          f.tbl, f.okey, maxord, off, kmax, kmax,
          (SELECT min(d_date) FROM date_dim WHERE d_week_seq = ws0 + 52 * kmax), maxord;
      END IF;
    END IF;
  END LOOP;

  CREATE TEMP TABLE _ext_counts (w int, fact text, n bigint) ON COMMIT DROP;

  -- ---- sales: template rows sold in the template week, written after the fact's base end -------
  FOR f IN SELECT * FROM (VALUES
      ('store_sales',   'ss_sold_date_sk', 'ss_ticket_number', 'ss_item_sk'),
      ('catalog_sales', 'cs_sold_date_sk', 'cs_order_number',  'cs_item_sk'),
      ('web_sales',     'ws_sold_date_sk', 'ws_order_number',  'ws_item_sk')
    ) v(tbl, dcol, okey, icol)
  LOOP
    SELECT d.d_date_sk INTO base_sk FROM _extend_base b JOIN date_dim d ON d.d_date = b.base_end WHERE b.fact = f.tbl;
    EXECUTE format($q$
      CREATE TEMP TABLE _ext_new ON COMMIT DROP AS
      SELECT %1$s, x.target_week_seq AS _w
      FROM %2$I s
      JOIN date_dim d    ON d.d_date_sk = s.%3$I
      JOIN _ext_weeks x  ON x.template_week_seq = d.d_week_seq
      CROSS JOIN LATERAL (
        SELECT 1 + ((abs(hashtext((s.%4$I::bigint + %5$s::bigint * x.k)::text || s.%6$I::text)::bigint) %% %7$s) - %8$s) / 10000.0 AS f
      ) j
      WHERE s.%3$I + 364 * x.k > %9$s
    $q$, pg_temp.ext_exprs(f.tbl, 's', 'x.k', f.okey, off, cz), f.tbl, f.dcol, f.okey, off, f.icol,
         2 * bp + 1, bp, base_sk);
    EXECUTE format('INSERT INTO %I (%s) SELECT %s FROM _ext_new', f.tbl, pg_temp.ext_cols(f.tbl), pg_temp.ext_cols(f.tbl));
    GET DIAGNOSTICS n = ROW_COUNT;
    INSERT INTO _ext_counts SELECT _w, f.tbl, count(*) FROM _ext_new GROUP BY _w;
    DROP TABLE _ext_new;
    total := total + n;
    RAISE NOTICE '%: % rows', f.tbl, n;
  END LOOP;

  -- ---- returns: the returns of a COPIED sale, shifted with it, landing in this run's weeks -----
  -- (k comes from the sale; a return with no return date goes into its sale's week)
  FOR f IN SELECT * FROM (VALUES
      ('store_returns',   'sr_returned_date_sk', 'sr_ticket_number', 'sr_item_sk', 'store_sales',   'ss_sold_date_sk', 'ss_ticket_number', 'ss_item_sk'),
      ('catalog_returns', 'cr_returned_date_sk', 'cr_order_number',  'cr_item_sk', 'catalog_sales', 'cs_sold_date_sk', 'cs_order_number',  'cs_item_sk'),
      ('web_returns',     'wr_returned_date_sk', 'wr_order_number',  'wr_item_sk', 'web_sales',     'ws_sold_date_sk', 'ws_order_number',  'ws_item_sk')
    ) v(tbl, dcol, okey, icol, stbl, sdcol, sokey, sicol)
  LOOP
    SELECT d.d_date_sk INTO base_sk FROM _extend_base b JOIN date_dim d ON d.d_date = b.base_end WHERE b.fact = f.stbl;
    EXECUTE format($q$
      CREATE TEMP TABLE _ext_new ON COMMIT DROP AS
      SELECT %1$s, x.target_week_seq AS _w
      FROM %2$I r
      JOIN %3$I s        ON s.%4$I = r.%5$I AND s.%6$I = r.%7$I
      JOIN date_dim ds   ON ds.d_date_sk = s.%8$I
      LEFT JOIN date_dim dr ON dr.d_date_sk = r.%9$I
      CROSS JOIN generate_series(1, %10$s) kk(k)
      JOIN _ext_weeks x  ON x.target_week_seq = coalesce(dr.d_week_seq, ds.d_week_seq) + 52 * kk.k
      CROSS JOIN LATERAL (
        SELECT 1 + ((abs(hashtext((r.%5$I::bigint + %11$s::bigint * kk.k)::text || r.%7$I::text)::bigint) %% %12$s) - %13$s) / 10000.0 AS f
      ) j
      WHERE ds.d_week_seq BETWEEN %14$s AND %14$s + 51       -- the sale is a template row …
        AND s.%8$I + 364 * kk.k > %15$s                       -- … whose copy is after the base end …
        AND ds.d_week_seq + 52 * kk.k <= %16$s                -- … and already written (this run or before)
    $q$, pg_temp.ext_exprs(f.tbl, 'r', 'kk.k', f.okey, off, cz), f.tbl, f.stbl, f.sokey, f.okey, f.sicol, f.icol,
         f.sdcol, f.dcol, kmax, off, 2 * bp + 1, bp, ws0, base_sk, w_to);
    EXECUTE format('INSERT INTO %I (%s) SELECT %s FROM _ext_new', f.tbl, pg_temp.ext_cols(f.tbl), pg_temp.ext_cols(f.tbl));
    GET DIAGNOSTICS n = ROW_COUNT;
    INSERT INTO _ext_counts SELECT _w, f.tbl, count(*) FROM _ext_new GROUP BY _w;
    DROP TABLE _ext_new;
    total := total + n;
    RAISE NOTICE '%: % rows', f.tbl, n;
  END LOOP;

  -- ---- inventory: the template week's snapshots (unique by date, item, warehouse) -------------
  SELECT d.d_date_sk INTO base_sk FROM _extend_base b JOIN date_dim d ON d.d_date = b.base_end WHERE b.fact = 'inventory';
  EXECUTE format($q$
    CREATE TEMP TABLE _ext_new ON COMMIT DROP AS
    SELECT %1$s, x.target_week_seq AS _w
    FROM inventory s
    JOIN date_dim d   ON d.d_date_sk = s.inv_date_sk
    JOIN _ext_weeks x ON x.template_week_seq = d.d_week_seq
    CROSS JOIN LATERAL (
      SELECT 1 + ((abs(hashtext((s.inv_date_sk + 364 * x.k)::text || '-' || s.inv_item_sk::text || '-' || s.inv_warehouse_sk::text)::bigint) %% %2$s) - %3$s) / 10000.0 AS f
    ) j
    WHERE s.inv_date_sk + 364 * x.k > %4$s
  $q$, pg_temp.ext_exprs('inventory', 's', 'x.k', '', off, cz), 2 * bp + 1, bp, base_sk);
  EXECUTE format('INSERT INTO inventory (%s) SELECT %s FROM _ext_new', pg_temp.ext_cols('inventory'), pg_temp.ext_cols('inventory'));
  GET DIAGNOSTICS n = ROW_COUNT;
  INSERT INTO _ext_counts SELECT _w, 'inventory', count(*) FROM _ext_new GROUP BY _w;
  DROP TABLE _ext_new;
  total := total + n;
  RAISE NOTICE 'inventory: % rows', n;

  -- ---- record every week of this run, with what it got -----------------------------------------
  INSERT INTO _extend_meta (target_week_seq, template_week_seq, k, rows)
  SELECT x.target_week_seq, x.template_week_seq, x.k,
         (SELECT jsonb_object_agg(t.fact, coalesce(c.n, 0))
            FROM unnest(ARRAY['store_sales', 'catalog_sales', 'web_sales', 'store_returns',
                              'catalog_returns', 'web_returns', 'inventory']) t(fact)
            LEFT JOIN _ext_counts c ON c.fact = t.fact AND c.w = x.target_week_seq)
  FROM _ext_weeks x;

  FOR r IN
    SELECT m.target_week_seq, m.template_week_seq, m.k, m.rows,
           (SELECT min(d_date) FROM date_dim WHERE d_week_seq = m.target_week_seq) AS d_from
    FROM _extend_meta m JOIN _ext_weeks x USING (target_week_seq)
    ORDER BY m.target_week_seq
  LOOP
    RAISE NOTICE 'week % (from %) <- template week % (k=%): %', r.target_week_seq, r.d_from, r.template_week_seq, r.k, r.rows;
  END LOOP;
  RAISE NOTICE 'TOTAL rows written: %', total;
END
$body$;
