-- channel_sales — every sales line of the three channels, labelled by channel (one view, both worlds).
--
-- Why a view: on the er layer revenue was three attributes on three entities (store_sales,
-- web_sales, catalog_sales), so a bare *"revenue"* named three things and *"revenue by channel"*
-- had no object to group — the channel was which TABLE a row lived in, not a column anyone could
-- ask for. The lexicon refused to guess (RG-LEX-006) and the question fell to a curated pattern
-- query the resolving Golem never reaches. This view makes the channel a COLUMN and the three
-- revenues ONE measure, so `er.entity.channel_sales` answers *"revenue by channel for 2025 by
-- month"* deterministically on the fast path (model/er/sales.ttrm, lexicon/aliases).
--
-- Channel labels are the ones `q_hartland.channel_revenue_monthly` already returns ('store',
-- 'web', 'marketplace'), in BOTH worlds — one vocabulary for the pattern path and the fast path.
--
-- Idempotent (CREATE OR REPLACE; the GRANT is a no-op when already held). Run against each world:
--     psql -d hartland_us -f data/views/channel_sales.sql
--     psql -d hartland_cz -f data/views/channel_sales.sql
-- as the owner of the sales tables (`hartland`). The owner's default privileges already give each
-- world's `<db>_readonly` role SELECT on new relations in `public`; the GRANT below says so anyway,
-- so the view does not depend on that remaining true.
CREATE OR REPLACE VIEW public.channel_sales AS
SELECT 'store'::text          AS channel,
       ss_sold_date_sk        AS sold_date_sk,
       ss_item_sk             AS item_sk,
       ss_customer_sk         AS customer_sk,
       ss_quantity            AS quantity,
       ss_ext_sales_price     AS ext_sales_price
  FROM public.store_sales
UNION ALL
SELECT 'web', ws_sold_date_sk, ws_item_sk, ws_bill_customer_sk, ws_quantity, ws_ext_sales_price
  FROM public.web_sales
UNION ALL
SELECT 'marketplace', cs_sold_date_sk, cs_item_sk, cs_bill_customer_sk, cs_quantity, cs_ext_sales_price
  FROM public.catalog_sales;

COMMENT ON VIEW public.channel_sales IS
  'All-channel sales lines (store, web, marketplace) — model: er.entity.channel_sales. Source: hartland data/views/channel_sales.sql';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_database() || '_readonly') THEN
        EXECUTE format('GRANT SELECT ON public.channel_sales TO %I', current_database() || '_readonly');
    END IF;
END $$;
