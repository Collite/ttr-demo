// IA-P4·S4.3·T6 — `scripts/fingerprint-overview.sh` and its engine, without an estate.
//
// Run: node --test scripts/tests/overview-fingerprint.test.mjs
//
// The workbooks here are the RENDERER's own (`fixtures/overview/workbook-*.xlsx`, kantheon over its hand fixture) and
// the reference answers are the reference SQL's own on that fixture (`reference-*.csv`, `just verify-overview-reference`
// writes them) — so a green run here is the local fingerprint of all five: the workbook a client receives agrees with
// the book it was computed from, through code the two share none of. Then every check is shown FAILING on purpose.
//
// No estate: a stub studio-bff serves the workbook, a fake `psql` prints the saved answer of the reference file it is
// handed (after recording every `-v`).

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn, execFileSync } from 'node:child_process';
import { createServer } from 'node:http';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const SCRIPT = path.resolve(here, '../fingerprint-overview.sh');
const ENGINE = path.resolve(here, '../lib/overview_fingerprint.py');
const EVOLUTION = path.resolve(here, '../lib/evolution_fingerprint.py');
const FIX = path.resolve(here, 'fixtures/overview');
const EVO = path.resolve(here, 'fixtures/evolution');
const AS_OF = '2026-06-15';

const CASES = {
  'portfolio-statement:v1': { name: 'statement', env: { IE_FP_PORTFOLIO: 'conseq:200900001', IE_FP_FROM: '2025-07-01' } },
  'client-overview:v1': { name: 'client-overview', env: { IE_FP_CLIENT: 'conseq:8809001' } },
  'distributor-overview:v1': { name: 'distributor-overview', env: {} },
  'price-sheet:v1': { name: 'price-sheet', env: { IE_FP_MONTHS: '6' }, months: ['--months', '6'] },
  'sync-run-changes:v1': { name: 'sync-run-changes', env: { IE_FP_RUN: 'run-20260930-0530' } },
};
const workbook = (c) => path.join(FIX, `workbook-${c.name}.xlsx`);
const reference = (c) => path.join(FIX, `reference-${c.name}.csv`);

const py = (script, ...args) => {
  try {
    return { code: 0, out: execFileSync('python3', [script, ...args], { encoding: 'utf8' }) };
  } catch (e) {
    return { code: e.status, out: `${e.stdout ?? ''}${e.stderr ?? ''}` };
  }
};

/** psql `--csv` (a header, then plain cells; a cell with a comma quoted) with [edit] applied to its rows. */
function edited(file, edit) {
  const [head, ...lines] = readFileSync(file, 'utf8').trimEnd().split('\n');
  const keys = head.split(',');
  const rows = lines.map((l) => Object.fromEntries(l.split(',').map((v, i) => [keys[i], v])));
  edit(rows, keys);
  return `${head}\n${rows.map((r) => keys.map((k) => r[k] ?? '').join(',')).join('\n')}\n`;
}

function compareWith(template, csv, extra = [], wb = workbook(CASES[template])) {
  const dir = mkdtempSync(path.join(tmpdir(), 'ov-fp-'));
  writeFileSync(path.join(dir, 'ref.csv'), csv);
  return py(ENGINE, 'compare', template, wb, path.join(dir, 'ref.csv'), ...(CASES[template].months ?? []), ...extra);
}

