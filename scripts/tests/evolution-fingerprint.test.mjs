// IA-P4·S4.2·T5 — `scripts/fingerprint-evolution.sh` and its engine, without an estate.
//
// Run: node --test scripts/tests/evolution-fingerprint.test.mjs
//
// The workbook here is the RENDERER's own (`fixtures/evolution/workbook-*.xlsx`, kantheon over its hand fixture) and the
// reference answer is the reference SQL's own on that fixture (`reference-*.csv`, `just verify-evolution-reference`
// writes them) — so a green run here is the local fingerprint: the workbook a client receives agrees with the book it
// was computed from, through code the two share none of. Then every check is shown FAILING on purpose: a cent too far,
// a return too far, a FIFO workbook, a window with no rate, a row that does not balance, a book the reference refuses,
// a render the renderer refuses — each naming what disagreed.
//
// No estate: a stub studio-bff serves the workbook, a fake `psql` prints the saved reference answer (after checking
// it was handed the reference file and every `-v` it needs).

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn, execFileSync } from 'node:child_process';
import { createServer } from 'node:http';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const SCRIPT = path.resolve(here, '../fingerprint-evolution.sh');
const ENGINE = path.resolve(here, '../lib/evolution_fingerprint.py');
const SQL = path.resolve(here, '../sql/evolution-reference.sql');
const FIX = path.resolve(here, 'fixtures/evolution');

const CASES = {
  month: { portfolio: 'conseq:200900001', grain: 'month', workbook: 'workbook-200900001-month.xlsx', reference: 'reference-200900001-month.csv' },
  quarter: { portfolio: 'conseq:200900002', grain: 'quarter', workbook: 'workbook-200900002-quarter.xlsx', reference: 'reference-200900002-quarter.csv' },
};
const FROM = '2025-07-01';
const AS_OF = '2026-06-15';

const engine = (...args) => {
  try {
    return { code: 0, out: execFileSync('python3', [ENGINE, ...args], { encoding: 'utf8' }) };
  } catch (e) {
    return { code: e.status, out: `${e.stdout ?? ''}${e.stderr ?? ''}` };
  }
};

/** The reference CSV with [edit] applied to its parsed rows (psql's `--csv`: a header, then plain cells). */
function editedReference(file, edit) {
  const [head, ...lines] = readFileSync(path.join(FIX, file), 'utf8').trimEnd().split('\n');
  const keys = head.split(',');
  const rows = lines.map((l) => Object.fromEntries(l.split(',').map((v, i) => [keys[i], v])));
  edit(rows);
  return `${head}\n${rows.map((r) => keys.map((k) => r[k]).join(',')).join('\n')}\n`;
}

function harness(c, opts = {}) {
  const dir = mkdtempSync(path.join(tmpdir(), 'ev-fp-'));
  const calls = [];
  writeFileSync(path.join(dir, 'reference.csv'), opts.reference ?? readFileSync(path.join(FIX, c.reference), 'utf8'));
  writeFileSync(
    path.join(dir, 'psql'),
    `#!/usr/bin/env node
const { readFileSync, writeFileSync } = require('node:fs');
const args = process.argv.slice(2);
writeFileSync(${JSON.stringify(path.join(dir, 'psql-args.json'))}, JSON.stringify(args));
process.stdout.write(readFileSync(${JSON.stringify(path.join(dir, 'reference.csv'))}, 'utf8'));
`,
    { mode: 0o755 },
  );
  const auths = [];
  const server = createServer((req, res) => {
    calls.push(`${req.method} ${req.url}`);
    auths.push(req.headers.authorization);
    const json = (status, body) => {
      res.writeHead(status, { 'content-type': 'application/json' });
      res.end(JSON.stringify(body));
    };
    if (req.method === 'POST' && req.url === '/api/reports/render') {
      let body = '';
      req.on('data', (x) => (body += x));
      req.on('end', () => {
        calls.push(`render ${body}`);
        if (opts.refusal) return json(opts.refusal.status, opts.refusal.body);
        json(200, { artifactId: 'a-2', sizeBytes: '11973' });
      });
      return;
    }
    if (req.method === 'GET' && req.url.startsWith('/api/reports/artifacts/')) {
      res.writeHead(200, { 'content-type': 'application/octet-stream' });
      res.end(readFileSync(path.join(FIX, c.workbook)));
      return;
    }
    json(404, { code: 'NOT_FOUND', message: req.url });
  });
  return { dir, calls, auths, server };
}

