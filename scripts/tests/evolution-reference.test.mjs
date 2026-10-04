// IA-P4·S4.2·T5 — `scripts/sql/evolution-reference.sql` RUN on PostgreSQL 16 against the hand fixture, and held to the
// hand answers (kantheon's `expected-average.csv`) and to the saved answers the fingerprint suite reads.
//
// Run: just verify-evolution-reference           (starts PG16, loads the fixture, runs this file)
//      just verify-evolution-reference --write   (…and rewrites fixtures/evolution/reference-*.csv)
//
// It does NOT skip without a database: a reference that has never run reports nothing (the conformance suites' rule).
// With no EVOLUTION_REF_DSN every test FAILS and names the recipe.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const FIX = path.resolve(here, 'fixtures/evolution');
const SQL = path.resolve(here, '../sql/evolution-reference.sql');
const ENGINE = path.resolve(here, '../lib/evolution_fingerprint.py');
const DSN = process.env.EVOLUTION_REF_DSN;
const WRITE = process.env.EVOLUTION_REF_WRITE === '1';

/** The cases `evolution-fingerprint.test.mjs` compares the renderer's workbooks with. */
const SAVED = {
  'conseq:200900001/month': 'reference-200900001-month.csv',
  'conseq:200900002/quarter': 'reference-200900002-quarter.csv',
};

const book = JSON.parse(readFileSync(path.join(FIX, 'fixture-ledger.json'), 'utf8'));
const P1 = book.portfolios[0].portfolio_id;
const P2 = book.portfolios[1].portfolio_id;
// IA-P4 review R3 · R9: a book of its own (same-day movements; a holding deemed with no opening price), loaded beside
// the main one — its own portfolios, instruments and client, the same home currency
const cases = JSON.parse(readFileSync(path.join(FIX, 'fixture-cases.json'), 'utf8'));

const q = (v) => (v === null || v === undefined ? 'NULL' : `'${String(v).replace(/'/g, "''")}'`);
const n = (v) => (v === null || v === undefined ? 'NULL' : String(v));

/** A fixture as INSERTs into `book-schema.sql`'s six tables — the book the hand answers were worked from. */
function bookSql(b = book, { estate = true } = {}) {
  const out = estate ? [`INSERT INTO investment_estate_setting (home_currency) VALUES (${q(b.home_currency)});`] : [];
  for (const p of b.portfolios) {
    out.push(`INSERT INTO investment_portfolio_setting VALUES (${q(p.portfolio_id)}, ${q(p.reporting_currency)});`);
    for (const [isin, units] of Object.entries(p.valuation?.units ?? {})) {
      out.push(
        `INSERT INTO investment_position (portfolio_ref, asset_ref, valuation_date, quantity, valid_from) VALUES ` +
          `(${q(p.portfolio_id)}, ${q(isin)}, ${q(p.valuation.valuation_date)}, ${n(units)}, ${q(p.valuation.valuation_date)});`,
      );
    }
  }
  for (const r of b.rates) out.push(`INSERT INTO investment_fx_rate VALUES (${q(r.currency)}, ${q(r.rate_date)}, ${n(r.rate)}, ${n(r.units)});`);
  for (const r of b.prices) out.push(`INSERT INTO investment_asset_price VALUES (${q(r.isin)}, ${q(r.price_date)}, ${n(r.price)}, ${q(r.currency)});`);
  for (const m of b.movements) {
    out.push(
      'INSERT INTO investment_transaction (external_id, portfolio_ref, asset_ref, leg, operation, trade_date, quantity, amount, currency, reversal_of) ' +
        `VALUES (${q(m.external_id)}, ${q(m.portfolio)}, ${q(m.isin)}, ${q(m.leg)}, ${q(m.operation)}, ${q(m.trade_date)}, ${n(m.quantity)}, ${n(m.amount)}, ${q(m.currency)}, ${q(m.reversal_of)});`,
    );
  }
  return out.join('\n');
}

function ready() {
  assert.ok(DSN, 'EVOLUTION_REF_DSN is not set — run `just verify-evolution-reference`, which starts PostgreSQL 16, loads the fixture and re-runs this file');
}

function reference(portfolio, grain, window = book.window) {
  return execFileSync(
    'psql',
    [DSN, '-X', '-q', '--csv', '-v', 'ON_ERROR_STOP=1', '-v', `portfolio=${portfolio}`, '-v', `from=${window.from}`, '-v', `as_of=${window.as_of}`, '-v', `grain=${grain}`, '-f', SQL],
    { encoding: 'utf8' },
  );
}

