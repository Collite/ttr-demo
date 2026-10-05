// IA-P4b·S4b.2 — `scripts/lib/income_labels.py`: the classification table the fingerprint references classify the book
// with (IA-C55), read strictly — the synced table accepted, every shape it does not know refused by line, and the
// normalisation the renderer's (kantheon `IncomeLabels.normalize`, held to the same case list).
//
// Run: node --test scripts/tests/income-labels.test.mjs        (no database; in CI's script suites)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const READER = path.resolve(here, '../lib/income_labels.py');
const SYNCED = path.resolve(here, '../../model/investment/income-labels.yaml');
const CASES = path.resolve(here, 'fixtures/evolution/income-labels.cases.json');

const py = (...args) => {
  try {
    return { code: 0, out: execFileSync('python3', [READER, ...args], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }) };
  } catch (e) {
    return { code: e.status, out: `${e.stdout ?? ''}${e.stderr ?? ''}` };
  }
};

function table(text) {
  const file = path.join(mkdtempSync(path.join(tmpdir(), 'labels-')), 'income-labels.yaml');
  writeFileSync(file, text);
  return file;
}

const GOOD = `# a comment
version: 2
labels:
  - label: "vstupní poplatek"
    class: fee
    note: "the entry fee"
  - label: "nákup"
    leg: cash
    class: other   # a trailing comment
  - label: "vyrovnání zůstatku"
    match: prefix
    class: other
`;

test('IL.1 — the table synced from kantheon reads whole: a version and every label', () => {
  const r = py('check', SYNCED);
  assert.equal(r.code, 0, r.out);
  assert.match(r.out, /^version \d+, \d+ labels$/m);
  const n = Number(/, (\d+) labels/.exec(r.out)[1]);
  assert.ok(n >= 10, `only ${n} labels — the table this repo classifies with is the renderer's, all of it`);
  // and every entry reaches the relation, in the file's order
  const sql = py('sql', SYNCED).out;
  assert.equal((sql.match(/\(\d+, '/g) ?? []).length, n);
  assert.match(sql, /^VALUES \(1, 'vstupní poplatek', CAST\(NULL AS TEXT\), 'prefix', 'fee'\)/);
});

test('IL.2 — the relation carries each entry\'s order, label, leg, match and class, quotes escaped', () => {
  const sql = py('sql', table(GOOD)).out.trim();
  assert.equal(
    sql,
    "VALUES (1, 'vstupní poplatek', CAST(NULL AS TEXT), 'exact', 'fee'), (2, 'nákup', 'cash', 'exact', 'other'), " +
      "(3, 'vyrovnání zůstatku', CAST(NULL AS TEXT), 'prefix', 'other')",
  );
  const quoted = py('sql', table('version: 1\nlabels:\n  - label: "o\'neil"\n    class: other\n')).out.trim();
  assert.match(quoted, /'o''neil'/);
  const empty = py('sql', table('version: 1\nlabels: []\n')).out.trim();
  assert.match(empty, /WHERE FALSE$/, 'an empty table is an empty relation, not a syntax error');
});

test('IL.3 — every shape the reader does not know is REFUSED, naming the line — never half-read', () => {
  const refusals = {
    'version: 0\nlabels: []\n': /`version` must be a whole number/,
    'labels: []\n': /no `version`/,
    'version: 1\n': /no `labels`/,
    'version: 1\nlabels:\n  - { label: "x", class: fee }\n': /:3: expected `key: value`/,
    'version: 1\nlabels:\n  - label: \'x\'\n    class: fee\n': /double-quoted string or a bare word only/,
    'version: 1\nlabels:\n  - label: "x"\n    class: fee\n    colour: red\n': /unknown keys \['colour'\]/,
    'version: 1\nlabels:\n  - label: "Vstupní poplatek"\n    class: fee\n': /not normalised — .* write 'vstupní poplatek'/,
    'version: 1\nlabels:\n  - label: "x"\n    class: rebate\n': /class 'rebate'/,
    'version: 1\nlabels:\n  - label: "x"\n    leg: security\n    class: fee\n': /leg 'security'/,
    'version: 1\nlabels:\n  - label: "x"\n    match: regex\n    class: fee\n': /match 'regex'/,
    'version: 1\nlabels:\n  - label: "x"\n    class: fee\n  - label: "x"\n    class: other\n': /'x' listed twice/,
    // R16: one entry per label, match kind and leg — a leg-less entry covers both legs, so a leg-restricted second one
    // overlaps it (the file's order would pick); the same leg twice too
    'version: 1\nlabels:\n  - label: "x"\n    class: fee\n  - label: "x"\n    leg: cash\n    class: other\n': /'x' listed twice — one entry per label and leg/,
    'version: 1\nlabels:\n  - label: "x"\n    leg: cash\n    class: fee\n  - label: "x"\n    class: other\n': /'x' listed twice/,
    'version: 1\nlabels:\n  - label: "x"\n    leg: cash\n    class: fee\n  - label: "x"\n    leg: cash\n    class: other\n': /'x' listed twice/,
    'version: 1\nlabels:\n  - label: "x\n    class: fee\n': /does not close/,
    'version: 1\nlabels:\n   - label: "x"\n    class: fee\n': /indented two spaces/,
    'version: 1\nnotes: x\nlabels: []\n': /unknown top-level key 'notes'/,
    'version: 1\nlabels:\n  - label: ""\n    class: fee\n': /no `label`/,
  };
  for (const [text, why] of Object.entries(refusals)) {
    const r = py('check', table(text));
    assert.notEqual(r.code, 0, `accepted:\n${text}`);
    assert.match(r.out, why, `${JSON.stringify(text)} → ${r.out}`);
  }
  // a missing file is a refusal too, never an empty table
  assert.notEqual(py('sql', '/no/such/income-labels.yaml').code, 0);
});

test('IL.4 — the normalisation is the renderer\'s: kantheon\'s case list, every case', () => {
  const cases = JSON.parse(readFileSync(CASES, 'utf8'));
  assert.ok(cases.length >= 10);
  for (const c of cases) {
    if (!c.label.trim()) continue; // argv cannot carry a blank label meaningfully; the SQL side checks it
    assert.equal(py('normalize', c.label).out.replace(/\n$/, ''), c.normalized, JSON.stringify(c.label));
  }
});

test('IL.5 — one label may have an entry per LEG, and an exact entry beside a prefix one — those do not overlap (R16)', () => {
  const ok = py(
    'check',
    table(
      'version: 1\nlabels:\n  - label: "x"\n    leg: cash\n    class: fee\n  - label: "x"\n    leg: external-flow\n    class: other\n' +
        '  - label: "y"\n    class: fee\n  - label: "y"\n    match: prefix\n    class: other\n',
    ),
  );
  assert.equal(ok.code, 0, ok.out);
  assert.match(ok.out, /version 1, 4 labels/);
});

test('IL.6 — whitespace is Unicode White_Space, as the renderer\'s `(?U)\\s`: NEL folds, a file separator and a BOM do not', () => {
  // Python's own `\\s` (and str.strip) would also take U+001C…U+001F, which Kotlin's does not
  assert.equal(py('normalize', 'Vklad\u0085Ident. 20240115 1').out.replace(/\n$/, ''), 'vklad');
  assert.equal(py('normalize', 'vklad\u001cx').out.replace(/\n$/, ''), 'vklad\u001cx');
  assert.equal(py('normalize', '\u001cvklad').out.replace(/\n$/, ''), '\u001cvklad');
  assert.equal(py('normalize', '\ufeffvklad').out.replace(/\n$/, ''), '\ufeffvklad');
});
