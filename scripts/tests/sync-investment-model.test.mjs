// IE-P2·S2.3·T2 — the investment sync is idempotent, stamped, and carries the interpreted face only.
//
// Run: node --test scripts/tests/sync-investment-model.test.mjs
//
// The sync copies `kantheon/packages/investment/model/{db,er,binding,queries}` into
// `model/investment/` here (IE-C27). It is the one place this repo's model is written by a machine,
// and three things about it are load-bearing:
//
//   ⛔ **It must carry the INTERPRETED FACE ONLY.** kantheon's package has two faces in one
//      directory: `model/db er binding queries` (parses) and `model/{book,parties,instruments}.ttrm`
//      (`model book` is not a grammar model code — the parser REJECTS them). S2.1·D1 is what that
//      costs: a rejected file is still READ by anything walking the tree, its `def entity`
//      declarations recovered under a guessed `er` code, and `book.ttrm` sorts before `er/book.ttrm`
//      — so the two facts the Golem reads resolved to the wrong file. Handing veles one of those is
//      how that defect reaches the estate, whatever its own Kotlin loader does with a parse error.
//
//   ⛔ **It must not carry kantheon's test tree.** Those suites import a harness that is not synced,
//      and `just verify-model` here runs `find model -name '*.test.mjs'` — so a copied `tests/`
//      directory does not sit there inertly, it turns this repo's model gate red.
//
//   ⛔ **It must be idempotent and checkable.** A hand-edit in `model/investment/` is a change to a
//      model whose source of truth is another repository; nothing but the stamp can see it.
//
// The recipes are driven through `just --justfile … --working-directory <tmp>`, so every assertion
// below runs against a throwaway destination rather than against this checkout.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, existsSync, readdirSync, statSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, '../..');
const justfile = path.join(repo, 'justfile');

/** The kantheon checkout the sync reads. Overridable so a CI lane can point elsewhere. */
const KANTHEON = process.env.IE_KANTHEON_DIR ?? path.resolve(repo, '../kantheon-ie');