const engine = (...args) => {
  try {
    return { code: 0, out: execFileSync('python3', [ENGINE, ...args], { encoding: 'utf8' }) };
  } catch (e) {
    return { code: e.status, out: `${e.stdout ?? ''}${e.stderr ?? ''}` };
  }
};

test('the fixture book loads into an empty schema', () => {
  ready();
  const psql = (sql) => execFileSync('psql', [DSN, '-X', '-q', '-v', 'ON_ERROR_STOP=1', '-c', sql], { encoding: 'utf8' });
  psql('DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;');
  execFileSync('psql', [DSN, '-X', '-q', '-v', 'ON_ERROR_STOP=1', '-f', path.join(FIX, 'book-schema.sql')]);
  execFileSync('psql', [DSN, '-X', '-q', '-v', 'ON_ERROR_STOP=1'], { input: bookSql() });
  const count = execFileSync('psql', [DSN, '-X', '-q', '-t', '-A', '-c', 'SELECT count(*) FROM investment_transaction'], { encoding: 'utf8' }).trim();
  assert.equal(count, String(book.movements.length));
});

for (const portfolio of [P1, P2]) {
  for (const grain of ['month', 'quarter']) {
    test(`${portfolio} by ${grain}: every row equals the hand answer, and nothing is refused`, () => {
      ready();
      const dir = mkdtempSync(path.join(tmpdir(), 'ev-ref-'));
      const csv = reference(portfolio, grain);
      writeFileSync(path.join(dir, 'ref.csv'), csv);
      const json = engine('reference', path.join(dir, 'ref.csv'));
      assert.equal(json.code, 0, json.out);
      assert.equal(JSON.parse(json.out).refused, '');
      writeFileSync(path.join(dir, 'ref.json'), json.out);
      const r = engine('expect', path.join(dir, 'ref.json'), path.join(FIX, 'expected-average.csv'), `portfolio:${portfolio}`, grain);
      assert.equal(r.code, 0, r.out);

      // the answers the no-database suite reads (two of the four cases): the same numbers — rewritten with --write
      const name = SAVED[`${portfolio}/${grain}`];
      if (name) {
        const saved = path.join(FIX, name);
        if (WRITE) writeFileSync(saved, csv);
        const a = JSON.parse(engine('reference', saved).out);
        assert.deepEqual(a.rows, JSON.parse(json.out).rows, `${name} is stale — just verify-evolution-reference --write`);
      }
    });
  }
}

