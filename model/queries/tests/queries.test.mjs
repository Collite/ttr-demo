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

// ── T6.9 / T6.10 — a pattern compiles the way veles compiles it ──────────────────────────────────────
// veles serves `search.patterns` through ttr-metadata's RegexAlgorithm (ttr-core
// packages/kotlin/ttr-metadata/…/search/regex/RegexAlgorithm.kt). `buildCapturingRegex` below follows it
// step for step: each `{name}` / `@name` → `(?<name>.+?)`; the text is NFD-folded and lower-cased; only
// `\ . * + ? [ ] ^ $` are escaped, so `( | )` are regex groups; and the LAST placeholder turns greedy
// only when the regex ends with it. A pattern that fails to compile is not an error anyone sees: the
// rebuild records a CompileError and serves the query without it.
const CURLY_PARAM = /\{([\w\p{L}]+)\}/gu;
const AT_PARAM = /@([\w\p{L}]+)/gu;
const fold = (s) => s.normalize('NFD').replace(/\p{M}+/gu, '').toLowerCase();
const SANITIZE = { 'č': 'c', 'ř': 'r', 'š': 's', 'ž': 'z', 'ň': 'n', 'ť': 't', 'ď': 'd', 'ů': 'u', 'ý': 'y', 'ÿ': 'y' };
const sanitizeGroupName = (name) =>
  [...name].map((ch) => {
    if (/[A-Za-z0-9]/.test(ch)) return ch;
    if (SANITIZE[ch.toLowerCase()]) return SANITIZE[ch.toLowerCase()];
    const base = ch.normalize('NFD').replace(/\p{M}+/gu, '');
    return /^[A-Za-z]$/.test(base) ? base : '';
  }).join('');

/** Every placeholder OCCURRENCE in the template, `{name}` and `@name` alike. */
const placeholders = (pattern) => [
  ...[...pattern.matchAll(CURLY_PARAM)].map((m) => m[1]),
  ...[...pattern.matchAll(AT_PARAM)].map((m) => m[1]),
];

function buildCapturingRegex(pattern) {
  const names = [...new Set(placeholders(pattern))];
  let tokenized = pattern;
  names.forEach((n, i) => {
    tokenized = tokenized.replaceAll(`{${n}}`, `paramtoken${i}paramtoken`).replaceAll(`@${n}`, `paramtoken${i}paramtoken`);
  });
  let re = fold(tokenized).replace(/[\\.*+?[\]^$]/g, (c) => `\\${c}`);
  names.forEach((n, i) => {
    re = re.replaceAll(`paramtoken${i}paramtoken`, `(?<${sanitizeGroupName(n)}>.+?)`);
  });
  if (names.length > 0) {
    const lastLazy = `(?<${sanitizeGroupName(names.at(-1))}>.+?)`;
    if (re.endsWith(lastLazy)) re = `${re.slice(0, -lastLazy.length)}(?<${sanitizeGroupName(names.at(-1))}>.+)`;
  }
  return { source: re, names };
}

/**
 * What the regex must still match after the group ending at [from]: the rest of that group's own
 * alternative, then — outwards, one enclosing group at a time — whatever follows each enclosing group.
 */
function continuationAfter(re, from) {
  const scan = (pos, stopAtBar) => {
    let depth = 0;
    for (let k = pos; k < re.length; k++) {
      const c = re[k];
      if (c === '\\') { k++; continue; }
      if (c === '(') depth++;
      else if (c === ')') { if (depth === 0) return k; depth--; }
      else if (c === '|' && depth === 0 && stopAtBar) return k;
    }
    return re.length;
  };
  let out = '';
  let pos = from;
  while (pos < re.length) {
    let k = scan(pos, true);
    out += re.slice(pos, k);
    if (k >= re.length) break;
    if (re[k] === '|') k = scan(k + 1, false); // the other alternatives of the enclosing group are not taken
    pos = k + 1; // past the enclosing group's `)`
  }
  return out;
}

test('T6.9 — every query pattern compiles the way veles compiles it: no placeholder twice, none left undelimited', () => {
  // 2026-10-14 (ttr-demo#72 review). category_revenue's cs pattern `…{channel}( v roce {year}| za rok
  // {year}|)` named the group `year` twice — java.util.regex refuses a duplicate group name even in
  // separate alternatives, so veles dropped the pattern. Its en twin `…{channel}( in {year}|)` compiled,
  // but nothing after `{channel}` was required, so the lazy capture stopped after ONE character ("w"):
  // a substring hit (0.85) where the question was matched whole.
  const problems = [];
  for (const { def } of allQueries()) {
    for (const pattern of def.search?.patterns ?? []) {
      const at = `${def.name}: ${JSON.stringify(pattern)}`;
      const groups = placeholders(pattern).map(sanitizeGroupName);
      const twice = groups.filter((g, i) => groups.indexOf(g) !== i);
      if (twice.length > 0) {
        problems.push(`${at} — group ${[...new Set(twice)].join(', ')} named twice (Java refuses it; veles drops the pattern)`);
        continue;
      }
      const { source } = buildCapturingRegex(pattern);
      try {
        new RegExp(source, 'i');
      } catch (e) {
        problems.push(`${at} — does not compile: ${e.message}`);
        continue;
      }
      for (const m of source.matchAll(/\(\?<(\w+)>\.\+\?\)/g)) {
        const rest = continuationAfter(source, m.index + m[0].length);
        if (new RegExp(`^(?:${rest})$`).test('')) {
          problems.push(`${at} — {${m[1]}} is lazy and nothing after it is required, so it captures one character`);
        }
      }
    }
  }
  assert.deepEqual(problems, [], `patterns veles would drop or match short:\n${problems.join('\n')}`);
});

test('T6.10 — category_revenue: each example is matched whole and gives its channel and year', () => {
  // veles keeps one hit per query: the best score, the FIRST pattern on a tie (1.0 = the whole question
  // matched, 0.85 = part of it). So the pattern naming both placeholders must come before the
  // channel-only one, or the greedy `{channel}` takes "web in 2025".
  const def = queryNamed('category_revenue');
  const compiled = def.search.patterns.map((p) => new RegExp(buildCapturingRegex(p).source, 'i'));
  const expected = {
    'Revenue by category for Web in 2025': { channel: 'web', year: '2025' },
    'Tržby podle kategorie pro web v roce 2025': { channel: 'web', year: '2025' },
  };
  assert.deepEqual([...def.search.examples].sort(), Object.keys(expected).sort());
  for (const [example, params] of Object.entries(expected)) {
    const needle = fold(example.trim());
    let best = null;
    for (const re of compiled) {
      const m = re.exec(needle);
      if (!m) continue;
      const score = m.index === 0 && m[0].length === needle.length ? 1.0 : 0.85;
      if (best == null || score > best.score) best = { score, groups: { ...m.groups } };
    }
    assert.ok(best, `no pattern matches ${example}`);
    assert.equal(best.score, 1.0, `${example}: matched only in part`);
    assert.deepEqual(best.groups, params, `${example}: extracted ${JSON.stringify(best.groups)}`);
  }
});