// The renderer's own workbook with a cell or a shared string changed — `part pattern replacement` triples (Python
// regexes), each of which must match, so a template change cannot turn a mutation into a silent no-op.
const MUTATE = `import re, sys, zipfile
src, dst, *edits = sys.argv[1:]
hit = [0] * (len(edits) // 3)
with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        data = zin.read(item.filename)
        for i in range(0, len(edits), 3):
            if edits[i] == item.filename:
                text, n = re.subn(edits[i + 1], edits[i + 2], data.decode('utf-8'))
                hit[i // 3] += n
                data = text.encode('utf-8')
        zout.writestr(item, data)
missed = [edits[3 * i + 1] for i, n in enumerate(hit) if n == 0]
sys.exit(f'no match for {missed}' if missed else 0)
`;
function mutated(template, ...edits) {
  const dir = mkdtempSync(path.join(tmpdir(), 'ov-fp-wb-'));
  writeFileSync(path.join(dir, 'mutate.py'), MUTATE);
  const dst = path.join(dir, 'workbook.xlsx');
  execFileSync('python3', [path.join(dir, 'mutate.py'), workbook(CASES[template]), dst, ...edits], { encoding: 'utf8' });
  return dst;
}
const SST = 'xl/sharedStrings.xml';

// ── the local fingerprint ──────────────────────────────────────────────────────────────────────────────────────

for (const [template, c] of Object.entries(CASES)) {
  test(`${template}: the renderer's workbook equals the reference on the book`, () => {
    const r = py(ENGINE, 'compare', template, workbook(c), reference(c), ...(c.months ?? []));
    assert.equal(r.code, 0, r.out);
    assert.match(r.out, /the workbook equals the book/);
  });
}

test("portfolio-statement: its Evolution sheet equals v2's reference for the same portfolio and window", () => {
  const dir = mkdtempSync(path.join(tmpdir(), 'ov-fp-'));
  writeFileSync(path.join(dir, 'wb.json'), py(EVOLUTION, 'sheet', workbook(CASES['portfolio-statement:v1']), 'conseq:200900001', '--sheet', 'Evolution').out);
  writeFileSync(path.join(dir, 'ref.json'), py(EVOLUTION, 'reference', path.join(EVO, 'reference-200900001-month.csv')).out);
  const r = py(EVOLUTION, 'compare', path.join(dir, 'wb.json'), path.join(dir, 'ref.json'));
  assert.equal(r.code, 0, r.out);
  assert.match(r.out, /agree — 12 periods/);
});

// ── every check, failing on purpose ────────────────────────────────────────────────────────────────────────────

test('price-sheet: a price a cent away, an instrument missing, the wrong number of months — each named', () => {
  const c = reference(CASES['price-sheet:v1']);
  let r = compareWith('price-sheet:v1', edited(c, (rows) => (rows[1].price = String(Number(rows[1].price) + 0.01))));
  assert.equal(r.code, 1);
  assert.match(r.out, /on 20\d\d-\d\d-\d\d: workbook .* · book/);
  r = compareWith('price-sheet:v1', edited(c, (rows) => rows.splice(0, rows.length, ...rows.filter((x) => x.asset_id !== 'CZ0008473618'))));
  assert.match(r.out, /instrument CZ0008473618: in the workbook, not on the book/);
  r = compareWith('price-sheet:v1', readFileSync(c, 'utf8'), ['--months', '12']);
  assert.match(r.out, /6 month columns, not min\(12, 24\)/);
});

test('portfolio-statement: an amount two cents away and a cash balance a crown away — each named', () => {
  const c = reference(CASES['portfolio-statement:v1']);
  let r = compareWith('portfolio-statement:v1', edited(c, (rows) => {
    const t = rows.find((x) => x.kind === 'transaction' && x.amount !== '');
    t.amount = String(Number(t.amount) + 0.02);
  }));
  assert.equal(r.code, 1);
  assert.match(r.out, /amount: workbook .* · book .*\(Δ -0\.02\)/);
  r = compareWith('portfolio-statement:v1', edited(c, (rows) => {
    const cash = rows.find((x) => x.kind === 'cash');
    cash.balance = String(Number(cash.balance) + 1);
  }));
  assert.match(r.out, /cash EUR: workbook .* · book/);
});

