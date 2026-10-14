// Stage 2.6 T6.1 — ListQueries = 15 with declared params; no profit/cost.
// Mocked/unit: parses the whole model/ tree as one project (project-harness.mjs), no
// live DB (the 15 queries were also EXPLAIN-verified against live hartland_us ad hoc —
// see model/queries/README.md — but that's a bonus check, not part of this suite).
// Run: node --test model/queries/tests/queries.test.mjs (from the hartland repo root).

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import { loadHartlandProject, ACCEPTED_RESIDUAL_CODES, hartlandRoot } from '../../tests/project-harness.mjs';

// js-yaml borrowed from the tatrman checkout the harness reads (TATRMAN_PACKAGES, else the sibling),
// exactly as agents/tests/shems.test.mjs borrows it — for T6.8's routing cases.
const tatrmanPackages = process.env.TATRMAN_PACKAGES ?? path.resolve(hartlandRoot, '../tatrman/packages');
const yaml = await import(
  path.resolve(tatrmanPackages, '../node_modules/.pnpm/js-yaml@4.1.1/node_modules/js-yaml/dist/js-yaml.mjs')
);

const EXPECTED_QUERIES = [
  'channel_revenue_monthly', 'channel_revenue_yoy', 'category_revenue',
  'marketplace_revenue_by_warehouse', 'top_items_by_revenue', 'returns_by_reason',
  'returns_rate_by_channel', 'warehouse_stockout_weeks', 'inventory_on_hand_series',
  'customer_channel_overlap', 'revenue_by_customer_state', 'buyer_age_profile',
  'promo_share', 'store_sales_by_month', 'customer_running_total',
  // LR 2026-10-10 — the 16th: which months of a year fell against the prior one, for one channel
  // (the Czech demo's 3.2; the yearly per-channel query cannot say which months).
  'channel_revenue_monthly_yoy',
  // LR ruling 1 (2026-10-11) — the 17th: how many weeks one DC was out of stock (the Czech demo's 3.5).
  'warehouse_stockout_week_count',
];

const BANNED_TOKENS = ['net_profit', 'margin', 'wholesale_cost', 'list_price', 'net_paid'];

const project = await loadHartlandProject();

function allQueries() {
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

test('T6.2 — ListQueries = 17, exactly the D-2 roster + LR\'s monthly YoY + stockout-week count, each with typed+labeled params', () => {
  const queries = allQueries();
  const names = queries.map(({ def }) => def.name);
  assert.deepEqual([...names].sort(), [...EXPECTED_QUERIES].sort());
  assert.equal(queries.length, 17);
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
  const withKeywords = allQueries()
    .filter(({ def }) => def.search?.keywords != null)
    .map(({ def }) => def.name);
  assert.deepEqual(withKeywords, [], `queries carrying legacy search{keywords}: ${withKeywords.join(', ')}`);

  // And the positive half, which is the part that would actually break the demo: every query the
  // estate serves still HAS a search block for the golem to match on.
  const without = allQueries().filter(({ def }) => def.search == null).map(({ def }) => def.name);
  assert.deepEqual(without, [], `queries with no search block at all — undiscoverable: ${without.join(', ')}`);
});

function queryNamed(name) {
  const hit = allQueries().find(({ def }) => def.name === name);
  assert.ok(hit, `no query ${name}`);
  return hit.def;
}

/** Lower-cased words, Unicode-aware (`tržiště` is one word, `(drop|decline)` is two). */
const words = (s) => s.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter(Boolean);

test('T6.7 — category_revenue: every example names a channel and a year; no example or pattern promises a drop or a half-year', () => {
  // 2026-10-14. The query answers revenue per category for ONE channel in ONE whole year — `{channel,
  // year}`, both required, one row per category, the largest first. Its examples were "Which categories
  // drove the H2 2025 drop?" / „Které kategorie způsobily propad v 2. pol. 2025?“: a drop it does not
  // compute, a half-year it cannot take, and a premise false in both worlds (H2 2025 ≈ 2.3× H1). Asked
  // live, the estate refused or asked back instead of answering. And golem shows a query's FIRST example
  // as a follow-up chip, verbatim, so an example is a question the estate suggests to the user.
  const def = queryNamed('category_revenue');
  const examples = def.search?.examples ?? [];
  const patterns = def.search?.patterns ?? [];
  assert.ok(examples.length >= 2, 'category_revenue needs an en and a cs example');
  assert.ok(patterns.length >= 1, 'category_revenue needs a pattern, or veles stops serving it as a pattern query');

  const CHANNEL = new Set(['web', 'webu', 'marketplace', 'tržiště', 'tržišti', 'store', 'stores', 'prodejna', 'prodejny', 'prodejen']);
  for (const ex of examples) {
    const w = words(ex);
    assert.ok(w.some((x) => CHANNEL.has(x)), `example names no channel (the query takes one, required): ${ex}`);
    assert.ok(w.some((x) => /^\d{4}$/.test(x)), `example names no year (the query takes one whole year, required): ${ex}`);
  }

  const PROMISES = new Set([
    'drop', 'drops', 'dropped', 'decline', 'declined', 'drove', 'caused', 'fell',
    'propad', 'propadu', 'pokles', 'poklesu', 'způsobily', 'zpusobily', 'zapříčinily', 'zapricinily',
    'h1', 'h2', 'half', 'pol', 'pololetí', 'pololeti',
  ]);
  for (const s of [...examples, ...patterns]) {
    const hits = words(s).filter((x) => PROMISES.has(x));
    assert.deepEqual(hits, [], `promises a drop or a half-year the query does not compute: ${s}`);
  }
});

test('T6.8 — every pattern case of the routing corpus asks one of its saved query\'s own examples, cs and en', async () => {
  // run-set/routing `p-*`: "one example question per saved query". The case and the examples move
  // together — a changed example with a stale case measures a question the model no longer suggests.
  const dir = path.join(hartlandRoot, 'run-set/routing/cases');
  const files = (await readdir(dir)).filter((f) => f.startsWith('p-') && f.endsWith('.case.yaml')).sort();
  assert.ok(files.length > 0, `no p-*.case.yaml under ${dir}`);
  const misses = [];
  for (const f of files) {
    const c = yaml.load(await readFile(path.join(dir, f), 'utf-8'));
    const tag = (c.tags ?? []).find((t) => t.startsWith('q.hartland.'));
    assert.ok(tag, `${f}: no q.hartland.* tag names its saved query`);
    const examples = queryNamed(tag.slice('q.hartland.'.length)).search?.examples ?? [];
    for (const loc of ['cs', 'en']) {
      if (!examples.includes(c.question?.[loc])) misses.push(`${f} ${loc}: ${JSON.stringify(c.question?.[loc])}`);
    }
  }
  assert.deepEqual(misses, [], `cases asking a question that is not one of their query's examples:\n${misses.join('\n')}`);
});
