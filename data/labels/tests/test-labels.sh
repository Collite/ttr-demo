#!/usr/bin/env bash
# The label retype's suite, on a throwaway local Postgres (data/automation/tests/pg-local.sh — no Docker, no cluster).
# It builds the five tables with dsdgen's CHAR columns and padded values — labels, a code that fills its width, a
# flag — retypes them, and checks: the labels VARCHAR of their width with no blank left, the codes and flags still
# CHAR, a second run a no-op, and a world it cannot retype (a view on a label, a missing column) left as it was.
#
#   tests/test-labels.sh          `just labels-test`
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DIR="$(cd "$HERE/.." && pwd)"
# shellcheck source=../../automation/tests/pg-local.sh
source "$DIR/../automation/tests/pg-local.sh"
pg_local_start || exit 1
trap pg_local_stop EXIT
# shellcheck source=../../extend/tests/lib-test.sh
source "$DIR/../extend/tests/lib-test.sh"

createdb lab || exit 1
pg lab -q -f - <<'SQL'
CREATE TABLE item (i_item_sk int PRIMARY KEY, i_item_id char(16), i_product_name char(50), i_brand char(50),
                   i_class char(50), i_category char(50), i_manufact char(50), i_size char(20), i_container char(10));
CREATE TABLE reason (r_reason_sk int PRIMARY KEY, r_reason_id char(16), r_reason_desc char(100));
CREATE TABLE promotion (p_promo_sk int PRIMARY KEY, p_promo_id char(16), p_promo_name char(50));
CREATE TABLE household_demographics (hd_demo_sk int PRIMARY KEY, hd_buy_potential char(15));
CREATE TABLE date_dim (d_date_sk int PRIMARY KEY, d_day_name char(9), d_holiday char(1));
INSERT INTO item VALUES (1, 'AAAAAAAABAAAAAAA', 'Ashgrove Parfém MX-15X', 'Ashgrove', 'accent', 'Books', 'Ashgrove Studio', 'L', 'Blistr'),
                        (2, 'AAAAAAAACAAAAAAA', NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO reason VALUES (1, 'AAAAAAAABAAAAAAA', 'Balík byl poškozen');
INSERT INTO promotion VALUES (1, 'AAAAAAAABAAAAAAA', 'able');
INSERT INTO household_demographics VALUES (1, '0-500');
INSERT INTO date_dim VALUES (1, 'Friday', 'N'), (2, 'Wednesday', 'Y');
SQL
pgq postgres "CREATE DATABASE lab_view TEMPLATE lab" >/dev/null
pgq postgres "CREATE DATABASE lab_missing TEMPLATE lab" >/dev/null

types() { # types <db> — table.column:type(len) of every column of the five tables, sorted
  pgq "$1" "SELECT string_agg(table_name || '.' || column_name || ':' || data_type || '(' || coalesce(character_maximum_length::text, '') || ')', ' ' ORDER BY table_name, column_name)
            FROM information_schema.columns WHERE table_schema = 'public' AND data_type IN ('character', 'character varying')
              AND table_name IN ('item', 'reason', 'promotion', 'household_demographics', 'date_dim')"
}
padded() { # padded <db> — label values with a trailing blank
  pgq "$1" "SELECT (SELECT count(*) FROM item WHERE i_category <> rtrim(i_category) OR i_size <> rtrim(i_size) OR i_container <> rtrim(i_container))
             + (SELECT count(*) FROM reason WHERE r_reason_desc <> rtrim(r_reason_desc))
             + (SELECT count(*) FROM date_dim WHERE d_day_name <> rtrim(d_day_name))"
}
fp() { pgq "$1" "SELECT md5(string_agg(x::text, '|' ORDER BY i_item_sk)) FROM item x"; }
run() { bash "$DIR/run-labels.sh" local "$1" - 2>&1; }

echo "== as dsdgen declares it"
expect "a CHAR label reads padded" "$(pgq lab "SELECT length(i_category::text) || ' ' || octet_length(i_category) FROM item WHERE i_item_sk = 1")" = "5 50"
expect "the category reaches a client with its blanks" "$(pgq lab "SELECT '[' || i_category || ']' FROM item WHERE i_item_sk = 1" | wc -c)" -eq 8
before_types="$(types lab)"

echo "== the retype"
out="$(run lab)"; rc=$?
expect "run-labels.sh exits 0" "$rc" -eq 0
expect "one ALTER per table (5 tables)" "$(grep -c 'now VARCHAR' <<<"$out")" -eq 5
expect "the labels are VARCHAR of their width, the codes and the flag stay CHAR" "$(types lab)" = \
  "date_dim.d_day_name:character varying(9) date_dim.d_holiday:character(1) household_demographics.hd_buy_potential:character varying(15) item.i_brand:character varying(50) item.i_category:character varying(50) item.i_class:character varying(50) item.i_container:character varying(10) item.i_item_id:character(16) item.i_manufact:character varying(50) item.i_product_name:character varying(50) item.i_size:character varying(20) promotion.p_promo_id:character(16) promotion.p_promo_name:character varying(50) reason.r_reason_desc:character varying(100) reason.r_reason_id:character(16)"
expect "no label keeps a trailing blank" "$(padded lab)" -eq 0
expect "the values are the same words" "$(pgq lab "SELECT i_category || '|' || i_size || '|' || i_container || '|' || r_reason_desc FROM item, reason WHERE i_item_sk = 1")" = "Books|L|Blistr|Balík byl poškozen"
expect "a NULL stays NULL" "$(pgq lab "SELECT count(*) FROM item WHERE i_item_sk = 2 AND i_category IS NULL AND i_size IS NULL")" -eq 1
expect "a code is untouched" "$(pgq lab "SELECT i_item_id FROM item WHERE i_item_sk = 1")" = "AAAAAAAABAAAAAAA"

echo "== a second run"
before="$(fp lab)"; types_after="$(types lab)"
out="$(run lab)"; rc=$?
expect "a second run exits 0" "$rc" -eq 0
expect "a second run alters nothing" "$(grep -c 'now VARCHAR' <<<"$out")" -eq 0
expect "a second run leaves item byte-identical" "$(fp lab)" = "$before"
expect "a second run leaves the types" "$(types lab)" = "$types_after"

echo "== a world it cannot retype is left as it was"
pg lab_view -q -c "CREATE VIEW item_labels AS SELECT i_item_sk, i_category FROM item"
out="$(run lab_view)"; rc=$?
expect "a view on a label: run-labels.sh fails" "$rc" -ne 0
expect "… and rolls every table back (one transaction)" "$(types lab_view)" = "$before_types"
pg lab_missing -q -c "ALTER TABLE promotion DROP COLUMN p_promo_name"
out="$(run lab_missing)"; rc=$?
expect "a missing label column: run-labels.sh fails" "$rc" -ne 0
expect "… naming it" "$(grep -c 'no such text column: promotion.p_promo_name' <<<"$out")" -ge 1
expect "… and retypes nothing" "$(pgq lab_missing "SELECT data_type FROM information_schema.columns WHERE table_name = 'item' AND column_name = 'i_category'")" = "character"
out="$(bash "$DIR/run-labels.sh" local tpc-ds-1g - 2>&1)"; rc=$?
expect "tpc-ds-1g is refused" "$rc" -eq 2

finish
