// Stage 2.1 T6 — model-load / resolution unit tests (mocked: parse from the committed
// .ttrm files, no live DB). Uses Node's built-in test runner (`node --test`) so the
// content-only hartland repo needs no package.json / node_modules of its own — it
// borrows the built @tatrman/parser from the sibling tatrman checkout (collite-gh/*
// convention: both repos live side by side).
//
// Run: node --test model/db/tests/db.test.mjs   (from the hartland repo root)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const hartlandRoot = path.resolve(here, '../../..');
const dbDir = path.resolve(hartlandRoot, 'model/db');
const tatrmanPackages = process.env.TATRMAN_PACKAGES ?? path.resolve(hartlandRoot, '../tatrman/packages');
const tatrmanParserDist = path.join(tatrmanPackages, 'parser/dist/index.js');

const { parseString } = await import(tatrmanParserDist);

// D-5 entity roster (05-d-ttrm-spec.md) — the demo subset every db file must model.
const EXPECTED_FACT_TABLES = [
  'store_sales', 'web_sales', 'catalog_sales',
  'store_returns', 'web_returns', 'catalog_returns',
  'inventory',
];
const EXPECTED_DIM_TABLES = [
  'date_dim', 'item', 'customer', 'customer_address',
  'customer_demographics', 'household_demographics', 'income_band',
  'store', 'warehouse', 'promotion', 'reason', 'call_center',
];
// AU (automation agents) S0.1 — the H-1/H-2 extension (orders.ttrm, returns-flow.ttrm); their shape is
// asserted by model/tests/automation-extension.test.mjs, this roster only keeps the count exact.
const EXPECTED_AU_TABLES = [
  'sales_order', 'sales_line', 'price_list', 'customer_price', 'invoice', 'warehouse_outage',
  'reorder_proposal', 'winback_mail',
  'return_request_hdr', 'return_request_line', 'return_receipt', 'credit_note', 'refund_payment',
  'replacement_shipment',
];
const EXPECTED_TABLES = [...EXPECTED_FACT_TABLES, ...EXPECTED_DIM_TABLES, ...EXPECTED_AU_TABLES];

// D-6a — deliberately excluded profit/cost/list-price/discount-internal columns.
const BANNED_COLUMN_SUBSTRINGS = [
  'net_profit', 'net_paid', 'wholesale_cost', 'list_price',
  'ext_wholesale_cost', 'ext_list_price', 'ext_discount_amt', 'ext_tax',
  'ext_ship_cost', 'coupon_amt', '_fee', 'return_ship_cost', 'refunded_cash',
  'reversed_charge', 'store_credit', 'account_credit', 'net_loss',
  'return_tax', 'return_amt_inc_tax',
];

async function ttrmFiles(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  return entries.filter((e) => e.isFile() && e.name.endsWith('.ttrm')).map((e) => path.join(dir, e.name));
}

async function parseAll(files) {
  const parsed = [];
  for (const file of files) {
    const content = await readFile(file, 'utf-8');
    const result = parseString(content, `file://${file}`);
    parsed.push({ file, result });
  }
  return parsed;
}

test('T6.1 — parse-clean: every model/db/*.ttrm file parses with zero errors', async () => {
  const files = await ttrmFiles(dbDir);
  assert.ok(files.length >= 3, `expected facts/dims/fks, found ${files.length}`);
  const parsed = await parseAll(files);
  for (const { file, result } of parsed) {
    assert.deepEqual(result.errors, [], `${path.basename(file)} parse errors: ${JSON.stringify(result.errors)}`);
  }
});

test('T6.2 — schema completeness: every D-5 fact/dim table is declared', async () => {
  const files = await ttrmFiles(dbDir);
  const parsed = await parseAll(files);
  const tableNames = new Set();
  for (const { result } of parsed) {
    for (const def of result.ast?.definitions ?? []) {
      if (def.kind === 'table') tableNames.add(def.name);
    }
  }
  const missing = EXPECTED_TABLES.filter((t) => !tableNames.has(t));
  assert.deepEqual(missing, [], `missing tables: ${missing.join(', ')}`);
  assert.equal(tableNames.size, EXPECTED_TABLES.length, `expected exactly ${EXPECTED_TABLES.length} tables, got ${tableNames.size}: ${[...tableNames].join(', ')}`);
});