test('a ledger holding units the provider does not is refused, as the renderer refuses it (incomplete_ledger)', () => {
  ready();
  const psql = (sql) => execFileSync('psql', [DSN, '-X', '-q', '-v', 'ON_ERROR_STOP=1', '-c', sql], { encoding: 'utf8' });
  psql(`UPDATE investment_position SET quantity = 1 WHERE portfolio_ref = ${q(P1)} AND asset_ref = 'CZ0008474053'`);
  try {
    const dir = mkdtempSync(path.join(tmpdir(), 'ev-ref-'));
    writeFileSync(path.join(dir, 'ref.csv'), reference(P1, 'month'));
    const refused = JSON.parse(engine('reference', path.join(dir, 'ref.csv')).out).refused;
    assert.match(refused, /the ledger holds [\d.]+ more units of CZ0008474053 than the provider's valuation \(incomplete_ledger\)/);
  } finally {
    // put the book back, so a rerun of a single test starts from the fixture
    const units = book.portfolios[0].valuation.units.CZ0008474053;
    psql(`UPDATE investment_position SET quantity = ${units} WHERE portfolio_ref = ${q(P1)} AND asset_ref = 'CZ0008474053'`);
  }
});

// ── IA-P4 review: R1 (a window ending before the provider's valuation) · R3 (same-day order) · R9 (unknown cost) ─────

/** The reference for [portfolio] by [grain] over [window], held to the rows of [expected] for [key] — none refused. */
function holds(portfolio, grain, window, expected, key = `portfolio:${portfolio}`) {
  const dir = mkdtempSync(path.join(tmpdir(), 'ev-ref-'));
  writeFileSync(path.join(dir, 'ref.csv'), reference(portfolio, grain, window));
  const json = engine('reference', path.join(dir, 'ref.csv'));
  assert.equal(json.code, 0, json.out);
  assert.equal(JSON.parse(json.out).refused, '', `${portfolio} ${grain} as of ${window.as_of} is refused`);
  writeFileSync(path.join(dir, 'ref.json'), json.out);
  const r = engine('expect', path.join(dir, 'ref.json'), expected, key, grain);
  assert.equal(r.code, 0, `${portfolio} ${grain} as of ${window.as_of}:\n${r.out}`);
}

/** psql-style CSV rows of [file] as objects (the hand answers carry no quoted commas). */
function csvRows(file) {
  const [head, ...lines] = readFileSync(file, 'utf8').trimEnd().split('\n');
  const keys = head.split(',');
  return { keys, rows: lines.map((l) => Object.fromEntries(l.split(',').map((v, i) => [keys[i], v]))) };
}

test('R1 · as of 2026-04-30, before the provider\'s valuation of 06-12: every row is the main window\'s — the gap is read against the ledger to 06-12, not cut at as_of', () => {
  ready();
  // the main answers to April by month; by quarter Q3…Q1 and a partial Q2 (04-01…04-30) that IS the main April
  const { keys, rows } = csvRows(path.join(FIX, 'expected-average.csv'));
  const kept = [];
  const partial = []; // after every Q1 — the comparison reads a scope's rows in order
  for (const r of rows) {
    if (r.grain === 'month' && r.period <= '2026-04') kept.push(r);
    if (r.grain === 'quarter' && r.period <= '2026-Q1') kept.push(r);
    if (r.grain === 'month' && r.period === '2026-04') partial.push({ ...r, grain: 'quarter', period: '2026-Q2' });
  }
  kept.push(...partial);
  const dir = mkdtempSync(path.join(tmpdir(), 'ev-ref-'));
  const expected = path.join(dir, 'expected-as-of-2026-04-30.csv');
  writeFileSync(expected, `${keys.join(',')}\n${kept.map((r) => keys.map((k) => r[k]).join(',')).join('\n')}\n`);
  for (const portfolio of [P1, P2]) for (const grain of ['month', 'quarter']) holds(portfolio, grain, { from: book.window.from, as_of: '2026-04-30' }, expected);
});

test('R1 · as of 2026-03-15 (C\'s payout and B\'s sale come after it): the hand answers of expected-as-of-2026-03-15', () => {
  ready();
  const expected = path.join(FIX, 'expected-as-of-2026-03-15-average.csv');
  for (const portfolio of [P1, P2]) for (const grain of ['month', 'quarter']) holds(portfolio, grain, { from: book.window.from, as_of: '2026-03-15' }, expected);
});

test('the cases book loads beside the main one (its own portfolios, instruments and client; the same home currency)', () => {
  ready();
  assert.equal(cases.home_currency, book.home_currency);
  execFileSync('psql', [DSN, '-X', '-q', '-v', 'ON_ERROR_STOP=1'], { input: bookSql(cases, { estate: false }) });
  const count = execFileSync('psql', [DSN, '-X', '-q', '-t', '-A', '-c', 'SELECT count(*) FROM investment_transaction'], { encoding: 'utf8' }).trim();
  assert.equal(count, String(book.movements.length + cases.movements.length));
});

test('R3 · P3: a same-day storno pairs whatever the ids\' order, and a day\'s buys come before its sales — the hand answers', () => {
  ready();
  const expected = path.join(FIX, 'expected-cases-average.csv');
  for (const grain of ['month', 'quarter']) holds(cases.portfolios[0].portfolio_id, grain, cases.window, expected);
});

test('R9 · P4: a holding deemed at the opening with no opening price has an unknown cost — empty, never 0 — the hand answers', () => {
  ready();
  const expected = path.join(FIX, 'expected-cases-average.csv');
  for (const grain of ['month', 'quarter']) holds(cases.portfolios[1].portfolio_id, grain, cases.window, expected);
  // and the unknown is the reference's own answer, not the comparison forgiving it: the cells are empty
  const csv = reference(cases.portfolios[1].portfolio_id, 'month', cases.window);
  const nov = csv.split('\n').find((l) => l.startsWith('2025-11,'));
  const { keys } = csvRows(path.join(FIX, 'expected-cases-average.csv'));
  const head = csv.split('\n')[0].split(',');
  const cell = (k) => nov.split(',')[head.indexOf(k)];
  for (const k of ['invested_close', 'unrealized_close', 'sales_at_cost', 'realized_sales', 'fx_realized', 'unexplained']) assert.equal(cell(k), '', `${k} is ${cell(k)}`);
  assert.equal(Number(cell('sales_proceeds')), 2200);
  assert.ok(keys.includes('unconverted'));
});
