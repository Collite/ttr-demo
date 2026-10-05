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
// IA-P4b·S4b.2: the classification table the renderer packages, synced with the model — handed to the reference as
// `:labels`, the way scripts/fingerprint-evolution.sh hands it in on the estate
const LABELS = execFileSync(
  'python3',
  [path.resolve(here, '../lib/income_labels.py'), 'sql', path.resolve(here, '../../model/investment/income-labels.yaml')],
  { encoding: 'utf8' },
).trim();

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
      'INSERT INTO investment_transaction (external_id, portfolio_ref, asset_ref, leg, operation, trade_date, quantity, amount, currency, reversal_of, fee, label, settlement_date) ' +
        `VALUES (${q(m.external_id)}, ${q(m.portfolio)}, ${q(m.isin)}, ${q(m.leg)}, ${q(m.operation)}, ${q(m.trade_date)}, ${n(m.quantity)}, ${n(m.amount)}, ${q(m.currency)}, ${q(m.reversal_of)}, ` +
        `${n(m.fee)}, ${q(m.label)}, ${q(m.settlement_date)});`,
    );
  }
  return out.join('\n');
}

function ready() {
  assert.ok(DSN, 'EVOLUTION_REF_DSN is not set — run `just verify-evolution-reference`, which starts PostgreSQL 16, loads the fixture and re-runs this file');
}

