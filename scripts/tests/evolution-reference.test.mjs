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

const q = (v) => (v === null || v === undefined ? 'NULL' : `'${String(v).replace(/'/g, "''")}'`);
const n = (v) => (v === null || v === undefined ? 'NULL' : String(v));

/** The fixture as INSERTs into `book-schema.sql`'s six tables — the book the hand answers were worked from. */
function bookSql() {
  const out = [`INSERT INTO investment_estate_setting (home_currency) VALUES (${q(book.home_currency)});`];
  for (const p of book.portfolios) {
    out.push(`INSERT INTO investment_portfolio_setting VALUES (${q(p.portfolio_id)}, ${q(p.reporting_currency)});`);
    for (const [isin, units] of Object.entries(p.valuation?.units ?? {})) {
      out.push(
        `INSERT INTO investment_position (portfolio_ref, asset_ref, valuation_date, quantity, valid_from) VALUES ` +
          `(${q(p.portfolio_id)}, ${q(isin)}, ${q(p.valuation.valuation_date)}, ${n(units)}, ${q(p.valuation.valuation_date)});`,
      );
    }
  }
  for (const r of book.rates) out.push(`INSERT INTO investment_fx_rate VALUES (${q(r.currency)}, ${q(r.rate_date)}, ${n(r.rate)}, ${n(r.units)});`);
  for (const r of book.prices) out.push(`INSERT INTO investment_asset_price VALUES (${q(r.isin)}, ${q(r.price_date)}, ${n(r.price)}, ${q(r.currency)});`);
  for (const m of book.movements) {
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

function reference(portfolio, grain) {
  return execFileSync(
    'psql',
    [DSN, '-X', '-q', '--csv', '-v', 'ON_ERROR_STOP=1', '-v', `portfolio=${portfolio}`, '-v', `from=${book.window.from}`, '-v', `as_of=${book.window.as_of}`, '-v', `grain=${grain}`, '-f', SQL],
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