test('client-overview: a value two cents away is named; a cent is within IA-C51', () => {
  const c = reference(CASES['client-overview:v1']);
  let r = compareWith('client-overview:v1', edited(c, (rows) => (rows[0].value_rc = String(Number(rows[0].value_rc) + 0.02))));
  assert.equal(r.code, 1);
  assert.match(r.out, /conseq:200900001 value_rc/);
  r = compareWith('client-overview:v1', edited(c, (rows) => (rows[0].value_rc = String(Number(rows[0].value_rc) + 0.009))));
  assert.equal(r.code, 0, r.out);
});

test('distributor-overview: a portfolio the workbook does not list — the key and the Book’s count both named', () => {
  const c = reference(CASES['distributor-overview:v1']);
  const r = compareWith('distributor-overview:v1', edited(c, (rows) => rows.push({ ...rows[0], portfolio_id: 'conseq:200900099' })));
  assert.equal(r.code, 1);
  assert.match(r.out, /portfolio conseq:200900099: on the book, not in the workbook/);
  assert.match(r.out, /Book: open portfolios: workbook 2 · book 3/);
});

test('sync-run-changes: a changed count off by one is named; a run the reference refuses is not compared', () => {
  const c = reference(CASES['sync-run-changes:v1']);
  let r = compareWith('sync-run-changes:v1', edited(c, (rows) => (rows.find((x) => x.target === 'investment.transaction').changed = '4')));
  assert.equal(r.code, 1);
  assert.match(r.out, /movements changed \(investment\.transaction\): workbook 3 · book 4/);
  r = compareWith('sync-run-changes:v1', edited(c, (rows) => rows.forEach((x) => (x.refused = '1 batch(es) of the run are not committed'))));
  assert.equal(r.code, 2);
  assert.match(r.out, /cannot be compared: 1 batch\(es\) of the run are not committed/);
});

test('sync-run-changes: a correction (reversed) and an SCD2 closed row are changed movements, as the journal counts them; a refused row is not', () => {
  const c = reference(CASES['sync-run-changes:v1']);
  const csv = readFileSync(c, 'utf8');
  // the fixture's two inserted movements, listed as corrections — the journal's effects count each as one `inserted`
  for (const outcome of ['reversed', 'closed']) {
    const r = compareWith('sync-run-changes:v1', csv, [], mutated('sync-run-changes:v1', SST, '<t>inserted</t>', `<t>${outcome}</t>`));
    assert.equal(r.code, 0, `${outcome}: ${r.out}`);
    assert.match(r.out, /3 movements, 61 prices/);
  }
  // …but a refused row is listed and changed nothing
  const r = compareWith('sync-run-changes:v1', csv, [], mutated('sync-run-changes:v1', SST, '<t>inserted</t>', '<t>rejected</t>'));
  assert.equal(r.code, 1, r.out);
  assert.match(r.out, /movements changed \(investment\.transaction\): workbook 1 · book 3/);
});

test('sync-run-changes: a run committed with counts only is refused — the workbook counts rows it cannot list', () => {
  const c = reference(CASES['sync-run-changes:v1']);
  // the Run sheet's "Batches committed with counts only" (a shared "0" with its neighbours) made 2
  const r = compareWith('sync-run-changes:v1', readFileSync(c, 'utf8'), [], mutated('sync-run-changes:v1', SST, '<t>0</t>', '<t>2</t>'));
  assert.equal(r.code, 2, r.out);
  assert.match(r.out, /2 batch\(es\) of the run were committed with counts only/);
});