function run(h, c, args = [], env = {}) {
  const { port } = h.server.address();
  return new Promise((resolve) => {
    const proc = spawn('bash', [SCRIPT, ...args], {
      cwd: h.dir,
      env: {
        ...process.env,
        PATH: `${h.dir}:${process.env.PATH}`,
        IE_FP_BFF: `http://127.0.0.1:${port}`,
        IE_FP_BEARER: 'tok-1',
        IE_FP_DSN: 'postgresql://fake/entry',
        IE_FP_PORTFOLIO: c.portfolio,
        IE_FP_FROM: FROM,
        IE_FP_AS_OF: AS_OF,
        IE_FP_GRAIN: c.grain,
        ...env,
      },
    });
    let out = '';
    proc.stdout.on('data', (x) => (out += x));
    proc.stderr.on('data', (x) => (out += x));
    proc.on('close', (code) => resolve({ code, out }));
  });
}

async function withHarness(c, opts, body) {
  const h = harness(c, opts);
  await new Promise((r) => h.server.listen(0, '127.0.0.1', r));
  try {
    return await body(h);
  } finally {
    h.server.close();
  }
}

test('the tools the fingerprint needs are on PATH', () => {
  for (const tool of ['bash', 'curl', 'jq', 'python3']) {
    assert.doesNotThrow(() => execFileSync('sh', ['-c', `command -v ${tool}`]), `${tool} is not on PATH`);
  }
});

test('the saved reference answers ARE the hand answers — the third side, without a database', () => {
  for (const c of Object.values(CASES)) {
    const dir = mkdtempSync(path.join(tmpdir(), 'ev-ref-'));
    const json = path.join(dir, 'ref.json');
    writeFileSync(json, engine('reference', path.join(FIX, c.reference)).out);
    const { code, out } = engine('expect', json, path.join(FIX, 'expected-average.csv'), `portfolio:${c.portfolio}`, c.grain);
    assert.equal(code, 0, out);
    assert.match(out, /agree/);
  }
});

