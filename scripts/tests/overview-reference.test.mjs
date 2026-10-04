// IA-P4·S4.3·T6 — the four overview references (`scripts/sql/{statement,overview,price-sheet,sync-run-changes}-
// reference.sql`) RUN on PostgreSQL 16 against kantheon's hand fixture (+ the provider's figures and a synthetic
// journal), and each held to answers computed HERE, in JavaScript, from the fixture's JSON — a third implementation that
// shares nothing with the SQL or with the renderer. Then the saved answers the no-database suite reads.
//
// Run: just verify-overview-reference           (starts PG16 — the evolution reference's container — and runs this)
//      just verify-overview-reference --write   (…and rewrites fixtures/overview/reference-*.csv)
//
// Like the evolution reference's suite, it does NOT skip without a database: every test FAILS and names the recipe.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const EVO = path.resolve(here, 'fixtures/evolution');
const FIX = path.resolve(here, 'fixtures/overview');
const SQL = path.resolve(here, '../sql');
const DSN = process.env.OVERVIEW_REF_DSN;
const WRITE = process.env.OVERVIEW_REF_WRITE === '1';

const book = JSON.parse(readFileSync(path.join(EVO, 'fixture-ledger.json'), 'utf8'));
const P1 = book.portfolios[0].portfolio_id;
const CLIENT = book.clients[0].client_id;
const AS_OF = book.window.as_of;
const FROM = book.window.from;

const q = (v) => (v === null || v === undefined ? 'NULL' : `'${String(v).replace(/'/g, "''")}'`);
const n = (v) => (v === null || v === undefined ? 'NULL' : String(v));