test('sync-run-changes: 0 = 0 holds nothing — a run that changed no movement and no price is refused; a 0 against 3 is still a difference', () => {
  const quiet = mutated(
    'sync-run-changes:v1',
    SST, '<t>inserted</t>', '<t>unchanged</t>',
    SST, '<t>updated</t>', '<t>unchanged</t>',
    'xl/worksheets/sheet4.xml', '(<c r="A5"[^>]*><v>)61\\.0(</v>)', '\\g<1>0.0\\2',
  );
  const c = reference(CASES['sync-run-changes:v1']);
  let r = compareWith('sync-run-changes:v1', edited(c, (rows) => rows.forEach((x) => (x.changed = '0'))), [], quiet);
  assert.equal(r.code, 2, r.out);
  assert.match(r.out, /changed no movement and no price/);
  // the journal says it changed 3 movements and 61 prices; the workbook lists none — a difference, never "nothing to hold"
  r = compareWith('sync-run-changes:v1', readFileSync(c, 'utf8'), [], quiet);
  assert.equal(r.code, 1, r.out);
  assert.match(r.out, /movements changed \(investment\.transaction\): workbook 0 · book 3/);
});

// ── the script, end to end ─────────────────────────────────────────────────────────────────────────────────────

function harness(template, opts = {}) {
  const c = CASES[template];
  const dir = mkdtempSync(path.join(tmpdir(), 'ov-fp-sh-'));
  const answers = {
    [`${c.name === 'statement' ? 'statement' : c.name === 'client-overview' || c.name === 'distributor-overview' ? 'overview' : c.name}-reference.sql`]:
      opts.reference ?? readFileSync(reference(c), 'utf8'),
    'evolution-reference.sql': readFileSync(path.join(EVO, 'reference-200900001-month.csv'), 'utf8'),
  };
  writeFileSync(path.join(dir, 'answers.json'), JSON.stringify(answers));
  writeFileSync(
    path.join(dir, 'psql'),
    `#!/usr/bin/env node
const { readFileSync, appendFileSync } = require('node:fs');
const args = process.argv.slice(2);
appendFileSync(${JSON.stringify(path.join(dir, 'psql-calls'))}, JSON.stringify(args) + '\\n');
${opts.psqlFails ? `process.stderr.write(${JSON.stringify(opts.psqlFails)}); process.exit(1);` : ''}
const file = args[args.indexOf('-f') + 1].split('/').pop();
process.stdout.write(JSON.parse(readFileSync(${JSON.stringify(path.join(dir, 'answers.json'))}, 'utf8'))[file]);
`,
    { mode: 0o755 },
  );
  const calls = [];
  const server = createServer((req, res) => {
    calls.push({ method: req.method, url: req.url, authorization: req.headers.authorization });
    const json = (status, body) => {
      res.writeHead(status, { 'content-type': 'application/json' });
      res.end(JSON.stringify(body));
    };
    if (req.method === 'POST' && req.url === '/api/reports/render') {
      let body = '';
      req.on('data', (x) => (body += x));
      req.on('end', () => {
        calls.at(-1).body = JSON.parse(body);
        if (opts.refusal) return json(opts.refusal.status, opts.refusal.body);
        json(200, { artifactId: 'a-3', fileName: `${c.name}-${AS_OF}.xlsx` });
      });
      return;
    }
    if (req.method === 'GET' && req.url.startsWith('/api/reports/artifacts/a-3')) {
      res.writeHead(200, { 'content-type': 'application/octet-stream' });
      res.end(readFileSync(workbook(c)));
      return;
    }
    json(404, { code: 'NOT_FOUND', message: req.url });
  });
  return { dir, calls, server, psqlCalls: () => readFileSync(path.join(dir, 'psql-calls'), 'utf8').trim().split('\n').map((l) => JSON.parse(l)) };
}