function reference(portfolio, grain, window = book.window, labels = LABELS) {
  return execFileSync(
    'psql',
    [DSN, '-X', '-q', '--csv', '-v', 'ON_ERROR_STOP=1', '-v', `portfolio=${portfolio}`, '-v', `from=${window.from}`, '-v', `as_of=${window.as_of}`, '-v', `grain=${grain}`, '-v', `labels=${labels}`, '-f', SQL],
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
      // every cash and external-flow movement of the fixture carries a label: IA-C49's footnotes drop (IA-P4b)
      assert.equal(JSON.parse(json.out).labelled, true);
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

// ── IA-P4b·S4b.2: income and fees by the provider's label (IA-C55) ────────────────────────────────────────────────────

test('IA-P4b · the book before IA-P4b (every label NULL): kantheon\'s expected-unlabelled answers — fees and income 0, entry fees inside withdrawals, the footnotes kept', () => {
  ready();
  const psql = (sql) => execFileSync('psql', [DSN, '-X', '-q', '-v', 'ON_ERROR_STOP=1', '-c', sql], { encoding: 'utf8' });
  psql(`UPDATE investment_transaction SET label = NULL WHERE portfolio_ref IN (${q(P1)}, ${q(P2)})`);
  try {
    const expected = path.join(FIX, 'expected-unlabelled-average.csv');
    for (const portfolio of [P1, P2]) {
      for (const grain of ['month', 'quarter']) {
        holds(portfolio, grain, book.window, expected);
        const dir = mkdtempSync(path.join(tmpdir(), 'ev-ref-'));
        writeFileSync(path.join(dir, 'ref.csv'), reference(portfolio, grain));
        assert.equal(JSON.parse(engine('reference', path.join(dir, 'ref.csv')).out).labelled, false, `${portfolio} ${grain}`);
      }
    }
  } finally {
    // the labels back, so the cases below and a rerun of one test start from the fixture
    for (const m of book.movements) {
      if (m.label !== null && m.label !== undefined) psql(`UPDATE investment_transaction SET label = ${q(m.label)} WHERE external_id = ${q(m.external_id)}`);
    }
  }
});

test('IA-P4b · ONE movement without a label keeps the footnotes — the classification is incomplete, whatever the others say', () => {
  ready();
  const psql = (sql) => execFileSync('psql', [DSN, '-X', '-q', '-v', 'ON_ERROR_STOP=1', '-c', sql], { encoding: 'utf8' });
  const victim = book.movements.find((m) => m.portfolio === P1 && m.leg === 'external-flow' && m.trade_date >= book.window.from);
  psql(`UPDATE investment_transaction SET label = '   ' WHERE external_id = ${q(victim.external_id)}`);
  try {
    const dir = mkdtempSync(path.join(tmpdir(), 'ev-ref-'));
    writeFileSync(path.join(dir, 'ref.csv'), reference(P1, 'month'));
    assert.equal(JSON.parse(engine('reference', path.join(dir, 'ref.csv')).out).labelled, false, 'a blank label is no label');
  } finally {
    psql(`UPDATE investment_transaction SET label = ${q(victim.label)} WHERE external_id = ${q(victim.external_id)}`);
  }
});

test('IA-P4b · the matching rules, on a table of their own: exact before prefix, the longest prefix, a leg restricts, a fee deposit is a refund', () => {
  ready();
  // The real table cannot show these (its one prefix entry is `other`, and no fixture movement is a fee refund), so a
  // table written for the rules — the same relation shape income_labels.py emits — and six withdrawals and deposits of
  // P1 on 2026-05-20, external-flow only (the cash identity is not touched). The May row moves by exactly what the
  // renderer's rules say, measured against the same table WITHOUT the six.
  const rules =
    "VALUES (1, 'alpha', CAST(NULL AS TEXT), 'prefix', 'fee'), (2, 'alpha beta', CAST(NULL AS TEXT), 'prefix', 'interest'), " +
    "(3, 'alpha beta gamma', CAST(NULL AS TEXT), 'exact', 'other'), (4, 'refund thing', CAST(NULL AS TEXT), 'exact', 'fee'), " +
    "(5, 'cash only', 'cash', 'exact', 'fee')";
  const may = (labels) => {
    const rows = csvRows2(reference(P1, 'month', book.window, labels));
    return rows.find((r) => r.period === '2026-05');
  };
  const before = may(rules);
  const psql = (sql) => execFileSync('psql', [DSN, '-X', '-q', '-v', 'ON_ERROR_STOP=1', '-c', sql], { encoding: 'utf8' });
  const six = [
    ['R1', 'withdrawal', '10.00', 'X, Alpha Beta Gamma'], // exact `alpha beta gamma` (other) beats both prefixes → withdrawals
    ['R2', 'withdrawal', '20.00', 'alpha beta delta'], //     the LONGEST prefix, `alpha beta` (interest) → income −20
    ['R3', 'withdrawal', '40.00', 'alpha zeta'], //           prefix `alpha` (fee) → fees +40
    ['R4', 'deposit', '80.00', 'Refund thing'], //            exact `refund thing` (fee) on a DEPOSIT → fees −80, not a deposit
    ['R5', 'withdrawal', '160.00', 'cash only'], //           `cash only` is the cash leg's → unknown here → withdrawals
    ['R6', 'deposit', '320.00', 'Vklad Ident. 20260520 1'], // no entry → unknown → deposits
  ];
  try {
    for (const [id, op, amount, label] of six) {
      psql(
        'INSERT INTO investment_transaction (external_id, portfolio_ref, leg, operation, trade_date, amount, currency, label) ' +
          `VALUES (${q(`${P1}:FLOW:RULES:${id}`)}, ${q(P1)}, 'external-flow', ${q(op)}, '2026-05-20', ${amount}, 'CZK', ${q(label)})`,
      );
    }
    const after = may(rules);
    const d = (k) => Math.round((Number(after[k]) - Number(before[k])) * 100) / 100;
    assert.deepEqual(
      { deposits: d('deposits'), withdrawals: d('withdrawals'), fees: d('fees'), income: d('income'), unexplained: d('unexplained') },
      { deposits: 320, withdrawals: 170, fees: -40, income: -20, unexplained: 0 },
    );
  } finally {
    psql(`DELETE FROM investment_transaction WHERE external_id LIKE ${q(`${P1}:FLOW:RULES:%`)}`);
  }
});

test('IA-P4b · the reference normalises a label EXACTLY as the renderer does — the renderer\'s case list, through the SQL\'s own text', () => {
  ready();
  // the expression between /* norm */ and /* /norm */ in evolution-reference.sql, run over kantheon's cases
  const text = readFileSync(SQL, 'utf8');
  const m = /\/\* norm \*\/([\s\S]*?)\/\* \/norm \*\//.exec(text);
  assert.ok(m, 'evolution-reference.sql lost its /* norm */ … /* /norm */ markers');
  assert.ok(m[1].includes('l.label'), 'the normalisation no longer reads l.label');
  const cases = JSON.parse(readFileSync(path.join(FIX, 'income-labels.cases.json'), 'utf8'));
  assert.ok(cases.length >= 10);
  const values = cases.map((c, i) => `(${i}, ${q(c.label)})`).join(', ');
  const out = execFileSync(
    'psql',
    [DSN, '-X', '-q', '--csv', '-v', 'ON_ERROR_STOP=1', '-c', `SELECT i, COALESCE(${m[1].replaceAll('l.label', 'c.label')}, '') AS norm FROM (VALUES ${values}) c (i, label) ORDER BY i`],
    { encoding: 'utf8' },
  );
  const got = out.trimEnd().split('\n').slice(1).map((l) => l.replace(/^\d+,/, '').replace(/^"(.*)"$/, '$1'));
  cases.forEach((c, i) => assert.equal(got[i], c.normalized, JSON.stringify(c.label)));
});

test('IA-P4b · a capital letter with a diacritic folds in a C-locale database, where lower() alone would not', () => {
  ready();
  // the trap, measured: on a C ctype `lower('ÚROKY Z PRODLENÍ')` is `Úroky z prodlenÍ` — a first letter and a last one
  // left upper case, and a label the table spells `úroky z prodlení` would never match
  const ctype = execFileSync('psql', [DSN, '-X', '-q', '-t', '-A', '-c', 'SELECT datctype FROM pg_database WHERE datname = current_database()'], { encoding: 'utf8' }).trim();
  assert.equal(ctype, 'C', 'the reference database must be C-locale, as hartland\'s entry is — else this proves nothing');
  const plainLower = execFileSync('psql', [DSN, '-X', '-q', '-t', '-A', '-c', "SELECT lower('ÚROKY Z PRODLENÍ')"], { encoding: 'utf8' }).trim();
  assert.notEqual(plainLower, 'úroky z prodlení', 'lower() alone folded the capitals — the trap this test pins is gone');
  const text = readFileSync(SQL, 'utf8');
  const expr = /\/\* norm \*\/([\s\S]*?)\/\* \/norm \*\//.exec(text)[1].replaceAll('l.label', 'c.label');
  const out = execFileSync(
    'psql',
    [DSN, '-X', '-q', '-t', '-A', '-c', `SELECT ${expr} FROM (VALUES (1, 'ÚROKY Z PRODLENÍ'), (2, 'JT, VSTUPNÍ POPLATEK'), (3, 'VÝBĚR'), (4, 'POJIŠTĚNÍ - VRATKA'), (5, 'Úroky')) c (i, label) ORDER BY c.i`],
    { encoding: 'utf8' },
  );
  assert.deepEqual(out.trimEnd().split('\n'), ['úroky z prodlení', 'vstupní poplatek', 'výběr', 'pojištění - vratka', 'úroky']);
});

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

/** The reference's own CSV answer as objects — its cells carry no quoted commas (the `refused` text aside, last). */
function csvRows2(csv) {
  const [head, ...lines] = csv.trimEnd().split('\n');
  const keys = head.split(',');
  return lines.map((l) => Object.fromEntries(l.split(',').map((v, i) => [keys[i], v])));
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

// ── the IA-P4b review: R1 (a fee on both legs counted once) · R7 (the provider's valuation counts at settlement) ─────

test('R1 · P5: a cash-account contract\'s fee arrives on BOTH legs — the flow counts it in fees, its cash twin stays in cash_movements only — the hand answers', () => {
  ready();
  const p5 = cases.portfolios[2].portfolio_id;
  const expected = path.join(FIX, 'expected-cases-average.csv');
  for (const grain of ['month', 'quarter']) holds(p5, grain, cases.window, expected);
  // and the twins are the reference's own answer, not the comparison forgiving them: July's 300 entry fee is on both
  // legs (`…:CASH:DEB:502` ↔ `…:DEP:DEB502`), September's commission by day + amount (a hashed flow id), October's
  // cash 75 beside a flow 80 is NO twin (another amount) — both are fees
  const rows = csvRows2(reference(p5, 'month', cases.window));
  const fees = Object.fromEntries(rows.map((r) => [r.period, Math.round(Number(r.fees) * 100) / 100]));
  assert.deepEqual(fees, { '2025-07': 300, '2025-08': 50, '2025-09': 120, '2025-10': 155, '2025-11': 40, '2025-12': -15 });
  for (const r of rows) assert.ok(Math.abs(Number(r.unexplained)) < 0.005, `${r.period} unexplained ${r.unexplained}`);
});

test('R7 · P6: the valuation counts a movement on its settlement day — a sale and a buy settling after it are not yet in it, a buy with no day may still be settling — the hand answers', () => {
  ready();
  const p6 = cases.portfolios[3].portfolio_id;
  const expected = path.join(FIX, 'expected-cases-average.csv');
  for (const grain of ['month', 'quarter']) holds(p6, grain, cases.window, expected);
});

test('R7 · a buy that SETTLED before the valuation cannot explain a gap away as "still settling" — the ledger then holds more than the provider and the portfolio is refused', () => {
  ready();
  // the IA-P4b review's failure scenario (a), planted in P6: a 25-unit buy dealt 12-22 and settled 12-24 — inside the
  // 20 days before the 12-31 valuation — that the provider's units (50) do not hold. Its settlement day says the
  // provider has counted it, so the difference is the LEDGER's (a movement it holds and the provider does not); under
  // the old deal-day rule the buy's own units "explained" it and the report carried 25 units nobody holds
  const p6 = cases.portfolios[3].portfolio_id;
  const psql = (sql) => execFileSync('psql', [DSN, '-X', '-q', '-v', 'ON_ERROR_STOP=1', '-c', sql], { encoding: 'utf8' });
  const id = `${p6}:SUB:R7PLANT`;
  psql(
    'INSERT INTO investment_transaction (external_id, portfolio_ref, asset_ref, leg, operation, trade_date, quantity, amount, currency, label, settlement_date) ' +
      `VALUES (${q(id)}, ${q(p6)}, 'CZ0000600027', 'security', 'buy', '2025-12-22', 25, 2700.00, 'CZK', 'Nákup', '2025-12-24')`,
  );
  try {
    const dir = mkdtempSync(path.join(tmpdir(), 'ev-ref-'));
    writeFileSync(path.join(dir, 'ref.csv'), reference(p6, 'month', cases.window));
    const refused = JSON.parse(engine('reference', path.join(dir, 'ref.csv')).out).refused;
    assert.match(refused, /the ledger holds 25(\.0+)? more units of CZ0000600027 than the provider's valuation \(incomplete_ledger\)/);
  } finally {
    psql(`DELETE FROM investment_transaction WHERE external_id = ${q(id)}`);
  }
});
