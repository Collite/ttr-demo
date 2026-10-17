-- AU-hartland P1 · S1.1 — the extension's foreign keys (contracts §1: the 22, and the 4 S0.1 added), added once
-- the data is in: one validating scan each instead of a trigger check per inserted row. Each is added only if
-- missing (a reset drops fk_c_center with the rest; the others go with their tables). The model's three LOGICAL
-- keys on the return_request VIEW (fk_rrv_*, fk_rlv_request) have no DDL: a view carries no constraint.
DO $$
DECLARE k text[];
BEGIN
  FOREACH k SLICE 1 IN ARRAY ARRAY[
    ['fk_so_customer',    'sales_order',          'so_customer_sk',          'customer',           'c_customer_sk'],
    ['fk_so_warehouse',   'sales_order',          'so_warehouse_sk',         'warehouse',          'w_warehouse_sk'],
    ['fk_sl_order',       'sales_line',           'sl_order_number',         'sales_order',        'so_order_number'],
    ['fk_sl_item',        'sales_line',           'sl_item_sk',              'item',               'i_item_sk'],
    ['fk_sl_warehouse',   'sales_line',           'sl_warehouse_sk',         'warehouse',          'w_warehouse_sk'],
    ['fk_sl_customer',    'sales_line',           'sl_customer_sk',          'customer',           'c_customer_sk'],
    ['fk_pl_item',        'price_list',           'pl_item_sk',              'item',               'i_item_sk'],
    ['fk_cp_item',        'customer_price',       'cp_item_sk',              'item',               'i_item_sk'],
    ['fk_cp_customer',    'customer_price',       'cp_customer_sk',          'customer',           'c_customer_sk'],
    ['fk_inv_customer',   'invoice',              'inv_customer_sk',         'customer',           'c_customer_sk'],
    ['fk_inv_order',      'invoice',              'inv_order_number',        'sales_order',        'so_order_number'],
    ['fk_wo_warehouse',   'warehouse_outage',     'wo_warehouse_sk',         'warehouse',          'w_warehouse_sk'],
    ['fk_rr_customer',    'return_request_hdr',   'rr_customer_sk',          'customer',           'c_customer_sk'],
    ['fk_rr_order',       'return_request_hdr',   'rr_order_number',         'sales_order',        'so_order_number'],
    ['fk_rl_request',     'return_request_line',  'rl_request_number',       'return_request_hdr', 'rr_request_number'],
    ['fk_rl_item',        'return_request_line',  'rl_item_sk',              'item',               'i_item_sk'],
    ['fk_rl_variant',     'return_request_line',  'rl_requested_variant_sk', 'item',               'i_item_sk'],
    ['fk_rl_customer',    'return_request_line',  'rl_customer_sk',          'customer',           'c_customer_sk'],
    ['fk_rc_line',        'return_receipt',       'rc_line_id',              'return_request_line', 'rl_line_id'],
    ['fk_cn_line',        'credit_note',          'cn_line_id',              'return_request_line', 'rl_line_id'],
    ['fk_rp_credit_note', 'refund_payment',       'rp_credit_note_id',       'credit_note',        'cn_credit_note_id'],
    ['fk_rs_line',        'replacement_shipment', 'rs_line_id',              'return_request_line', 'rl_line_id'],
    ['fk_rp_item',        'reorder_proposal',     'rp_item_sk',              'item',               'i_item_sk'],
    ['fk_rp_warehouse',   'reorder_proposal',     'rp_warehouse_sk',         'warehouse',          'w_warehouse_sk'],
    ['fk_wm_customer',    'winback_mail',         'wm_customer_sk',          'customer',           'c_customer_sk'],
    ['fk_c_center',       'customer',             'c_center_sk',             'warehouse',          'w_warehouse_sk']
  ] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = k[1] AND conrelid = ('public.' || k[2])::regclass) THEN
      EXECUTE format('ALTER TABLE public.%I ADD CONSTRAINT %I FOREIGN KEY (%I) REFERENCES public.%I (%I)', k[2], k[1], k[3], k[4], k[5]);
    END IF;
  END LOOP;
END $$;

INSERT INTO _automation_meta (step, as_of, rows)
SELECT '80-keys', :'as_of', count(*) FROM pg_constraint WHERE contype = 'f' AND conname LIKE 'fk\_%' AND connamespace = 'public'::regnamespace
   AND conrelid::regclass::text IN ('sales_order', 'sales_line', 'price_list', 'customer_price', 'invoice', 'warehouse_outage',
                                    'return_request_hdr', 'return_request_line', 'return_receipt', 'credit_note', 'refund_payment',
                                    'replacement_shipment', 'reorder_proposal', 'winback_mail', 'customer');