async function run(template, opts = {}) {
  const h = harness(template, opts);
  await new Promise((r) => h.server.listen(0, '127.0.0.1', r));
  try {
    const { port } = h.server.address();
    const result = await new Promise((resolve) => {
      const proc = spawn('bash', [SCRIPT, template, ...(opts.args ?? [])], {
        cwd: h.dir,
        // fd 3 only for a test that hands the token over a pipe — on Linux an extra stdio pipe is a socket pair whose
        // read side errors (ECONNRESET) once the child exits, so it also gets an error handler below
        stdio: opts.fd3 !== undefined ? ['pipe', 'pipe', 'pipe', 'pipe'] : ['pipe', 'pipe', 'pipe'],
        env: {
          ...process.env,
          PATH: `${h.dir}:${process.env.PATH}`,
          IE_FP_BFF: `http://127.0.0.1:${port}`,
          IE_FP_BEARER: 'tok-1',
          IE_FP_DSN: 'postgresql://fake/entry',
          IE_FP_AS_OF: AS_OF,
          ...CASES[template].env,
          ...(opts.env ?? {}),
        },
      });
      if (opts.fd3 !== undefined) {
        proc.stdio[3].on('error', () => {});
        proc.stdio[3].end(opts.fd3);
      }
      let out = '';
      proc.stdout.on('data', (x) => (out += x));
      proc.stderr.on('data', (x) => (out += x));
      proc.on('close', (code) => resolve({ code, out }));
    });
    return { ...result, h };
  } finally {
    h.server.close();
  }
}

test('the script renders through studio-bff with the bearer, runs the reference with its -v, and agrees — price sheet', async () => {
  const { code, out, h } = await run('price-sheet:v1');
  assert.equal(code, 0, out);
  const render = h.calls.find((c) => c.method === 'POST');
  assert.deepEqual(render.body, { templateId: 'price-sheet:v1', args: { months: '6', as_of: AS_OF } });
  assert.equal(render.authorization, 'Bearer tok-1');
  const psql = h.psqlCalls()[0];
  assert.ok(psql.includes('as_of=2026-06-15') && psql.includes('months=6'), JSON.stringify(psql));
  assert.match(out, /the price-sheet:v1 matches the book/);
});

test('the statement: its sheets against its reference, then its Evolution against v2’s', async () => {
  const { code, out, h } = await run('portfolio-statement:v1');
  assert.equal(code, 0, out);
  const files = h.psqlCalls().map((a) => a[a.indexOf('-f') + 1].split('/').pop());
  assert.deepEqual(files, ['statement-reference.sql', 'evolution-reference.sql']);
  assert.match(out, /agree — 12 periods/);
});

test('a render the renderer refuses fails, with its code and sentence', async () => {
  const { code, out } = await run('client-overview:v1', { refusal: { status: 502, body: { code: 'incomplete_ledger', message: 'the ledger of conseq:1 holds more units' } } });
  assert.equal(code, 1);
  assert.match(out, /render failed: HTTP 502 incomplete_ledger — the ledger of conseq:1/);
});

test('a workbook that differs from the book fails, naming the difference', async () => {
  const c = reference(CASES['distributor-overview:v1']);
  const { code, out } = await run('distributor-overview:v1', { reference: edited(c, (rows) => (rows[1].value_rc = String(Number(rows[1].value_rc) + 1))) });
  assert.equal(code, 1);
  assert.match(out, /value_rc: workbook .* · book/);
  assert.match(out, /does not match the book/);
});

test('the run’s change log on a role that cannot read the journal: refused, naming IE_FP_JOURNAL_DSN', async () => {
  const { code, out } = await run('sync-run-changes:v1', { psqlFails: 'ERROR:  permission denied for table journal_batch\n' });
  assert.equal(code, 1);
  assert.match(out, /IE_FP_JOURNAL_DSN/);
});

test('a template the script does not know, and a missing parameter, are refused before anything is rendered', async () => {
  let r = await run('price-sheet:v1', { env: { IE_FP_MONTHS: '25' } });
  assert.equal(r.code, 1);
  assert.match(r.out, /IE_FP_MONTHS must be 1\.\.24/);
  assert.equal(r.h.calls.length, 0);
  r = await run('client-overview:v1', { env: { IE_FP_CLIENT: '' } });
  assert.equal(r.code, 1);
  assert.match(r.out, /IE_FP_CLIENT is required/);
});

