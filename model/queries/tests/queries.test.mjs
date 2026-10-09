// Stage 2.6 T6.1 — ListQueries = 15 with declared params; no profit/cost.
// Mocked/unit: parses the whole model/ tree as one project (project-harness.mjs), no
// live DB (the 15 queries were also EXPLAIN-verified against live hartland_us ad hoc —
// see model/queries/README.md — but that's a bonus check, not part of this suite).
// Run: node --test model/queries/tests/queries.test.mjs (from the hartland repo root).

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadHartlandProject, ACCEPTED_RESIDUAL_CODES, isOwnModelFile, isSyncedModelFile } from '../../tests/project-harness.mjs';

const EXPECTED_QUERIES = [
  'channel_revenue_monthly', 'channel_revenue_yoy', 'category_revenue',
  'marketplace_revenue_by_warehouse', 'top_items_by_revenue', 'returns_by_reason',
  'returns_rate_by_channel', 'warehouse_stockout_weeks', 'inventory_on_hand_series',
  'customer_channel_overlap', 'revenue_by_customer_state', 'buyer_age_profile',
  'promo_share', 'store_sales_by_month', 'customer_running_total',
  // LR 2026-10-10 — the 16th: which months of a year fell against the prior one, for one channel
  // (the Czech demo's 3.2; the yearly per-channel query cannot say which months).
  'channel_revenue_monthly_yoy',
];

const BANNED_TOKENS = ['net_profit', 'margin', 'wholesale_cost', 'list_price', 'net_paid'];

const project = await loadHartlandProject();

/**
 * The queries THIS repo authors. ⛔ IE-P2·S2.3: `model/investment/queries/` is synced in from
 * kantheon and served beside these, so an unscoped walk turns "the D-2 roster of 15" into "however
 * many queries the tree happens to hold".
 */
function allQueries() {
  return allQueriesAnywhere().filter(({ uri }) => isOwnModelFile(uri));
}

function allQueriesAnywhere() {
  const out = [];
  for (const [uri, ast] of project.asts) {
    for (const def of ast.definitions ?? []) {
      if (def.kind === 'query') out.push({ def, uri });
    }
  }
  return out;
}

test('T6.1 — parse-clean: q_hartland.ttrm parses with zero errors', () => {
  const errors = project.parseErrorsByFile.get('model/queries/q_hartland.ttrm');
  assert.ok(errors !== undefined, 'file not found by the harness');
  assert.deepEqual(errors, [], `parse errors: ${JSON.stringify(errors)}`);
});

test('T6.2 — ListQueries = 16, exactly the D-2 roster + LR\'s monthly YoY, each with typed+labeled params', () => {
  const queries = allQueries();
  const names = queries.map(({ def }) => def.name);
  assert.deepEqual([...names].sort(), [...EXPECTED_QUERIES].sort());
  assert.equal(queries.length, 16);
  for (const { def } of queries) {
    for (const p of def.parameters ?? []) {
      assert.ok(p.type, `${def.name}.${p.name} has no type`);
      assert.ok(p.label, `${def.name}.${p.name} has no label`);
    }
    assert.equal(def.language, 'SQL', `${def.name}: language must be SQL`);
    assert.ok(def.sourceText?.value?.length > 0, `${def.name}: empty sourceText`);
  }
});

test('T6.3 — year params default range 2021-2026 is documented (spot-check labels mention year)', () => {
  const yearParamNames = new Set(['year', 'year_from', 'year_to', 'prior_year']);
  const queries = allQueries();
  let sawYearParam = false;
  for (const { def } of queries) {
    for (const p of def.parameters ?? []) {
      if (yearParamNames.has(p.name)) {
        sawYearParam = true;
        assert.equal(p.type?.name, 'int', `${def.name}.${p.name} should be int`);
      }
    }
  }
  assert.ok(sawYearParam, 'expected at least one year-shaped param across the 15 queries');
});

test('T6.4 — no profit/cost/margin token anywhere in the queries file', () => {
  const offenders = [];
  for (const { def, uri } of allQueries()) {
    const text = def.sourceText?.value ?? '';
    for (const token of BANNED_TOKENS) {
      if (text.toLowerCase().includes(token)) offenders.push(`${uri}: ${def.name} contains '${token}'`);
    }
  }
  assert.deepEqual(offenders, [], `banned tokens found: ${offenders.join('; ')}`);
});

test('T6.5 — no unexpected diagnostics from the queries file (project-wide sweep still clean)', () => {
  const codes = project.diagnosticsByFile.get('model/queries/q_hartland.ttrm') ?? new Set();
  const real = [...codes].filter((c) => !ACCEPTED_RESIDUAL_CODES.has(c));
  assert.deepEqual(real, [], `unexpected diagnostics: ${real.join(', ')}`);
});

test('T6.6 — no query carries the legacy `search { keywords }` sub-block (RS-32)', () => {
  // ⛔ FIXED at IE-P2·S2.3 (found at S2.2·D2). This assertion said `keywords` and tested
  // `def.search != null` — so it forbade the ENTIRE `search` block, including the
  // `patterns:`/`examples:` form all 15 queries here carry and which is how the running golem
  // discovers them. It has been RED on master since the toolchain bump, asserting the opposite of
  // what this estate deliberately does, and a red assertion nobody can satisfy stops being read.
  //
  // What RS-32 actually deprecated in a way this repo can act on is `search { keywords { … } }`,
  // the locale-keyed sub-block that moved onto lexicon `term` entries. The outer form is
  // deprecated too — `ttr/lexicon-legacy-patterns` — and is ACCEPTED, not fixed, in the harness's
  // residual list, with the reason: moving the patterns would take every q.hartland.* out of
  // discovery at once, on the estate that is the live demo.
  const withKeywords = allQueriesAnywhere()
    .filter(({ def }) => def.search?.keywords != null)
    .map(({ def }) => def.name);
  assert.deepEqual(withKeywords, [], `queries carrying legacy search{keywords}: ${withKeywords.join(', ')}`);

  // And the positive half, which is the part that would actually break the demo: every query the
  // estate serves still HAS a search block for the golem to match on.
  const without = allQueriesAnywhere().filter(({ def }) => def.search == null).map(({ def }) => def.name);
  assert.deepEqual(without, [], `queries with no search block at all — undiscoverable: ${without.join(', ')}`);
});

test('T6.7 — the synced investment package brings its twenty-one, and they are not counted as ours', () => {
  // Nine since IE-P3·S3.1: `period_values` (the report's per-period program, ⚑IE-15 (a)) and
  // `portfolio_header` joined the seven. Nineteen since IA-P3·S3.1: the ten Browse programs
  // (kantheon contracts IA-C35 … IA-C42); twenty since IA-P3·S3.3 (`clients_list`); twenty-one since IA-P4·S4.1
  // (`conversion_rates`, the period evolution's rates).
  const synced = allQueriesAnywhere().filter(({ uri }) => isSyncedModelFile(uri)).map(({ def }) => def.name);
  assert.equal(synced.length, 21, `the 21 q.investment.* programs, got ${synced.length}: ${synced.join(', ')}`);
  assert.ok(!synced.some((n) => EXPECTED_QUERIES.includes(n)), 'a name collides with the D-2 roster');
  assert.equal(allQueries().length + synced.length, allQueriesAnywhere().length, 'every query is one or the other');
});