function bookSql() {
  const out = [`INSERT INTO investment_estate_setting (home_currency) VALUES (${q(book.home_currency)});`];
  for (const c of book.clients) out.push(`INSERT INTO investment_client (external_id, name, valid_from) VALUES (${q(c.client_id)}, ${q(c.name)}, '2024-01-01');`);
  for (const p of book.portfolios) {
    out.push(
      `INSERT INTO investment_portfolio (external_id, label, client_ref, base_currency, state, valid_from) VALUES ` +
        `(${q(p.portfolio_id)}, ${q(p.name)}, ${q(p.client_id)}, ${q(p.base_currency)}, 'active', '2024-01-01');`,
    );
    out.push(`INSERT INTO investment_portfolio_setting VALUES (${q(p.portfolio_id)}, ${q(p.reporting_currency)});`);
    for (const [isin, units] of Object.entries(p.valuation?.units ?? {})) {
      out.push(
        'INSERT INTO investment_position (portfolio_ref, asset_ref, valuation_date, quantity, market_value, valid_from) VALUES ' +
          `(${q(p.portfolio_id)}, ${q(isin)}, ${q(p.valuation.valuation_date)}, ${n(units)}, ${n(p.valuation.market_values?.[isin])}, ${q(p.valuation.valuation_date)});`,
      );
    }
  }
  for (const v of book.valuation_points) {
    out.push(`INSERT INTO investment_portfolio_valuation (portfolio_ref, valuation_date, value, currency) VALUES (${q(v.portfolio)}, ${q(v.valuation_date)}, ${n(v.value)}, ${q(v.currency)});`);
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

// ── the answers, computed from the JSON ─────────────────────────────────────────────────────────────────────────────

const rate = (cur, day) => {
  if (cur === book.home_currency) return 1;
  const r = book.rates.filter((x) => x.currency === cur && x.rate_date <= day).sort((a, b) => b.rate_date.localeCompare(a.rate_date))[0];
  return r ? Number(r.rate) / r.units : null;
};
const price = (isin, day) =>
  book.prices.filter((p) => p.isin === isin && p.price_date <= day).sort((a, b) => b.price_date.localeCompare(a.price_date))[0] ?? null;
const reversed = new Set(book.movements.map((m) => m.reversal_of).filter(Boolean));
const effective = book.movements.filter((m) => !m.reversal_of && !reversed.has(m.external_id));
const signed = (m) => (m.operation === 'credit' ? Math.abs(Number(m.amount)) : m.operation === 'debit' ? -Math.abs(Number(m.amount)) : 0);
const monthEnd = (y, m) => new Date(Date.UTC(y, m, 0)).toISOString().slice(0, 10); // m 1-based: day 0 of the next month
const quarterBefore = (day) => {
  const [y, m] = day.split('-').map(Number);
  const first = Math.floor((m - 1) / 3) * 3 + 1; // the as_of's quarter's first month
  return monthEnd(first === 1 ? y - 1 : y, first === 1 ? 12 : first - 1);
};

// the fixture's clients are all open versions (loaded with no valid_to) — the book is its open clients' portfolios
const openClients = new Set(book.clients.map((c) => c.client_id));

function expectedOverview(client) {
  return book.portfolios
    .filter((p) => (client ? p.client_id === client : openClients.has(p.client_id)))
    .map((p) => {
      const mv = p.valuation && p.valuation.valuation_date <= AS_OF ? Object.values(p.valuation.market_values).filter((v) => v !== null).reduce((a, v) => a + Number(v), 0) : null;
      const cash = {};
      for (const m of effective.filter((x) => x.portfolio === p.portfolio_id && x.leg === 'cash' && x.trade_date <= AS_OF)) cash[m.currency] = (cash[m.currency] ?? 0) + signed(m);
      const entries = Object.entries(cash);
      const cashRc = entries.length === 0 ? null : entries.some(([c, b]) => b !== 0 && rate(c, AS_OF) === null) ? null : entries.reduce((a, [c, b]) => a + (b === 0 ? 0 : b * rate(c, AS_OF)), 0);
      const point = (day) => {
        const v = book.valuation_points.filter((x) => x.portfolio === p.portfolio_id && x.valuation_date <= day).sort((a, b) => b.valuation_date.localeCompare(a.valuation_date))[0];
        if (!v) return null;
        const r = rate(v.currency, day);
        return Number(v.value) === 0 || v.currency === book.home_currency ? Number(v.value) : r === null ? null : Number(v.value) * r;
      };
      const now = point(AS_OF);
      const prev = point(quarterBefore(AS_OF));
      return {
        client_id: p.client_id,
        portfolio_id: p.portfolio_id,
        market_value_rc: mv === null ? null : p.base_currency === book.home_currency || mv === 0 ? mv : mv * rate(p.base_currency, AS_OF),
        cash_rc: cashRc,
        value_rc: now,
        value_prev_quarter_end: prev,
        chg_qoq_pct: now === null || !prev ? null : (now / prev - 1) * 100,
      };
    });
}

// ── running the references ──────────────────────────────────────────────────────────────────────────────────────

function ready() {
  assert.ok(DSN, 'OVERVIEW_REF_DSN is not set — run `just verify-overview-reference`, which starts PostgreSQL 16, loads the fixture and re-runs this file');
}

function run(file, vars) {
  const args = [DSN, '-X', '-q', '--csv', '-v', 'ON_ERROR_STOP=1'];
  for (const [k, v] of Object.entries(vars)) args.push('-v', `${k}=${v}`);
  return execFileSync('psql', [...args, '-f', path.join(SQL, file)], { encoding: 'utf8' });
}

function rows(csv) {
  const [head, ...lines] = csv.trimEnd().split('\n');
  const keys = head.split(',');
  return lines.map((l) => Object.fromEntries(l.split(',').map((v, i) => [keys[i], v])));
}

function save(name, csv) {
  const file = path.join(FIX, name);
  if (WRITE) writeFileSync(file, csv);
  assert.equal(readFileSync(file, 'utf8'), csv, `${name} is stale — just verify-overview-reference --write`);
}

const close = (got, want, tol, what) => {
  if (want === null) return assert.equal(got, '', `${what}: computed ${got}, expected nothing`);
  assert.ok(got !== '', `${what}: computed nothing, expected ${want}`);
  assert.ok(Math.abs(Number(got) - want) <= tol, `${what}: computed ${got}, expected ${want}`);
};

test('the fixture book, its provider figures and a journal load into an empty schema', () => {
  ready();
  const psql = (sql) => execFileSync('psql', [DSN, '-X', '-q', '-v', 'ON_ERROR_STOP=1', '-c', sql], { encoding: 'utf8' });
  psql('DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;');
  for (const f of [path.join(EVO, 'book-schema.sql'), path.join(FIX, 'overview-schema.sql')]) execFileSync('psql', [DSN, '-X', '-q', '-v', 'ON_ERROR_STOP=1', '-f', f]);
  execFileSync('psql', [DSN, '-X', '-q', '-v', 'ON_ERROR_STOP=1'], { input: bookSql() });
  execFileSync('psql', [DSN, '-X', '-q', '-v', 'ON_ERROR_STOP=1', '-f', path.join(FIX, 'journal.sql')]);
  const count = execFileSync('psql', [DSN, '-X', '-q', '-t', '-A', '-c', 'SELECT count(*) FROM investment_portfolio_valuation'], { encoding: 'utf8' }).trim();
  assert.equal(count, String(book.valuation_points.length));
});

test('price-sheet: every valued instrument × the as_of and the month-ends back, at the latest price by each', () => {
  ready();
  const csv = run('price-sheet-reference.sql', { as_of: AS_OF, months: 6 });
  const got = rows(csv);
  const isins = [...new Set(book.portfolios.filter((p) => p.valuation.valuation_date <= AS_OF).flatMap((p) => Object.keys(p.valuation.units)))].sort();
  const [y, m] = AS_OF.split('-').map(Number);
  const days = [AS_OF, ...[1, 2, 3, 4, 5].map((k) => monthEnd(m - k > 0 ? y : y - 1, ((m - k - 1 + 12) % 12) + 1))].sort();
  assert.equal(got.length, isins.length * days.length);
  for (const isin of isins) {
    for (const day of days) {
      const row = got.find((r) => r.asset_id === isin && r.day === day);
      assert.ok(row, `${isin} on ${day}: no row`);
      const p = price(isin, day);
      close(row.price, p ? Number(p.price) : null, 1e-9, `${isin} on ${day}`);
    }
  }
  save('reference-price-sheet.csv', csv);
});

test('statement: the window’s effective ledger, row by row, and the cash leg per currency to the as_of', () => {
  ready();
  const csv = run('statement-reference.sql', { portfolio: P1, from: FROM, as_of: AS_OF });
  const got = rows(csv);
  const tx = got.filter((r) => r.kind === 'transaction');
  const want = effective.filter((x) => x.portfolio === P1 && x.trade_date >= FROM && x.trade_date <= AS_OF);
  assert.deepEqual(tx.map((r) => r.transaction_id).sort(), want.map((x) => x.external_id).sort());
  for (const w of want) {
    const r = tx.find((x) => x.transaction_id === w.external_id);
    close(r.amount, w.amount === null ? null : Number(w.amount), 0.005, `${w.external_id} amount`);
    close(r.quantity, w.quantity === null ? null : Number(w.quantity), 1e-9, `${w.external_id} quantity`);
  }
  const cash = {};
  for (const x of effective.filter((x) => x.portfolio === P1 && x.leg === 'cash' && x.trade_date <= AS_OF)) cash[x.currency] = (cash[x.currency] ?? 0) + signed(x);
  const gotCash = got.filter((r) => r.kind === 'cash');
  assert.deepEqual(gotCash.map((r) => r.currency).sort(), Object.keys(cash).sort());
  for (const r of gotCash) close(r.balance, cash[r.currency], 0.005, `cash ${r.currency}`);
  save('reference-statement.csv', csv);
});

for (const [name, client] of [['client-overview', CLIENT], ['distributor-overview', '']]) {
  test(`${name}: each open portfolio’s market value, cash, value now and at the last quarter end, in the home currency`, () => {
    ready();
    const csv = run('overview-reference.sql', { client, as_of: AS_OF });
    const got = rows(csv);
    const want = expectedOverview(client);
    assert.deepEqual(got.map((r) => r.portfolio_id), want.map((w) => w.portfolio_id));
    for (const w of want) {
      const r = got.find((x) => x.portfolio_id === w.portfolio_id);
      assert.equal(r.client_id, w.client_id);
      for (const k of ['market_value_rc', 'cash_rc', 'value_rc', 'value_prev_quarter_end']) close(r[k], w[k], 0.005, `${w.portfolio_id} ${k}`);
      close(r.chg_qoq_pct, w.chg_qoq_pct, 1e-6, `${w.portfolio_id} chg_qoq_pct`);
      assert.equal(r.open_clients, String(openClients.size), `${w.portfolio_id} open_clients`);
    }
    save(`reference-${name}.csv`, csv);
  });
}

test('distributor-overview: the book is its OPEN clients — one with no open portfolio still counts, a portfolio of a closed or unknown client is not on it', () => {
  ready();
  // edge rows inside one session, rolled back — the saved references above stay the fixture's own
  const edges = [
    "INSERT INTO investment_client (external_id, name, valid_from) VALUES ('conseq:8809002', 'Edge: open, no portfolio', '2024-01-01');",
    "INSERT INTO investment_client (external_id, name, valid_from, valid_to) VALUES ('conseq:8809003', 'Edge: closed', '2024-01-01', '2025-12-31');",
    "INSERT INTO investment_portfolio (external_id, label, client_ref, base_currency, state, valid_from) VALUES " +
      "('conseq:200900003', 'Edge: of a closed client', 'conseq:8809003', 'CZK', 'active', '2024-01-01'), " +
      "('conseq:200900004', 'Edge: of no client', 'conseq:8809004', 'CZK', 'active', '2024-01-01');",
  ];
  const within = (client) =>
    rows(
      execFileSync('psql', [DSN, '-X', '-q', '--csv', '-v', 'ON_ERROR_STOP=1', '-v', `client=${client}`, '-v', `as_of=${AS_OF}`], {
        encoding: 'utf8',
        input: ['BEGIN;', ...edges, `\\i ${path.join(SQL, 'overview-reference.sql')}`, 'ROLLBACK;', ''].join('\n'),
      }),
    );
  const whole = within('');
  assert.deepEqual(whole.map((r) => r.portfolio_id), expectedOverview('').map((w) => w.portfolio_id));
  assert.ok(whole.every((r) => r.open_clients === String(openClients.size + 1)), JSON.stringify(whole.map((r) => r.open_clients)));
  // a client's own overview reads that client's open portfolios, whatever the client's state — as client_overview does
  assert.deepEqual(within('conseq:8809003').map((r) => r.portfolio_id), ['conseq:200900003']);
});

test('sync-run-changes: a committed run’s changed rows per target, from its entry records', () => {
  ready();
  const csv = run('sync-run-changes-reference.sql', { run: 'run-20260930-0530' });
  const got = Object.fromEntries(rows(csv).map((r) => [r.target, r]));
  assert.equal(got['investment.transaction'].changed, '3');
  assert.equal(got['investment.transaction'].batches, '2');
  assert.equal(got['investment.asset_price'].changed, '61');
  assert.ok(Object.values(got).every((r) => r.refused === '' && r.undetailed === '0'));
  save('reference-sync-run-changes.csv', csv);
});

// the outcomes a change log LISTS as changed (IA-P4 review R5): the journal's `inserted + updated` must equal them
const CHANGED = new Set(['inserted', 'updated', 'closed', 'reversed']);

test('sync-run-changes: a correction is one changed movement — the effects equal the listed rows whose outcome changed the book', () => {
  ready();
  const got = Object.fromEntries(rows(run('sync-run-changes-reference.sql', { run: 'run-correction' })).map((r) => [r.target, r]));
  // a new movement + a correction (reversed); the unchanged and the refused rows change nothing
  assert.equal(got['investment.transaction'].changed, '2');
  assert.equal(got['investment.transaction'].refused, '');
  // computed HERE from every detailed record's rows: the counts the reference reads are those rows, by outcome
  const records = JSON.parse(
    execFileSync('psql', [DSN, '-X', '-q', '-t', '-A', '-c', "SELECT json_agg(json_build_object('batch', batch_id, 'p', payload::json)) FROM entry_record"], { encoding: 'utf8' }),
  );
  const detailed = records.filter((r) => Array.isArray(r.p.effects.rows));
  assert.ok(detailed.length >= 4, `${detailed.length} detailed records`);
  for (const r of detailed) {
    const listed = r.p.effects.rows.filter((x) => CHANGED.has(x.outcome)).length;
    assert.equal(r.p.effects.inserted + r.p.effects.updated, listed, `${r.batch}: effects ${JSON.stringify(r.p.effects)}`);
  }
});

test('sync-run-changes: a run committed with counts only is refused — its change log cannot list the rows', () => {
  ready();
  const got = rows(run('sync-run-changes-reference.sql', { run: 'run-counts' }));
  assert.match(got[0].refused, /^1 batch\(es\) of the run were committed with counts only/);
  assert.equal(got[0].undetailed, '1');
});

test('sync-run-changes: a run with a batch still held is refused — the journal records only committed effects', () => {
  ready();
  const refused = rows(run('sync-run-changes-reference.sql', { run: 'run-held' }))[0].refused;
  assert.match(refused, /^1 batch\(es\) of the run are not committed/);
  assert.match(rows(run('sync-run-changes-reference.sql', { run: 'no-such-run' }))[0].refused, /no batch of this run/);
});
