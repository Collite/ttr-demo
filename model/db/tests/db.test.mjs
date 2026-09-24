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
const EXPECTED_TABLES = [...EXPECTED_FACT_TABLES, ...EXPECTED_DIM_TABLES];

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