function just(cwd, ...args) {
  return execFileSync('just', ['--justfile', justfile, '--working-directory', cwd, ...args], {
    encoding: 'utf-8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });
}

/** Run a recipe expecting a NON-zero exit; return { status, output }. */
function justFails(cwd, ...args) {
  try {
    just(cwd, ...args);
    return { status: 0, output: '' };
  } catch (e) {
    return { status: e.status ?? -1, output: `${e.stdout ?? ''}${e.stderr ?? ''}` };
  }
}

/** The label case list (R15): a scratch kantheon holds it under `model/tests/`, a fresh destination its copy. */
const CASES = '[{"label": "Vklad", "normalized": "vklad"}]\n';
const CASES_COPY = 'scripts/tests/fixtures/evolution/income-labels.cases.json';

function freshDest() {
  const d = mkdtempSync(path.join(tmpdir(), 'ie-sync-'));
  mkdirSync(path.join(d, 'model'), { recursive: true });
  mkdirSync(path.join(d, path.dirname(CASES_COPY)), { recursive: true });
  writeFileSync(path.join(d, CASES_COPY), CASES);
  execFileSync('git', ['init', '-q'], { cwd: d });
  return d;
}

/** Every file under `dir`, repo-relative, sorted. */
function filesUnder(dir) {
  const out = [];
  const walk = (p, rel) => {
    for (const name of readdirSync(p).sort()) {
      const full = path.join(p, name);
      if (statSync(full).isDirectory()) walk(full, `${rel}${name}/`);
      else out.push(`${rel}${name}`);
    }
  };
  if (existsSync(dir)) walk(dir, '');
  return out.sort();
}

const kantheonPresent = existsSync(path.join(KANTHEON, 'packages/investment/model/db'));

test('T4.0 — the kantheon checkout the sync reads is actually there', () => {
  // ⛔ Not a skip. A sync suite that quietly passes when it cannot find its source proves nothing,
  // and S2.1·D5 is this effort's own instance of that: 14 assertions passed against an empty
  // package. If this fails, set IE_KANTHEON_DIR.
  assert.ok(kantheonPresent, `no investment package at ${KANTHEON} — set IE_KANTHEON_DIR`);
});

test('T4.1 — two runs into a fresh destination leave nothing to commit the second time', () => {
  const dest = freshDest();
  just(dest, 'sync-investment-model', KANTHEON);
  execFileSync('git', ['add', '-A'], { cwd: dest });
  execFileSync('git', ['-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'first sync'], { cwd: dest });

  just(dest, 'sync-investment-model', KANTHEON);
  const dirty = execFileSync('git', ['status', '--porcelain'], { cwd: dest, encoding: 'utf-8' });
  assert.equal(dirty.trim(), '', `the second sync changed something:\n${dirty}`);
});

test('T4.2 — SYNCED-FROM names the source commit and the day it was taken', () => {
  const dest = freshDest();
  just(dest, 'sync-investment-model', KANTHEON);
  const stamp = readFileSync(path.join(dest, 'model/investment/SYNCED-FROM'), 'utf-8');

  const head = execFileSync('git', ['-C', KANTHEON, 'rev-parse', 'HEAD'], { encoding: 'utf-8' }).trim();
  assert.match(stamp, new RegExp(`^source-commit: ${head}$`, 'm'), 'the kantheon HEAD sha');
  assert.match(stamp, /^synced-at: \d{4}-\d{2}-\d{2}$/m, 'an ISO date');
  assert.match(stamp, /^tree-sha256: [0-9a-f]{64}$/m, 'the tree hash check-investment-model recomputes');
});

test('T4.3 — a hand-edited file makes check-investment-model fail, and it says which one', () => {
  const dest = freshDest();
  just(dest, 'sync-investment-model', KANTHEON);
  just(dest, 'check-investment-model'); // clean tree: passes

  const victim = path.join(dest, 'model/investment/db/investment.ttrm');
  writeFileSync(victim, `${readFileSync(victim, 'utf-8')}\n// edited by hand\n`);

  const { status, output } = justFails(dest, 'check-investment-model');
  assert.notEqual(status, 0, 'check-investment-model passed over a hand-edited file');
  assert.match(output, /db\/investment\.ttrm/, `the failure must name the file:\n${output}`);
});

test('T4.4 — the INTERPRETED FACE ONLY: no book layer, no entry/, no kantheon test tree', () => {
  const dest = freshDest();
  just(dest, 'sync-investment-model', KANTHEON);
  const files = filesUnder(path.join(dest, 'model/investment'));

  assert.ok(files.length > 4, `the sync produced almost nothing: ${files.join(', ')}`);

  // S2.1·D1 — the three files the parser rejects, by name.
  for (const rejected of ['book.ttrm', 'parties.ttrm', 'instruments.ttrm']) {
    assert.ok(
      !files.some((f) => path.basename(f) === rejected && !f.startsWith('er/')),
      `${rejected} reached the estate — it does not parse, and a rejected file is still READ`,
    );
  }
  assert.ok(!files.some((f) => f.startsWith('entry/')), 'the entry face (DDL, apply programs) is not the estate\'s');
  assert.ok(!files.some((f) => f.includes('tests/')), 'kantheon\'s test tree would turn `just verify-model` red here');
  assert.ok(!files.some((f) => f.endsWith('.test.mjs') || f.endsWith('.mjs')), 'no JavaScript belongs in a served model');

  // And what it MUST carry: the four interpreted directories — and the classification table the fingerprint
  // references read (IA-P4b·S4b.2), the one top-level file.
  for (const kind of ['db/', 'er/', 'binding/', 'queries/']) {
    assert.ok(files.some((f) => f.startsWith(kind)), `the sync carries no ${kind}`);
  }
  assert.ok(files.includes('income-labels.yaml'), 'the sync carries no income-labels.yaml (IA-C55)');
  assert.deepEqual(files.filter((f) => !f.includes('/')).sort(), ['SYNCED-FROM', 'income-labels.yaml']);
  assert.ok(files.includes('SYNCED-FROM'), 'no stamp');
});

test('T4.4b — a DIRTY source is refused: the stamp may not name a commit it is not', () => {
  // The recipe's own first real run wrote `source-commit: 526f50a` over a tree that carried
  // uncommitted rewrites. `check-investment-model` would have been green over content nobody could
  // reproduce from the named commit — a drift check confirming a lie. The refusal is the fix; the
  // positive case (T4.1–T4.5) is what proves a CLEAN source still syncs.
  const dest = freshDest();
  const scratch = mkdtempSync(path.join(tmpdir(), 'ie-kantheon-'));
  execFileSync('git', ['init', '-q'], { cwd: scratch });
  const model = path.join(scratch, 'packages/investment/model');
  for (const kind of ['db', 'er', 'binding', 'queries']) {
    mkdirSync(path.join(model, kind), { recursive: true });
    writeFileSync(path.join(model, kind, 'x.ttrm'), 'package investment\n');
  }
  writeFileSync(path.join(model, 'income-labels.yaml'), 'version: 1\nlabels: []\n');
  mkdirSync(path.join(model, 'tests'));
  writeFileSync(path.join(model, 'tests', 'income-labels.cases.json'), CASES);
  execFileSync('git', ['add', '-A'], { cwd: scratch });
  execFileSync('git', ['-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'seed'], { cwd: scratch });
  just(dest, 'sync-investment-model', scratch); // clean: allowed

  writeFileSync(path.join(model, 'db/x.ttrm'), 'package investment\n// uncommitted\n');
  const { status, output } = justFails(dest, 'sync-investment-model', scratch);
  assert.notEqual(status, 0, 'the sync stamped a dirty source');
  assert.match(output, /uncommitted changes/, output);

  // …and it can still be forced, deliberately, with the commit marked.
  just(dest, 'sync-investment-model', scratch, 'true');
  const stamp = readFileSync(path.join(dest, 'model/investment/SYNCED-FROM'), 'utf-8');
  assert.match(stamp, /^source-commit: [0-9a-f]{40}\+dirty$/m, 'a forced sync must say so in the stamp');
});

test('T4.5 — every synced .ttrm declares `package investment`, and the db layer is `dbo`', () => {
  // The namespace is not cosmetic here (S2.3·D1b): the door resolves unqualified DB identifiers in
  // the fixed namespace `dbo`, and dispatch routes this estate's plans by `db.dbo.investment_*`.
  // A sync that carried a `public` db layer would give veles a model whose every query fails to
  // validate AND whose plans route to the default connection — the TPC-DS one.
  const dest = freshDest();
  just(dest, 'sync-investment-model', KANTHEON);
  const root = path.join(dest, 'model/investment');
  const ttrm = filesUnder(root).filter((f) => f.endsWith('.ttrm'));
  assert.ok(ttrm.length >= 4, `only ${ttrm.length} .ttrm files synced`);
  for (const f of ttrm) {
    const text = readFileSync(path.join(root, f), 'utf-8');
    assert.match(text, /^package investment$/m, `${f} does not declare \`package investment\``);
  }
  const db = readFileSync(path.join(root, 'db/investment.ttrm'), 'utf-8');
  assert.match(db, /^model db schema dbo$/m, 'the db layer must declare `dbo`, not the physical schema');
});

// ── the destination is EXACTLY the source, and nothing in it is invisible to the hash ─────────────
//
// The cases below sync from a throwaway kantheon with the real package's SHAPE — four kind
// directories each carrying a `tests/`, the entry face beside them — so they do not depend on what
// the sibling kantheon checkout holds today.

function commitAll(cwd, message) {
  execFileSync('git', ['add', '-A'], { cwd });
  execFileSync('git', ['-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', message], { cwd });
}

function scratchKantheon() {
  const dir = mkdtempSync(path.join(tmpdir(), 'ie-kantheon-'));
  execFileSync('git', ['init', '-q'], { cwd: dir });
  const model = path.join(dir, 'packages/investment/model');
  for (const kind of ['db', 'er', 'binding', 'queries']) {
    mkdirSync(path.join(model, kind, 'tests'), { recursive: true });
    writeFileSync(path.join(model, kind, `${kind}.ttrm`), `package investment\n// ${kind}\n`);
    writeFileSync(path.join(model, kind, 'tests', `${kind}.test.mjs`), '// kantheon-only\n');
  }
  writeFileSync(path.join(model, 'book.ttrm'), 'model book\n');
  writeFileSync(path.join(model, 'income-labels.yaml'), 'version: 1\nlabels: []\n');
  mkdirSync(path.join(model, 'tests'));
  writeFileSync(path.join(model, 'tests', 'income-labels.cases.json'), CASES);
  mkdirSync(path.join(model, 'entry'));
  writeFileSync(path.join(model, 'entry', 'programs.json'), '{}\n');
  commitAll(dir, 'seed');
  return { dir, model };
}

const inv = (dest, ...rest) => path.join(dest, 'model/investment', ...rest);

test('T4.6 — a re-sync removes a stray top-level file and a receiver-side tests/ directory', () => {
  // `rsync --delete` per kind directory could not see either: a top-level file is outside every
  // kind directory, and an excluded `tests/` on the receiver is protected from deletion. Both
  // survived a re-sync and were then re-certified by the new stamp.
  const k = scratchKantheon();
  const dest = freshDest();
  just(dest, 'sync-investment-model', k.dir);
  const clean = filesUnder(inv(dest));

  writeFileSync(inv(dest, 'NOTES.md'), 'stray\n');
  mkdirSync(inv(dest, 'er/tests'));
  writeFileSync(inv(dest, 'er/tests/local.test.mjs'), '// stray\n');
  writeFileSync(inv(dest, 'er/extra.ttrm'), 'package investment\n');

  just(dest, 'sync-investment-model', k.dir);
  assert.deepEqual(filesUnder(inv(dest)), clean, 'the re-synced tree is not exactly the source');
});

test('T4.7 — a file named SYNCED-FROM below the top level is not invisible to the hash', () => {
  const k = scratchKantheon();
  const dest = freshDest();
  just(dest, 'sync-investment-model', k.dir);
  writeFileSync(inv(dest, 'er/SYNCED-FROM'), 'hidden\n');

  const { status, output } = justFails(dest, 'check-investment-model');
  assert.notEqual(status, 0, 'check-investment-model passed over a file only its NAME hid');
  assert.match(output, /er\/SYNCED-FROM/, output);
});

test('T4.8 — a symlink under model/investment fails check-investment-model, and is named', () => {
  // `find -type f` does not see a symlink, so the hash did not either: a link to any file, anywhere,
  // passed the drift check.
  const k = scratchKantheon();
  const dest = freshDest();
  just(dest, 'sync-investment-model', k.dir);
  symlinkSync('../db/db.ttrm', inv(dest, 'er/linked.ttrm'));

  const { status, output } = justFails(dest, 'check-investment-model');
  assert.notEqual(status, 0, 'check-investment-model passed over a symlink');
  assert.match(output, /er\/linked\.ttrm/, output);
});

test('T4.9 — a symlink in the SOURCE is refused, and the destination is left untouched', () => {
  const k = scratchKantheon();
  symlinkSync('../db/db.ttrm', path.join(k.model, 'er', 'linked.ttrm'));
  commitAll(k.dir, 'a link');
  const dest = freshDest();

  const { status, output } = justFails(dest, 'sync-investment-model', k.dir);
  assert.notEqual(status, 0, 'the sync copied a symlink');
  assert.match(output, /er\/linked\.ttrm/, output);
  assert.ok(!existsSync(inv(dest)), 'a refused sync still wrote the destination');
});

test('T4.10 — a hand-edit plus a re-stamp passes the self-hash; check-investment-model-source catches it', () => {
  const k = scratchKantheon();
  const dest = freshDest();
  just(dest, 'sync-investment-model', k.dir);
  just(dest, 'check-investment-model-source', k.dir); // clean: passes

  // kantheon moves on. The comparison is against the STAMPED commit, not the checkout's HEAD.
  writeFileSync(path.join(k.model, 'db', 'db.ttrm'), 'package investment\n// a later commit\n');
  commitAll(k.dir, 'later');
  just(dest, 'check-investment-model-source', k.dir);

  const victim = inv(dest, 'queries', 'queries.ttrm');
  writeFileSync(victim, `${readFileSync(victim, 'utf-8')}// edited by hand\n`);
  const sha = just(dest, '_investment-tree-sha').trim();
  const stamp = inv(dest, 'SYNCED-FROM');
  writeFileSync(stamp, readFileSync(stamp, 'utf-8').replace(/^tree-sha256: .*$/m, `tree-sha256: ${sha}`));
  just(dest, 'check-investment-model'); // the self-hash is satisfied — which is exactly its limit

  const { status, output } = justFails(dest, 'check-investment-model-source', k.dir);
  assert.notEqual(status, 0, 'a hand-edit that re-stamped itself passed the source comparison');
  assert.match(output, /queries\/queries\.ttrm/, `the failure must name the file:\n${output}`);
});

test('T4.11 — a +dirty stamp names no commit, so the source comparison refuses it', () => {
  const k = scratchKantheon();
  const dest = freshDest();
  writeFileSync(path.join(k.model, 'db', 'db.ttrm'), 'package investment\n// uncommitted\n');
  just(dest, 'sync-investment-model', k.dir, 'true');

  const { status, output } = justFails(dest, 'check-investment-model-source', k.dir);
  assert.notEqual(status, 0, 'a dirty stamp was compared against a commit that does not hold it');
  assert.match(output, /dirty/i, output);
});

test('T4.12 — a source without income-labels.yaml is refused, and the destination is left untouched', () => {
  // IA-P4b·S4b.2: the fingerprint references classify the book with the synced table. A sync that silently
  // dropped it would leave the references reading last month's table — or none — under a fresh stamp.
  const k = scratchKantheon();
  const dest = freshDest();
  just(dest, 'sync-investment-model', k.dir);
  const before = filesUnder(inv(dest));
  execFileSync('git', ['rm', '-q', path.join(k.model, 'income-labels.yaml')], { cwd: k.dir });
  commitAll(k.dir, 'no table');
  const { status, output } = justFails(dest, 'sync-investment-model', k.dir);
  assert.notEqual(status, 0, 'a sync with no classification table succeeded');
  assert.match(output, /income-labels\.yaml is missing/, output);
  assert.deepEqual(filesUnder(inv(dest)), before, 'the refused sync touched the destination');
});

test('T4.13 — the label case list kept OUTSIDE model/investment is compared with the stamped commit too (R15)', () => {
  // the sync does not carry it (a test file, not model), so nothing else would see the copy drift from kantheon's:
  // the reference's SQL and income_labels.py would stay green on a list the renderer no longer satisfies
  const k = scratchKantheon();
  const dest = freshDest();
  just(dest, 'sync-investment-model', k.dir);
  assert.match(just(dest, 'check-investment-model-source', k.dir), /income-labels\.cases\.json is exactly kantheon/);

  // kantheon's list moves on in a LATER commit: the stamp still names the old one, whose list the copy is
  writeFileSync(path.join(k.model, 'tests', 'income-labels.cases.json'), '[]\n');
  commitAll(k.dir, 'later cases');
  just(dest, 'check-investment-model-source', k.dir);

  // the copy edited here: refused, and named — while model/investment itself still compares clean
  writeFileSync(path.join(dest, CASES_COPY), '[{"label": "Vklad", "normalized": "x"}]\n');
  let r = justFails(dest, 'check-investment-model-source', k.dir);
  assert.equal(r.status, 3, r.output);
  assert.match(r.output, /income-labels\.cases\.json is NOT kantheon [0-9a-f]+:packages\/investment\/model\/tests\/income-labels\.cases\.json/);
  assert.match(r.output, /model\/investment is exactly kantheon/, 'the model comparison still runs and reports');

  // the copy gone: refused too, never skipped
  execFileSync('rm', [path.join(dest, CASES_COPY)]);
  r = justFails(dest, 'check-investment-model-source', k.dir);
  assert.equal(r.status, 3, r.output);
  assert.match(r.output, /income-labels\.cases\.json is missing/);
});