for (const [name, c] of Object.entries(CASES)) {
  test(`${name}: the renderer's workbook agrees with the reference on the same book — Periods and Summary`, async () => {
    await withHarness(c, {}, async (h) => {
      const { code, out } = await run(h, c);
      assert.equal(code, 0, out);
      assert.match(out, /agree — \d+ periods × 35 columns \+ the Summary/);
      assert.match(out, /the evolution matches the book/);
      // the render the Evolution tab's download sends — a workbook (no `format`), the window as dates
      const render = JSON.parse(h.calls.find((x) => x.startsWith('render ')).slice('render '.length));
      assert.deepEqual(render, {
        templateId: 'investment-evolution:v2',
        args: { scope: 'portfolio', id: c.portfolio, grain: c.grain, from: FROM, as_of: AS_OF },
      });
      // psql was handed the reference and every variable it reads, as psql variables (it quotes them itself)
      const args = JSON.parse(readFileSync(path.join(h.dir, 'psql-args.json'), 'utf8'));
      assert.equal(args[args.indexOf('-f') + 1], SQL);
      for (const v of [`portfolio=${c.portfolio}`, `from=${FROM}`, `as_of=${AS_OF}`, `grain=${c.grain}`]) {
        assert.ok(args.includes(v), `psql was not given -v ${v}: ${args.join(' ')}`);
      }
      // …and the classification table (IA-P4b·S4b.2), as the relation the reference joins — read from the synced copy
      const labels = args.find((a) => a.startsWith('labels='));
      assert.ok(labels, `psql was not given -v labels=…: ${args.join(' ')}`);
      assert.match(labels, /^labels=VALUES \(1, 'vstupní poplatek', /);
      assert.match(out, /every cash and flow movement labelled \(IA-C49 footnotes off\)/);
    });
  });
}

test('⛔ a cent too far in one cell FAILS, naming the period and the column', async () => {
  const c = CASES.month;
  const reference = editedReference(c.reference, (rows) => {
    rows[4].market_value_close = String(Number(rows[4].market_value_close) + 0.02);
  });
  await withHarness(c, { reference }, async (h) => {
    const { code, out } = await run(h, c);
    assert.equal(code, 1, out);
    assert.match(out, /2025-11 market_value_close: workbook [\d.]+, reference [\d.]+/);
    assert.match(out, /does not match the book/);
  });
});

test('⛔ a deposit the book has and the workbook lacks moves the Summary too', async () => {
  const c = CASES.quarter;
  const reference = editedReference(c.reference, (rows) => {
    rows[1].deposits = String(Number(rows[1].deposits) + 100);
    rows[1].flows_net = String(Number(rows[1].flows_net) + 100);
  });
  await withHarness(c, { reference }, async (h) => {
    const { code, out } = await run(h, c);
    assert.equal(code, 1, out);
    assert.match(out, /2025-Q4 deposits/);
    assert.match(out, /Summary net_contributions/);
  });
});

test('⛔ a book the reference refuses is not compared — the refusal is the finding', async () => {
  const c = CASES.month;
  const reference = editedReference(c.reference, (rows) => {
    for (const r of rows) r.refused = 'the ledger holds 3 more units of CZ0008474053 than the provider (incomplete_ledger)';
  });
  await withHarness(c, { reference }, async (h) => {
    const { code, out } = await run(h, c);
    assert.equal(code, 1, out);
    assert.match(out, /the book cannot be compared: the ledger holds 3 more units/);
  });
});

test('⛔ a render the renderer refuses stops the run with ITS code and sentence', async () => {
  const c = CASES.month;
  const refusal = { status: 502, body: { code: 'evolution_unbalanced', message: 'the evolution of conseq:200900001 does not balance in 2026-03' } };
  await withHarness(c, { refusal }, async (h) => {
    const { code, out } = await run(h, c);
    assert.equal(code, 1, out);
    assert.match(out, /HTTP 502 evolution_unbalanced — the evolution of conseq:200900001 does not balance in 2026-03/);
  });
});

test('--save prints the fingerprint block for the private repo — and refuses to write inside this public one', async () => {
  const c = CASES.quarter;
  await withHarness(c, {}, async (h) => {
    const { code, out } = await run(h, c, ['--save']);
    assert.equal(code, 0, out);
    assert.match(out, /-----BEGIN FINGERPRINT investment-evolution-v2-conseq-200900002-quarter-2026-06-15\.json-----/);
    assert.match(out, /-----END FINGERPRINT-----/);
    const inside = await run(h, c, ['--save'], { IE_FP_SAVE_DIR: path.resolve(here, '..') });
    assert.equal(inside.code, 1, inside.out);
    assert.match(inside.out, /inside this repository, which is PUBLIC/);
  });
});

test('the bearer reaches studio-bff on both calls and never rides on curl\'s command line (a process list shows argv)', async () => {
  const c = CASES.month;
  const real = execFileSync('sh', ['-c', 'command -v curl'], { encoding: 'utf8' }).trim();
  await withHarness(c, {}, async (h) => {
    // a curl first on PATH that records its argv, then runs the real one
    writeFileSync(
      path.join(h.dir, 'curl'),
      `#!/usr/bin/env bash\nprintf '%s\\n' "$*" >>${JSON.stringify(path.join(h.dir, 'curl-argv'))}\nexec ${JSON.stringify(real)} "$@"\n`,
      { mode: 0o755 },
    );
    const { code, out } = await run(h, c, [], { IE_FP_BEARER: 'tok-secret-7' });
    assert.equal(code, 0, out);
    assert.deepEqual(h.auths, ['Bearer tok-secret-7', 'Bearer tok-secret-7']);
    const argv = readFileSync(path.join(h.dir, 'curl-argv'), 'utf8');
    assert.equal(argv.trim().split('\n').length, 2, argv);
    assert.ok(!argv.includes('tok-secret-7'), `the bearer is on curl's argv: ${argv}`);
  });
});

// ── the engine's own refusals ────────────────────────────────────────────────────────────────────────────────────

function compared(c, edit) {
  const dir = mkdtempSync(path.join(tmpdir(), 'ev-cmp-'));
  const wb = JSON.parse(engine('sheet', path.join(FIX, c.workbook), c.portfolio).out);
  edit(wb);
  writeFileSync(path.join(dir, 'w.json'), JSON.stringify(wb));
  writeFileSync(path.join(dir, 'r.json'), engine('reference', path.join(FIX, c.reference)).out);
  return engine('compare', path.join(dir, 'w.json'), path.join(dir, 'r.json'));
}

test('the engine reads the workbook a person opens: periods, Summary, Notes — by header, not by luck', () => {
  const wb = JSON.parse(engine('sheet', path.join(FIX, CASES.month.workbook), CASES.month.portfolio).out);
  assert.equal(wb.rows.length, 12);
  assert.equal(wb.rows[0].period, '2025-07');
  assert.equal(wb.rows[0].period_end, '2025-07-31');
  assert.equal(wb.facts['Cost basis'], 'average');
  assert.equal(wb.facts.Currency, 'CZK');
  assert.equal(wb.summary.portfolio_id, CASES.month.portfolio);
  // a portfolio the workbook does not hold is said, not read as empty
  const other = engine('sheet', path.join(FIX, CASES.month.workbook), 'conseq:999');
  assert.notEqual(other.code, 0);
  assert.match(other.out, /holds no row of conseq:999/);
});

// ── IA-P4b·S4b.2: IA-C49's footnotes follow the classification ─────────────────────────────────────────────────────

test('IA-P4b · the classified workbook prints no footnote on Withdrawals, Income, Fees — and the engine says so', () => {
  const wb = JSON.parse(engine('sheet', path.join(FIX, CASES.month.workbook), CASES.month.portfolio).out);
  assert.equal(wb.footnoted, false);
  // the book it was rendered from is labelled whole — and the saved reference says so
  assert.equal(JSON.parse(engine('reference', path.join(FIX, CASES.month.reference)).out).labelled, true);
});

test('IA-P4b · a workbook from before the classification (every header still ` *`) is read too — footnoted', () => {
  // the renderer's v2 workbook of IA-P4 (ttr-demo ce70327), kept as the shape an unclassified render prints
  const wb = JSON.parse(engine('sheet', path.join(FIX, 'workbook-200900001-month-unlabelled.xlsx'), CASES.month.portfolio).out);
  assert.equal(wb.footnoted, true);
  assert.equal(wb.rows.length, 12);
});

test('⛔ IA-P4b · footnotes that contradict the book FAIL — a classified book with them, an unclassified one without', () => {
  const kept = compared(CASES.month, (wb) => (wb.footnoted = true));
  assert.equal(kept.code, 1, kept.out);
  assert.match(kept.out, /carries IA-C49's footnotes .* but the book is labelled whole/);
  // the other way round: the reference says some movement carries no label, the workbook dropped the footnotes anyway
  const dir = mkdtempSync(path.join(tmpdir(), 'ev-cmp-'));
  const wb = JSON.parse(engine('sheet', path.join(FIX, CASES.month.workbook), CASES.month.portfolio).out);
  writeFileSync(path.join(dir, 'w.json'), JSON.stringify(wb));
  const ref = JSON.parse(engine('reference', path.join(FIX, CASES.month.reference)).out);
  ref.labelled = false;
  writeFileSync(path.join(dir, 'r.json'), JSON.stringify(ref));
  const dropped = engine('compare', path.join(dir, 'w.json'), path.join(dir, 'r.json'));
  assert.equal(dropped.code, 1, dropped.out);
  assert.match(dropped.out, /drops IA-C49's footnotes .* but the book is not labelled whole/);
});

test('⛔ IA-P4b · a fee the workbook moved and the book did not is a difference in fees AND withdrawals', () => {
  const { code, out } = compared(CASES.month, (wb) => {
    const may = wb.rows.find((r) => r.period === '2026-05');
    may.withdrawals = String(Number(may.withdrawals) + 1240);
    may.fees = String(Number(may.fees) - 1240);
  });
  assert.equal(code, 1, out);
  assert.match(out, /2026-05 withdrawals: workbook/);
  assert.match(out, /2026-05 fees: workbook/);
});

test('⛔ a FIFO workbook is refused — the reference computes average cost only', () => {
  const { code, out } = compared(CASES.month, (wb) => (wb.facts['Cost basis'] = 'fifo'));
  assert.equal(code, 1, out);
  assert.match(out, /costed `fifo`; the reference computes average cost only/);
});

test('⛔ a window with an amount no rate converts is refused — two empties agreeing prove nothing', () => {
  const { code, out } = compared(CASES.quarter, (wb) => {
    wb.rows[2].unconverted = '1';
    wb.rows[2].missing_rate = 'USD';
  });
  assert.equal(code, 1, out);
  assert.match(out, /2026-Q1: 1 amounts had no rate \(USD\)/);
});

test('⛔ a workbook row that does not balance is caught, whatever the reference says', () => {
  const { code, out } = compared(CASES.month, (wb) => (wb.rows[7].unexplained = '0.04'));
  assert.equal(code, 1, out);
  assert.match(out, /2026-02: the workbook's unexplained is 0.04, not 0.00/);
});

test('⛔ a plain return apart by more than 0.0001 pp fails; by rounding alone it passes', () => {
  const near = compared(CASES.month, (wb) => (wb.summary.plain_return_pct = String(Number(wb.summary.plain_return_pct) + 0.00005)));
  assert.equal(near.code, 0, near.out);
  const far = compared(CASES.month, (wb) => (wb.summary.plain_return_pct = String(Number(wb.summary.plain_return_pct) + 0.001)));
  assert.equal(far.code, 1, far.out);
  assert.match(far.out, /Summary plain_return_pct/);
});

test('R9 · a cell both sides leave empty (a cost nobody knows) agrees; empty on one side only is a difference', () => {
  const c = CASES.month;
  const dir = mkdtempSync(path.join(tmpdir(), 'ev-cmp-'));
  const wb = JSON.parse(engine('sheet', path.join(FIX, c.workbook), c.portfolio).out);
  const ref = JSON.parse(engine('reference', path.join(FIX, c.reference)).out);
  const blank = (row) => Object.assign(row, { invested_close: '', unrealized_close: '', sales_at_cost: '', unexplained: '' });
  blank(wb.rows[3]);
  writeFileSync(path.join(dir, 'w.json'), JSON.stringify(wb));
  writeFileSync(path.join(dir, 'r1.json'), JSON.stringify(ref));
  const one = engine('compare', path.join(dir, 'w.json'), path.join(dir, 'r1.json'));
  assert.equal(one.code, 1, one.out);
  assert.match(one.out, /2025-10 invested_close: workbook None, reference [\d.]+/);
  assert.match(one.out, /2025-10: the workbook's unexplained is empty, not 0\.00/);
  blank(ref.rows[3]);
  writeFileSync(path.join(dir, 'r2.json'), JSON.stringify(ref));
  const both = engine('compare', path.join(dir, 'w.json'), path.join(dir, 'r2.json'));
  assert.equal(both.code, 0, both.out);
});

test('⛔ a missing period is caught', () => {
  const { code, out } = compared(CASES.quarter, (wb) => wb.rows.pop());
  assert.equal(code, 1, out);
  assert.match(out, /the workbook has 3 periods, the reference 4/);
});
