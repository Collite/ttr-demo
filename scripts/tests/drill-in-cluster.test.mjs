// The in-cluster drill's lifting of a `--save`d fingerprint out of the Job's log — without a cluster.
//
// Run: node --test scripts/tests/drill-in-cluster.test.mjs
//
// A fake `kubectl` first on PATH answers every call the drill makes (configmaps, the Job, wait, get, delete) and serves
// a Job log holding a fingerprint block — honouring `--tail=N` the way kubectl does, so a drill that reads only the
// log's tail loses a long block exactly as it would on the estate.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtempSync, readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const SCRIPT = path.resolve(here, '../drill-in-cluster.sh');

/** A Job log: some chatter, a fingerprint block of [rows] CSV rows (plus its header), a verdict line. */
function jobLog(slug, rows) {
  const csv = ['asset_id,day,price', ...Array.from({ length: rows }, (_, i) => `CZ${String(i).padStart(10, '0')},2026-06-30,${100 + i}`)];
  return [
    'running the drill …',
    '  ✓ downloaded 61234 bytes',
    `-----BEGIN FINGERPRINT ${slug}-----`,
    ...csv,
    '-----END FINGERPRINT-----',
    '',
    'the price-sheet:v1 matches the book — as of 2026-06-15',
  ].join('\n') + '\n';
}

function harness(log, { failed = false } = {}) {
  const dir = mkdtempSync(path.join(tmpdir(), 'drill-'));
  writeFileSync(path.join(dir, 'job.log'), log);
  writeFileSync(
    path.join(dir, 'kubectl'),
    `#!/usr/bin/env node
const { readFileSync, appendFileSync } = require('node:fs');
const args = process.argv.slice(2);
appendFileSync(${JSON.stringify(path.join(dir, 'kubectl-calls'))}, JSON.stringify(args) + '\\n');
if (args.includes('apply')) { appendFileSync(${JSON.stringify(path.join(dir, 'applied.yaml'))}, readFileSync(0)); process.exit(0); }
if (args.includes('logs')) {
  const lines = readFileSync(${JSON.stringify(path.join(dir, 'job.log'))}, 'utf8').split('\\n');
  if (lines.at(-1) === '') lines.pop();
  const t = args.find((a) => a.startsWith('--tail='));
  const n = t ? Number(t.slice('--tail='.length)) : -1;
  process.stdout.write((n >= 0 ? lines.slice(-n) : lines).join('\\n') + '\\n');
  process.exit(0);
}
if (args.includes('wait')) {
  // as kubectl does: waiting for \`complete\` on a Job that failed blocks until the timeout (here 40 s, not 600)
  if (${JSON.stringify(failed)} && args.includes('--for=condition=complete')) {
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 40000);
    process.exit(1);
  }
  process.exit(0);
}
if (args.includes('get')) {
  // the Job's counts: a succeeded Job answers \`1/\` (no failures), a failed one \`/1\`; asked for \`succeeded\` alone, '1' or ''
  const both = args.some((a) => a.includes('.status.failed'));
  process.stdout.write(${JSON.stringify(failed)} ? (both ? '/1' : '') : both ? '1/' : '1');
  process.exit(0);
}
if (args.includes('create')) { process.stdout.write('apiVersion: v1\\nkind: ConfigMap\\n'); process.exit(0); }
process.exit(0);
`,
    { mode: 0o755 },
  );
  return dir;
}

function drill(dir, args, env = {}) {
  return new Promise((resolve) => {
    const proc = spawn('bash', [SCRIPT, ...args], {
      cwd: dir,
      // ⛔ a lifted fingerprint goes to a throwaway directory unless a test names its own: the script's default is the
      // PRIVATE project repo beside this checkout, and a fixture block written there reads as a real portfolio's
      env: { ...process.env, IE_FINGERPRINTS_DIR: mkdtempSync(path.join(tmpdir(), 'drill-fp-')), PATH: `${dir}:${process.env.PATH}`, ...env },
    });
    let out = '';
    proc.stdout.on('data', (x) => (out += x));
    proc.stderr.on('data', (x) => (out += x));
    proc.on('close', (code) => resolve({ code, out }));
  });
}

