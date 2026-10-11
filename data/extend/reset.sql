-- LR (2026-10-11, ruling 11) — undo the extension: delete every row extend.sql wrote, so the world
-- can be extended again from its original data (after `order_offset` changed, say). The original
-- rows and `_extend_base` (each fact's last original date) stay; `_extend_meta` is emptied, so the
-- next run copies every week again.
--
--   psql -1 -f reset.sql        (as a superuser; run-reset.sh / `just extend-reset <world>`)
--
-- What is a copy, without knowing the offset it was written with (the same reading as tests/lib-test.sh):
--   a sale    — sold after its fact's base end (the originals end there by definition);
--   a return  — of such a sale (joined on order + item), whatever its own return date;
--   inventory — a snapshot after inventory's base end.
-- Sales rows with no sale date are originals (extend.sql never copies them) and stay.
-- Single transaction: a failure deletes nothing.
\set ON_ERROR_STOP on
SET client_min_messages = notice;

DO $body$
DECLARE
  f       record;
  n       bigint;
  base_sk int;
  total   bigint := 0;
BEGIN
  IF to_regclass('public._extend_base') IS NULL OR NOT EXISTS (SELECT 1 FROM _extend_base) THEN
    RAISE NOTICE 'reset: nothing to do — this database was never extended';
    RETURN;
  END IF;

  -- returns first: once the sales are gone, a copied return could no longer be told from an original
  FOR f IN SELECT * FROM (VALUES
      ('store_returns',   'sr_ticket_number', 'sr_item_sk', 'store_sales',   'ss_ticket_number', 'ss_item_sk', 'ss_sold_date_sk'),
      ('catalog_returns', 'cr_order_number',  'cr_item_sk', 'catalog_sales', 'cs_order_number',  'cs_item_sk', 'cs_sold_date_sk'),
      ('web_returns',     'wr_order_number',  'wr_item_sk', 'web_sales',     'ws_order_number',  'ws_item_sk', 'ws_sold_date_sk')
    ) v(tbl, okey, icol, stbl, sokey, sicol, sdcol)
  LOOP
    SELECT d.d_date_sk INTO base_sk FROM _extend_base b JOIN date_dim d ON d.d_date = b.base_end WHERE b.fact = f.stbl;
    EXECUTE format(
      'DELETE FROM %1$I r USING %2$I s WHERE s.%3$I = r.%4$I AND s.%5$I = r.%6$I AND s.%7$I > %8$s',
      f.tbl, f.stbl, f.sokey, f.okey, f.sicol, f.icol, f.sdcol, base_sk);
    GET DIAGNOSTICS n = ROW_COUNT;
    total := total + n;
    RAISE NOTICE '%: % rows deleted', f.tbl, n;
  END LOOP;

  FOR f IN SELECT * FROM (VALUES
      ('store_sales', 'ss_sold_date_sk'), ('catalog_sales', 'cs_sold_date_sk'), ('web_sales', 'ws_sold_date_sk'),
      ('inventory', 'inv_date_sk')
    ) v(tbl, dcol)
  LOOP
    SELECT d.d_date_sk INTO base_sk FROM _extend_base b JOIN date_dim d ON d.d_date = b.base_end WHERE b.fact = f.tbl;
    EXECUTE format('DELETE FROM %I WHERE %I > %s', f.tbl, f.dcol, base_sk);
    GET DIAGNOSTICS n = ROW_COUNT;
    total := total + n;
    RAISE NOTICE '%: % rows deleted', f.tbl, n;
  END LOOP;

  DELETE FROM _extend_meta;
  RAISE NOTICE 'reset: % rows deleted in all; _extend_meta emptied; the base ends are kept', total;
END
$body$;
