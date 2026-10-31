#!/usr/bin/env bash
# AU-hartland P1·S1.1 T1 — after one build, the world has exactly contracts §1: every table with its columns (in
# order, with their types) and primary key, the 26 foreign keys validated, the two column adds, the two views,
# the internals, all owned by the facts' owner — and the money is the facts' own (not scaled again).
# Works on a throwaway copy of <db>:   test-ddl.sh <ctx> <db> [pod]
set -uo pipefail
CTX="${1:?usage: test-ddl.sh <ctx> <db> [pod]}"; SRC="${2:?db}"; POD="${3:-hartland-pg-1}"; NS="${EXTEND_NS:-data}"
source "$(dirname "$0")/lib-test.sh"
S="${SRC}_au_ddl"

# table | columns in order (name type) | primary key
TABLES=$(cat <<'EOF'
sales_order|so_order_number integer, so_channel text, so_customer_sk integer, so_placed_date date, so_delivered_date date, so_warehouse_sk integer, so_value numeric(12,2), so_state text, so_held_for text, so_placed_by text|so_order_number
sales_line|sl_order_number integer, sl_line_no integer, sl_item_sk integer, sl_quantity integer, sl_unit_price numeric(12,2), sl_ext_sales_price numeric(12,2), sl_warehouse_sk integer, sl_sold_date date, sl_customer_sk integer, sl_channel text|sl_order_number,sl_line_no
price_list|pl_item_sk integer, pl_channel text, pl_valid_from date, pl_price numeric(12,2), pl_valid_to date|pl_item_sk,pl_channel,pl_valid_from
customer_price|cp_item_sk integer, cp_customer_sk integer, cp_valid_from date, cp_price numeric(12,2), cp_valid_to date|cp_item_sk,cp_customer_sk,cp_valid_from
invoice|inv_invoice_id integer, inv_customer_sk integer, inv_order_number integer, inv_issued date, inv_due date, inv_amount numeric(12,2), inv_paid numeric(12,2), inv_status text|inv_invoice_id
warehouse_outage|wo_warehouse_sk integer, wo_from_date date, wo_to_date date, wo_reason text|wo_warehouse_sk,wo_from_date
return_request_hdr|rr_request_number integer, rr_customer_sk integer, rr_order_number integer, rr_channel text, rr_requested_date date|rr_request_number
return_request_line|rl_line_id integer, rl_request_number integer, rl_line_no integer, rl_item_sk integer, rl_quantity integer, rl_unit_price numeric(12,2), rl_reason text, rl_requested_resolution text, rl_requested_variant_sk integer, rl_state text, rl_way text, rl_customer_sk integer|rl_line_id
return_receipt|rc_receipt_id integer, rc_line_id integer, rc_received_date date, rc_item_sk integer, rc_quantity integer, rc_condition text|rc_receipt_id
credit_note|cn_credit_note_id integer, cn_line_id integer, cn_customer_sk integer, cn_issued_date date, cn_amount numeric(12,2), cn_status text|cn_credit_note_id
refund_payment|rp_payment_id integer, rp_credit_note_id integer, rp_paid_date date, rp_amount numeric(12,2)|rp_payment_id
replacement_shipment|rs_shipment_id integer, rs_line_id integer, rs_item_sk integer, rs_quantity integer, rs_shipped_date date|rs_shipment_id
reorder_proposal|rp_proposal_id bigint, rp_run text, rp_item_sk integer, rp_warehouse_sk integer, rp_on_hand integer, rp_weekly_demand numeric(12,2), rp_proposed_qty integer, rp_state text|rp_proposal_id
winback_mail|wm_customer_sk integer, wm_quarter text, wm_offer text, wm_run text, wm_mailed_at timestamptz|wm_customer_sk,wm_quarter
EOF
)

# name | table.column → table.column  (contracts §1: the 22 + the 4 of S0.1)
FKS=$(cat <<'EOF'
fk_so_customer sales_order.so_customer_sk customer.c_customer_sk
fk_so_warehouse sales_order.so_warehouse_sk warehouse.w_warehouse_sk
fk_sl_order sales_line.sl_order_number sales_order.so_order_number
fk_sl_item sales_line.sl_item_sk item.i_item_sk
fk_sl_warehouse sales_line.sl_warehouse_sk warehouse.w_warehouse_sk
fk_sl_customer sales_line.sl_customer_sk customer.c_customer_sk
fk_pl_item price_list.pl_item_sk item.i_item_sk
fk_cp_item customer_price.cp_item_sk item.i_item_sk
fk_cp_customer customer_price.cp_customer_sk customer.c_customer_sk
fk_inv_customer invoice.inv_customer_sk customer.c_customer_sk
fk_inv_order invoice.inv_order_number sales_order.so_order_number
fk_wo_warehouse warehouse_outage.wo_warehouse_sk warehouse.w_warehouse_sk
fk_rr_customer return_request_hdr.rr_customer_sk customer.c_customer_sk
fk_rr_order return_request_hdr.rr_order_number sales_order.so_order_number
fk_rl_request return_request_line.rl_request_number return_request_hdr.rr_request_number
fk_rl_item return_request_line.rl_item_sk item.i_item_sk
fk_rl_variant return_request_line.rl_requested_variant_sk item.i_item_sk
fk_rl_customer return_request_line.rl_customer_sk customer.c_customer_sk
fk_rc_line return_receipt.rc_line_id return_request_line.rl_line_id
fk_cn_line credit_note.cn_line_id return_request_line.rl_line_id
fk_rp_credit_note refund_payment.rp_credit_note_id credit_note.cn_credit_note_id
fk_rs_line replacement_shipment.rs_line_id return_request_line.rl_line_id
fk_rp_item reorder_proposal.rp_item_sk item.i_item_sk
fk_rp_warehouse reorder_proposal.rp_warehouse_sk warehouse.w_warehouse_sk
fk_wm_customer winback_mail.wm_customer_sk customer.c_customer_sk
fk_c_center customer.c_center_sk warehouse.w_warehouse_sk
EOF
)