test('T6.3 — every table declares a primaryKey', async () => {
  const files = await ttrmFiles(dbDir);
  const parsed = await parseAll(files);
  const withoutPk = [];
  for (const { result } of parsed) {
    for (const def of result.ast?.definitions ?? []) {
      if (def.kind !== 'table') continue;
      if (!Array.isArray(def.primaryKey) || def.primaryKey.length === 0) withoutPk.push(def.name);
    }
  }
  assert.deepEqual(withoutPk, [], `tables missing primaryKey: ${withoutPk.join(', ')}`);
});

test('T6.4 — every def fk from/to column resolves to a declared table.column or view.column', async () => {
  const files = await ttrmFiles(dbDir);
  const parsed = await parseAll(files);

  // table/view -> Set(column names). A view (views.ttrm) carries no constraints in the database,
  // but the model may declare logical keys on its columns — the same joins its source tables carry.
  const columnsByTable = new Map();
  for (const { result } of parsed) {
    for (const def of result.ast?.definitions ?? []) {
      if (def.kind !== 'table' && def.kind !== 'view') continue;
      columnsByTable.set(def.name, new Set((def.columns ?? []).map((c) => c.name)));
    }
  }

  function refTableColumn(idNode) {
    const parts = idNode.parts; // e.g. ['db','dbo','store_sales','ss_item_sk']
    return { table: parts[parts.length - 2], column: parts[parts.length - 1] };
  }

  const dangling = [];
  let fkCount = 0;
  for (const { result } of parsed) {
    for (const def of result.ast?.definitions ?? []) {
      if (def.kind !== 'fk') continue;
      fkCount++;
      for (const [label, list] of [['from', def.from], ['to', def.to]]) {
        for (const idNode of list?.items ?? []) {
          const { table, column } = refTableColumn(idNode);
          const cols = columnsByTable.get(table);
          if (!cols || !cols.has(column)) {
            dangling.push(`${def.name}.${label}: ${table}.${column}`);
          }
        }
      }
    }
  }
  assert.ok(fkCount > 0, 'expected at least one def fk');
  assert.deepEqual(dangling, [], `dangling fk refs: ${dangling.join('; ')}`);
});

test('T6.5 — no profit/cost/discount-internal column reachable (D-6a)', async () => {
  const files = await ttrmFiles(dbDir);
  const parsed = await parseAll(files);
  const offenders = [];
  for (const { file, result } of parsed) {
    for (const def of result.ast?.definitions ?? []) {
      if (def.kind !== 'table') continue;
      for (const col of def.columns ?? []) {
        if (BANNED_COLUMN_SUBSTRINGS.some((banned) => col.name.includes(banned))) {
          offenders.push(`${path.basename(file)}: ${col.name}`);
        }
      }
    }
  }
  assert.deepEqual(offenders, [], `profit/cost columns leaked into the model: ${offenders.join(', ')}`);
});

// LR C-5·4 (⚑LR-9) — validate's DC-scope policy (olymp `apps/validate` configFragment) filters each
// of these relations on its OWN distribution-centre column. A predicate on a column the model does
// not declare is one no reader of the model can explain, so each is declared here, with the fk that
// says what it means. ttr-server's HartlandScopeFragmentSpec holds the same five names.
const DC_SCOPED = {
  inventory: 'inv_warehouse_sk',
  warehouse: 'w_warehouse_sk',
  catalog_sales: 'cs_warehouse_sk',
  web_sales: 'ws_warehouse_sk',
  channel_sales: 'warehouse_sk',
};

test('LR ⚑LR-9 — every DC-scoped relation declares the column the DC-scope policy filters on, joined to warehouse', async () => {
  const parsed = await parseAll(await ttrmFiles(dbDir));
  const columnsByTable = new Map();
  const fkTo = new Map(); // "table.column" -> "table.column"
  const last2 = (idNode) => idNode.parts.slice(-2).join('.');
  for (const { result } of parsed) {
    for (const def of result.ast?.definitions ?? []) {
      if (def.kind === 'table' || def.kind === 'view') {
        columnsByTable.set(def.name, new Set((def.columns ?? []).map((c) => c.name)));
      }
      if (def.kind === 'fk' && def.from?.items?.length === 1) fkTo.set(last2(def.from.items[0]), last2(def.to.items[0]));
    }
  }
  const missing = [];
  const unjoined = [];
  for (const [table, column] of Object.entries(DC_SCOPED)) {
    if (!columnsByTable.get(table)?.has(column)) missing.push(`${table}.${column}`);
    if (table !== 'warehouse' && fkTo.get(`${table}.${column}`) !== 'warehouse.w_warehouse_sk') unjoined.push(`${table}.${column}`);
  }
  assert.deepEqual(missing, [], `DC columns the model does not declare: ${missing.join(', ')}`);
  assert.deepEqual(unjoined, [], `DC columns with no fk to warehouse: ${unjoined.join(', ')}`);
});