// ── S4.4: the evidence, and the journal from a laptop ──────────────────────────────────────────────────────────────

test('--save prints the book’s answer as a fingerprint block and writes it where IE_FP_SAVE_DIR points', async () => {
  const save = mkdtempSync(path.join(tmpdir(), 'ov-fp-save-'));
  const { code, out } = await run('client-overview:v1', { args: ['--save'], env: { IE_FP_SAVE_DIR: save } });
  assert.equal(code, 0, out);
  const slug = `client-overview-v1-conseq-8809001-${AS_OF}.csv`;
  const want = readFileSync(reference(CASES['client-overview:v1']), 'utf8');
  assert.equal(readFileSync(path.join(save, slug), 'utf8'), want);
  const block = out.split(`-----BEGIN FINGERPRINT ${slug}-----\n`)[1]?.split('-----END FINGERPRINT-----')[0];
  assert.equal(block, want);
});

test('--save into this (public) repository is refused, and nothing is written there', async () => {
  const inside = path.resolve(here, '../../fingerprints-must-not-exist');
  const { code, out } = await run('price-sheet:v1', { args: ['--save'], env: { IE_FP_SAVE_DIR: inside } });
  assert.equal(code, 1);
  assert.match(out, /inside this repository, which is PUBLIC/);
  assert.throws(() => readFileSync(inside));
});

test('an unknown option is refused before anything is rendered', async () => {
  const r = await run('price-sheet:v1', { args: ['--keep'] });
  assert.equal(r.code, 1);
  assert.match(r.out, /unknown option '--keep'/);
  assert.equal(r.h.calls.length, 0);
});

test('IE_FP_JOURNAL_PSQL: the run’s reference goes to that psql’s stdin, after a line that makes the session read-only', async () => {
  const dir = mkdtempSync(path.join(tmpdir(), 'ov-fp-jpsql-'));
  const fake = path.join(dir, 'jpsql');
  writeFileSync(
    fake,
    `#!/usr/bin/env node
const { readFileSync, writeFileSync } = require('node:fs');
writeFileSync(${JSON.stringify(path.join(dir, 'argv.json'))}, JSON.stringify(process.argv.slice(2)));
writeFileSync(${JSON.stringify(path.join(dir, 'stdin.sql'))}, readFileSync(0, 'utf8'));
process.stdout.write(readFileSync(${JSON.stringify(reference(CASES['sync-run-changes:v1']))}, 'utf8'));
`,
    { mode: 0o755 },
  );
  // the DSN psql would be asked for, if the prefix were ignored, fails — so a pass proves the prefix ran
  const { code, out } = await run('sync-run-changes:v1', { psqlFails: 'should not be called\n', env: { IE_FP_JOURNAL_PSQL: `${fake} --extra` } });
  assert.equal(code, 0, out);
  const argv = JSON.parse(readFileSync(path.join(dir, 'argv.json'), 'utf8'));
  assert.equal(argv[0], '--extra');
  assert.ok(argv.includes('run=run-20260930-0530') && argv.at(-1) === '-', JSON.stringify(argv));
  const sql = readFileSync(path.join(dir, 'stdin.sql'), 'utf8');
  assert.match(sql, /^SET default_transaction_read_only = on;\n/);
  assert.ok(sql.includes(readFileSync(path.resolve(here, '../sql/sync-run-changes-reference.sql'), 'utf8')));
});

test('IE_FP_BEARER_FILE: the token read from a pipe is the one studio-bff sees', async () => {
  const { code, out, h } = await run('distributor-overview:v1', { fd3: 'tok-pipe\n', env: { IE_FP_BEARER: '', IE_FP_BEARER_FILE: '/dev/fd/3' } });
  assert.equal(code, 0, out);
  assert.ok(h.calls.length > 0 && h.calls.every((c) => c.authorization === 'Bearer tok-pipe'), JSON.stringify(h.calls.map((c) => c.authorization)));
});