test('a fingerprint block far longer than a few hundred lines is lifted whole — a price sheet of 63 × 24', async () => {
  const slug = 'price-sheet-v1-24-2026-06-15.csv';
  const dir = harness(jobLog(slug, 63 * 24));
  const save = mkdtempSync(path.join(tmpdir(), 'drill-save-'));
  const { code, out } = await drill(dir, ['fingerprint', 'price-sheet:v1', '--save'], { IE_FINGERPRINTS_DIR: save });
  assert.equal(code, 0, out);
  const written = readFileSync(path.join(save, slug), 'utf8').trimEnd().split('\n');
  assert.equal(written.length, 1 + 63 * 24, `written ${written.length} lines`);
  assert.equal(written[0], 'asset_id,day,price');
  assert.match(out, new RegExp(`fingerprint written: .*${slug.replace(/\./g, '\\.')} \\(${63 * 24} rows\\)`));
  // the log was read whole
  const logs = readFileSync(path.join(dir, 'kubectl-calls'), 'utf8').trim().split('\n').map((l) => JSON.parse(l)).find((a) => a.includes('logs'));
  assert.ok(logs.includes('--tail=-1'), JSON.stringify(logs));
});

test('a run asked to --save whose log holds no block fails, and writes nothing', async () => {
  const dir = harness('running the drill …\n✗ the render failed\n');
  const save = mkdtempSync(path.join(tmpdir(), 'drill-save-'));
  const { code, out } = await drill(dir, ['fingerprint', 'price-sheet:v1', '--save'], { IE_FINGERPRINTS_DIR: save });
  assert.equal(code, 1, out);
  assert.match(out, /asked to --save and printed no fingerprint block/);
  assert.deepEqual(readdirSync(save), []);
});

test('a Job that FAILED is reported at once — not after the whole wait for `complete`', async () => {
  const dir = harness(jobLog('price-sheet-v1-24-2026-06-15.csv', 3) + '93 difference(s)\n', { failed: true });
  const started = Date.now();
  const { code, out } = await drill(dir, ['fingerprint', 'price-sheet:v1']);
  const seconds = (Date.now() - started) / 1000;
  assert.notEqual(code, 0, out);
  assert.match(out, /did not succeed/);
  assert.match(out, /93 difference\(s\)/, 'the failed Job\'s log is shown');
  assert.ok(seconds < 30, `the drill took ${seconds} s to notice the failure`);
});


test('IA-P4b · the Job carries the classification table and its reader, and points the evolution reference at them', async () => {
  // the evolution reference classifies fees and income with THIS checkout's synced income-labels.yaml — mounted
  // beside the model file the fingerprint reads, never fetched, never baked into an image
  // a log with no fingerprint block: no --save, so nothing is lifted (and no private repo is needed — CI has none)
  const dir = harness('running the drill …\nthe evolution matches the book\n');
  const { code, out } = await drill(dir, ['fingerprint', 'investment-evolution:v2']);
  assert.equal(code, 0, out);
  const calls = readFileSync(path.join(dir, 'kubectl-calls'), 'utf8').trim().split('\n').map((l) => JSON.parse(l));
  const created = calls.filter((a) => a.includes('create') && a.includes('configmap'));
  const scripts = created.find((a) => a.includes('estate-drill-scripts'));
  const model = created.find((a) => a.includes('estate-drill-model'));
  assert.ok(scripts.some((a) => /^--from-file=income_labels\.py=.*\/lib\/income_labels\.py$/.test(a)), JSON.stringify(scripts));
  assert.ok(model.some((a) => /^--from-file=.*\/model\/investment\/income-labels\.yaml$/.test(a)), JSON.stringify(model));
  const job = readFileSync(path.join(dir, 'applied.yaml'), 'utf8');
  assert.match(job, /\{ name: IE_FP_LABELS, value: \/model\/income-labels\.yaml \}/);
  assert.match(job, /\/scripts\/income_labels\.py \/drill\/lib\//);
  assert.match(job, /bash \/drill\/fingerprint-evolution\.sh/);
});