// The view's model columns ARE the script's (data/views/channel_sales.sql), in the script's order.
// Order matters twice: `definitionSql` mirrors the script, and Postgres' CREATE OR REPLACE VIEW can
// only APPEND columns — a new one anywhere but last makes the script fail on a world that has the view.
test('channel_sales — the model view declares the script\'s columns in the script\'s order', async () => {
  const sql = await readFile(path.resolve(hartlandRoot, 'data/views/channel_sales.sql'), 'utf-8');
  const firstBranch = sql.slice(sql.indexOf('CREATE OR REPLACE VIEW public.channel_sales AS'), sql.indexOf('UNION ALL'));
  const scriptColumns = [...firstBranch.matchAll(/\bAS\s+(\w+)\s*(?:,|\n\s*FROM)/g)].map((m) => m[1]);

  const parsed = await parseAll([path.join(dbDir, 'views.ttrm')]);
  const view = parsed[0].result.ast.definitions.find((d) => d.kind === 'view' && d.name === 'channel_sales');
  assert.deepEqual(view.columns.map((c) => c.name), scriptColumns);
  assert.equal(scriptColumns.at(-1), 'warehouse_sk', 'warehouse_sk (⚑LR-9) is appended LAST');
  assert.match(firstBranch, /NULL::int\s+AS\s+warehouse_sk/, 'a store line carries no distribution centre');
});

// BI-4 · C-24 (⚑BI-4-B, Bora 2026-10-22). Postgres returns a CHAR(n) value blank-padded to n, so every CHAR column a
// label is read from reached Superset, JDBC and Iris as `'Books' + 45 blanks`. The translator cannot trim it in the er
// mapping (an expression-bound attribute is not mapped yet), so the label columns are VARCHAR in both worlds' databases
// (data/labels/labels.sql retypes them, trimming) and here. The codes and flags stay CHAR: a code fills its width, a
// flag is one letter, so neither is padded.
const LABEL_COLUMNS = {
  'item.i_product_name': 50, 'item.i_brand': 50, 'item.i_class': 50, 'item.i_category': 50,
  'item.i_manufact': 50, 'item.i_size': 20, 'item.i_container': 10,
  'reason.r_reason_desc': 100, 'promotion.p_promo_name': 50,
  'household_demographics.hd_buy_potential': 15, 'date_dim.d_day_name': 9,
};
const CHAR_KEPT = [
  'item.i_item_id', 'customer.c_customer_id', 'customer_address.ca_address_id', 'customer_address.ca_state',
  'customer_demographics.cd_gender', 'customer_demographics.cd_marital_status', 'store.s_store_id', 'store.s_state',
  'warehouse.w_warehouse_id', 'warehouse.w_state', 'promotion.p_promo_id', 'reason.r_reason_id',
  'call_center.cc_call_center_id', 'date_dim.d_holiday', 'date_dim.d_weekend',
];

test('C-24 — the label columns are VARCHAR of their CHAR width, the codes and flags stay CHAR, and labels.sql retypes exactly the labels', async () => {
  const parsed = await parseAll([path.join(dbDir, 'dims.ttrm')]);
  const columns = new Map();
  for (const def of parsed[0].result.ast.definitions ?? []) {
    if (def.kind !== 'table') continue;
    for (const c of def.columns ?? []) columns.set(`${def.name}.${c.name}`, c.type);
  }
  const shape = (t) => (t?.kind === 'structured' ? `${t.typeName}(${t.length})` : t?.name);
  assert.deepEqual(
    Object.keys(LABEL_COLUMNS).map((k) => [k, shape(columns.get(k))]),
    Object.entries(LABEL_COLUMNS).map(([k, n]) => [k, `varchar(${n})`]),
  );
  const chars = [...columns].filter(([, t]) => shape(t)?.startsWith('char(')).map(([k]) => k);
  assert.deepEqual(chars.sort(), [...CHAR_KEPT].sort(), 'a CHAR column that is neither a code nor a flag would be padded');

  const sql = await readFile(path.resolve(hartlandRoot, 'data/labels/labels.sql'), 'utf-8');
  const listed = Object.fromEntries([...sql.matchAll(/\('(\w+)',\s*'(\w+)',\s*(\d+)\)/g)].map(([, t, c, n]) => [`${t}.${c}`, Number(n)]));
  assert.deepEqual(listed, LABEL_COLUMNS, 'labels.sql retypes another set of columns than the model declares VARCHAR');
});