cols_of() { # cols_of <db> <relation> — `name type, …` in column order
  pgq "$1" "SELECT string_agg(column_name || ' ' || CASE data_type
                WHEN 'numeric' THEN format('numeric(%s,%s)', numeric_precision, numeric_scale)
                WHEN 'timestamp with time zone' THEN 'timestamptz' ELSE data_type END, ', ' ORDER BY ordinal_position)
              FROM information_schema.columns WHERE table_schema = 'public' AND table_name = '$2'"
}

echo "== DDL, on a scratch copy of $SRC ($S)"
scratch_copy "$SRC" "$S"
run_automation "$S"; rc=$?
expect "the build exits 0" "$rc" -eq 0

while IFS='|' read -r t cols pk; do
  expect "$t: columns and types as contracts §1" "$(cols_of "$S" "$t")" = "$cols"
  expect "$t: primary key ($pk)" "$(pgq "$S" "SELECT string_agg(a.attname, ',' ORDER BY k.ord)
      FROM pg_constraint c CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY k(attnum, ord)
      JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
     WHERE c.conrelid = to_regclass('public.$t') AND c.contype = 'p'")" = "$pk"
done <<< "$TABLES"

while read -r name from to; do
  expect "$name: $from → $to, validated" "$(pgq "$S" "SELECT c.conrelid::regclass || '.' || a.attname || ' ' || c.confrelid::regclass || '.' || af.attname || ' ' || c.convalidated
      FROM pg_constraint c
      JOIN pg_attribute a  ON a.attrelid = c.conrelid   AND a.attnum = c.conkey[1]
      JOIN pg_attribute af ON af.attrelid = c.confrelid AND af.attnum = c.confkey[1]
     WHERE c.contype = 'f' AND c.conname = '$name' AND cardinality(c.conkey) = 1")" = "$from $to true"
done <<< "$FKS"
expect "no other foreign key on an extension table" "$(pgq "$S" "SELECT count(*) FROM pg_constraint
    WHERE contype = 'f' AND conrelid::regclass::text IN ($(printf "'%s'," $AU_TABLES | sed 's/,$//'))")" -eq 25

expect "customer.c_center_sk added (integer)" "$(pgq "$S" "SELECT data_type FROM information_schema.columns WHERE table_name = 'customer' AND column_name = 'c_center_sk'")" = integer
expect "date_dim.d_working_day added (boolean)" "$(pgq "$S" "SELECT data_type FROM information_schema.columns WHERE table_name = 'date_dim' AND column_name = 'd_working_day'")" = boolean
expect "customer.c_email added (generated, stored)" "$(pgq "$S" "SELECT is_generated FROM information_schema.columns WHERE table_name = 'customer' AND column_name = 'c_email'")" = ALWAYS
expect "every customer has a unique reserved-domain address" "$(pgq "$S" "SELECT count(*) - count(DISTINCT c_email) + count(*) FILTER (WHERE c_email NOT LIKE 'customer-%@customers.hartland.example') FROM customer")" -eq 0
expect "view return_request: the header + the derived state" "$(cols_of "$S" return_request)" = \
  "rr_request_number integer, rr_customer_sk integer, rr_order_number integer, rr_channel text, rr_requested_date date, rr_state text"
expect "view document_flow: predecessor → successor" "$(cols_of "$S" document_flow)" = \
  "df_pred_kind text, df_pred_id integer, df_succ_kind text, df_succ_id integer"
for t in $AU_INTERNALS; do expect "internal $t exists" "$(exists "$S" "$t")" -eq 1; done

owner=$(pgq "$S" "SELECT tableowner FROM pg_tables WHERE schemaname = 'public' AND tablename = 'web_sales'")
expect "every extension table and view is owned by the facts' owner ($owner)" "$(pgq "$S" "SELECT count(*) FROM pg_class c
    WHERE c.relnamespace = 'public'::regnamespace AND c.relname IN ($(printf "'%s'," $AU_TABLES $AU_VIEWS | sed 's/,$//'))
      AND pg_get_userbyid(c.relowner) = '$owner'")" -eq 16

# The facts are already in the world's currency (CZ: localize-cz scaled them): a released line carries its
# fact's amount and the unit price it implies — never × fx again.
off=$(conf web_order_offset)
for ch in "web:web_sales:ws:$off" "marketplace:catalog_sales:cs:0"; do
  IFS=: read -r name fact p o <<<"$ch"
  expect "$name: released lines carry their fact's amount and implied unit price" "$(pgq "$S" "SELECT count(*) || ':' || count(*) FILTER (
        WHERE s.sl_ext_sales_price = f.${p}_ext_sales_price AND s.sl_unit_price = round(f.${p}_ext_sales_price / f.${p}_quantity, 2))
      FROM sales_line s JOIN sales_order o ON o.so_order_number = s.sl_order_number AND o.so_state = 'released'
      JOIN $fact f ON f.${p}_order_number + $o = s.sl_order_number AND f.${p}_item_sk = s.sl_item_sk
     WHERE s.sl_channel = '$name'" | awk -F: '$1 > 0 && $1 == $2 {print "all"; exit} {print $0}')" = all
done

drop_scratch "$S"
finish
