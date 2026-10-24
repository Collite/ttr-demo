// AU-hartland P2: source contracts, checker verdicts, and reproducible manifest-v3 bundles.
// The recipe CLI and its shared fixtures follow [ttrp], independently of the model gate's JS toolchain.
// Ops remain authored and tested; their deployments await the Server's real automation.ops package.
// Run after `just toolchain-ttrp` and `just build-recipes`; CI requires the CLI.

import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { existsSync, realpathSync } from 'node:fs';
import { createHash } from 'node:crypto';
import os from 'node:os';
import { readFile, readdir, mkdtemp, rm } from 'node:fs/promises';
import path from 'node:path';
import { promisify } from 'node:util';
import { hartlandRoot } from '../../model/tests/project-harness.mjs';

const run = promisify(execFile);
const TTRP_SRC = process.env.TTRP_SRC ?? path.join(hartlandRoot, '.modeler/toolchains/ttrp');
const CLI = process.env.TTRP_CLI ?? path.join(TTRP_SRC, 'packages/kotlin/ttrp-cli/build/install/ttrp-cli/bin/ttrp-cli');
const cliMissing = !process.env.CI && !process.env.TTRP_CLI && !process.env.TTRP_SRC && !existsSync(CLI)
  && 'run `just toolchain-ttrp` (or set TTRP_CLI / TTRP_SRC)';
const FIXTURES = path.join(TTRP_SRC, 'packages/kotlin/ttrp-frontend/src/test/resources/recipes');
if (!cliMissing) {
  assert.ok(existsSync(CLI), `recipe CLI missing: ${CLI}`);
  assert.ok(existsSync(FIXTURES), `recipe fixtures missing: ${FIXTURES}; set TTRP_SRC`);
}

const automationDir = path.join(hartlandRoot, 'automation');
async function findRecipes(dir) {
  const out = [];
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory() && e.name !== 'stub' && e.name !== 'tests') out.push(...await findRecipes(p));
    else if (e.isFile() && e.name.endsWith('.ttrp')) out.push(p);
  }
  return out;
}
const recipeFiles = Object.fromEntries((await findRecipes(automationDir)).map((p) => [path.basename(p, '.ttrp'), p]));

// The eight recipes of contracts §4 (the programs name them — automation/tests/package.test.mjs).
const RECIPES = ['decide_return', 'monitor_inbound', 'no_run_since', 'obligation_due_passed', 'release_order', 'reorder_proposals', 'settle', 'winback'];

test('S2.2 — the eight recipes of contracts §4 are in the package, one folder each (ops/ for the two ops recipes)', () => {
  assert.deepEqual(Object.keys(recipeFiles).sort(), RECIPES);
  for (const [name, file] of Object.entries(recipeFiles)) {
    const rel = path.relative(automationDir, file);
    assert.ok(rel === `${name}/${name}.ttrp` || rel === `ops/${name}/${name}.ttrp`, rel);
  }
});

/** `ttrp <command> <file>` → { code, out } (stdout + stderr, the ANTLR and SLF4J notices dropped). */
async function ttrp(command, file) {
  try {
    const { stdout, stderr } = await run('python3', [path.join(hartlandRoot, 'scripts/build-recipes.py'), '--cli', CLI, '--command', command, '--recipe', file], { maxBuffer: 4 << 20 });
    return { code: 0, out: clean(stdout + stderr) };
  } catch (e) {
    return { code: e.code ?? 1, out: clean(`${e.stdout ?? ''}${e.stderr ?? ''}`) };
  }
}
const explain = (file) => ttrp('explain', file);
const clean = (s) => s.split('\n').filter((l) => !l.startsWith('ANTLR ') && !l.startsWith('SLF4J(')).join('\n');

/** The skeleton `ttrp explain` prints for a recipe: header, routes (+ the else target), wirings. */
function skeleton(out) {
  const lines = out.split('\n');
  const head = lines.find((l) => l.startsWith('recipe · '));
  const parameters = /· parameters (.*)$/.exec(head ?? '')?.[1].split(',').map((s) => s.trim()) ?? [];
  const routes = [];
  let elseTarget;
  for (const l of lines) {
    const m = /^ {2}route (\S+)(?:\s+-> (\S+))?/.exec(l);
    if (!m) continue;
    if (m[1] === 'else') elseTarget = m[2];
    else routes.push(m[1]);
  }
  const wirings = [];
  const at = lines.indexOf('actions');
  for (const l of at < 0 ? [] : lines.slice(at + 1)) {
    const m = /^ {2}(.+?)\s+-> (\w+) \{/.exec(l);
    if (m) wirings.push({ routes: m[1].split(',').map((s) => s.trim()), action: m[2], when: /\} when /.test(l) });
  }
  return { head, parameters, routes, elseTarget, wirings };
}

const checkableFiles = Object.entries(recipeFiles).filter(([n]) => n !== 'no_run_since');
const explained = cliMissing ? {} : Object.fromEntries(await Promise.all(checkableFiles.map(async ([n, f]) => [n, await explain(f)])));
const sources = Object.fromEntries(await Promise.all(Object.entries(recipeFiles).map(async ([n, f]) => [n, await readFile(f, 'utf-8')])));

test('S2.2 T1 — the seven checkable recipes parse and check with zero diagnostics (`ttrp explain`)', { skip: cliMissing }, () => {
  for (const [name, r] of Object.entries(explained)) {
    assert.equal(r.code, 0, `${name}:\n${r.out}`);
    assert.match(r.out, /^recipe · key /m, `${name}: the skeleton`);
    assert.match(r.out, /^checker · mode /m, `${name}: the checker's section`);
    assert.doesNotMatch(r.out, /TTRP-[A-Z]+-\d+/, `${name}: a finding`);
  }
});

/** The source without `//` comments (none of the recipes writes `//` inside a string). */
const code = (text) => text.replace(/\/\/[^\n]*/g, '');

test('S2.2 T1 — `parameters:` is what the toolchain reads, and every `:name` the recipe binds is declared or `:as_of`', { skip: cliMissing }, () => {
  for (const [name, r] of Object.entries(explained)) {
    const { parameters } = skeleton(r.out);
    const declared = /^\s*parameters:\s*\[([^\]]*)\]/m.exec(code(sources[name]))?.[1].split(',').map((s) => s.trim()).filter(Boolean) ?? [];
    assert.deepEqual(parameters, declared, `${name}: explain vs source`);
    const bound = new Set([...code(sources[name]).matchAll(/(?<![\w:]):([a-z_][a-z0-9_]*)/g)].map((m) => m[1]));
    bound.delete('as_of');
    assert.deepEqual([...bound].sort(), [...declared].sort(), `${name}: bound :names = parameters (REC-020/021, the text half)`);
  }
});

test('S2.2 T1 — every parameter a recipe declares is a `def parameter` of the package (REC-021, the name half)', async () => {
  const pkg = await readFile(path.join(automationDir, 'automation.ttrm'), 'utf-8');
  const defined = new Set([...pkg.matchAll(/^def parameter\s+(\w+)/gm)].map((m) => m[1]));
  for (const [name, src] of Object.entries(sources)) {
    const declared = /^\s*parameters:\s*\[([^\]]*)\]/m.exec(code(src))?.[1].split(',').map((s) => s.trim()).filter(Boolean) ?? [];
    for (const p of declared) assert.ok(defined.has(p), `${name}: parameter ${p}`);
  }
});

test('S2.2 T1 — every route of every switch is wired (REC-003, through the skeleton); `else: none` needs none', { skip: cliMissing }, () => {
  for (const [name, r] of Object.entries(explained)) {
    const { routes, elseTarget, wirings } = skeleton(r.out);
    const emitted = [...routes, ...(elseTarget && elseTarget !== 'none' ? [elseTarget] : [])];
    assert.ok(emitted.length > 0, `${name}: routes`);
    const wired = new Set(wirings.flatMap((w) => w.routes.map((x) => x.split('.')[1])));
    const unwired = wired.has('all') ? [] : emitted.filter((x) => !wired.has(x));
    assert.deepEqual(unwired, [], `${name}: unwired routes`);
    for (const w of wirings) for (const x of w.routes) assert.ok(x === `${x.split('.')[0]}.all` || emitted.includes(x.split('.')[1]), `${name}: ${x} wires no route`);
  }
});

test('S2.2 T1 — every wired action is a `def action` of the package (REC-001, the name half)', { skip: cliMissing }, async () => {
  const pkg = await readFile(path.join(automationDir, 'automation.ttrm'), 'utf-8');
  const defined = new Set([...pkg.matchAll(/^def action\s+(\w+)/gm)].map((m) => m[1]));
  for (const [name, r] of Object.entries(explained)) {
    for (const w of skeleton(r.out).wirings) assert.ok(defined.has(w.action), `${name}: action ${w.action}`);
  }
});

test('S2.2 T3 — monitor_inbound\'s two expects on `complete` are conditional on the way (`when:`, 17 §4.2 / §5)', { skip: cliMissing }, () => {
  const expects = skeleton(explained.monitor_inbound.out).wirings.filter((w) => w.action === 'expect');
  assert.deepEqual(expects.map((w) => [w.routes.join(','), w.when]), [['inbound.complete', true], ['inbound.complete', true]]);
  assert.match(sources.monitor_inbound, /kind: credit_note,\s+due: working_days\(:settlement\) \}\s+when: way = "refund_after_return"/);
  assert.match(sources.monitor_inbound, /kind: replacement,\s+due: working_days\(:settlement\) \}\s+when: way = "exchange"/);
});

// ── the four `17` recipes ARE ttr-core's shared fixtures ──────────────────────────────────────────────────────────
// Compared without comments, blank lines and indentation (P3 derives H-1 from Markdown). No difference is left: from grammar/v0.16.1 the fixtures carry
// monitor_inbound's `when:` (S2.2 T3) and decide_return's `days(365)` (ttr-core P1's F3), as these recipes do.
const FIXTURE_DELTAS = {};
const lines = (text) => code(text).split('\n').map((l) => l.trim()).filter((l) => l !== '').join('\n');

for (const name of ['release_order', 'decide_return', 'monitor_inbound', 'settle']) {
  const fixture = path.join(FIXTURES, `${name}.ttrp`);
  test(`S2.2 T2/T3 — ${name} is ttr-core's shared fixture (comments aside)`, { skip: cliMissing }, async () => {
    let want = lines(await readFile(fixture, 'utf-8'));
    for (const [re, to] of FIXTURE_DELTAS[name] ?? []) want = want.replace(re, to);
    assert.equal(lines(sources[name]), want);
  });
}

// ── the RecipeChecker (ttr-core P1, grammar/v0.16.1) ──────────────────────────────────────────────────────────────
test('S2.2 T1 — zero diagnostics from the RecipeChecker (`ttrp check`)', { skip: cliMissing }, async () => {
  for (const [name, file] of checkableFiles) {
    const r = await ttrp('check', file);
    assert.equal(r.code, 0, `${name}:\n${r.out}`);
    assert.equal(r.out.trim(), '', `${name}: findings`);
  }
});

// Every recipe is per-candidate, ops/no_run_since too. The task list expected `set-level, batch` for it, but its one
// context groups each deployment's runs by the deployment, the key, so its verdict depends on that deployment alone
// (06 A-5). Its program runs it hourly in batch either way.
test('S2.2 T1 — the mode verdicts: the seven checkable recipes per-candidate, no context set-level', { skip: cliMissing }, () => {
  for (const [name, r] of Object.entries(explained)) {
    assert.match(r.out, /^checker · mode per-candidate · /m, `${name}: the mode verdict`);
    const contexts = [...r.out.matchAll(/^ {2}context (\w+) .*\b(lookup|per-candidate|set-level)\b/gm)];
    for (const m of contexts) assert.notEqual(m[2], 'set-level', `${name}: context ${m[1]}`);
  }
});

// S2.3: the ops recipes remain authored, but no_run_since cannot lower row-dependent date arithmetic yet.
test('S2.3 — no_run_since has the documented TYP-001 refusal and no deployment', { skip: cliMissing }, async () => {
  const r = await ttrp('check', recipeFiles.no_run_since);
  assert.notEqual(r.code, 0);
  assert.match(r.out, /TTRP-TYP-001/);
  const world = code(await readFile(path.join(automationDir, 'worlds/demo.ttrm'), 'utf8'));
  assert.doesNotMatch(world, /program:\s*(?:no_run_since_hourly|obligation_due_passed_hourly)/);
});

const bundledNames = RECIPES.filter((n) => !['no_run_since', 'obligation_due_passed'].includes(n));
const sha = (bytes) => 'sha256:' + createHash('sha256').update(bytes).digest('hex');

async function tree(dir, prefix = '') {
  const files = {};
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const rel = prefix + e.name;
    if (e.isDirectory()) Object.assign(files, await tree(path.join(dir, e.name), rel + '/'));
    else files[rel] = sha(await readFile(path.join(dir, e.name)));
  }
  return files;
}

test('S2.3 — every deployment and process step has a committed recipe bundle', async () => {
  const programs = code(await readFile(path.join(automationDir, 'programs.ttrm'), 'utf8'));
  const mapping = Object.fromEntries([...programs.matchAll(/def program\s+(\w+)\s*\{\s*recipe:\s*(\w+)/g)].map((m) => [m[1], m[2]]));
  const world = code(await readFile(path.join(automationDir, 'worlds/demo.ttrm'), 'utf8'));
  for (const m of world.matchAll(/program:\s*(\w+)/g)) {
    assert.ok(mapping[m[1]], m[1]);
    assert.ok(bundledNames.includes(mapping[m[1]]), m[1] + ': deferred recipe must not deploy');
    assert.ok(existsSync(path.join(path.dirname(recipeFiles[mapping[m[1]]]), mapping[m[1]] + '.bundle/manifest.json')), m[1]);
  }
});

// One full rebuild per pass, shared by all six comparisons. A second pass is opt-in for investigation.
const reproOutputs = [];
if (!cliMissing) {
  const passes = Number(process.env.RECIPES_REPRO_PASSES ?? 1);
  assert.ok(Number.isInteger(passes) && passes >= 1, 'RECIPES_REPRO_PASSES must be a positive integer');
  for (let pass = 0; pass < passes; pass++) {
    const out = await mkdtemp(path.join(os.tmpdir(), 'hartland-bundle-'));
    reproOutputs.push(out);
    await run('python3', [path.join(hartlandRoot, 'scripts/build-recipes.py'), '--cli', CLI, '--out', out], { maxBuffer: 8 << 20 });
  }
}
after(async () => { for (const out of reproOutputs) await rm(out, { recursive: true, force: true }); });

test('S2.3 — disk bundles equal exactly the six active recipes', async () => {
  const actual = [];
  for (const e of await readdir(automationDir, { withFileTypes: true })) {
    if (e.isDirectory()) for (const b of await readdir(path.join(automationDir, e.name))) {
      if (b.endsWith('.bundle')) actual.push(b.slice(0, -7));
    }
  }
  assert.deepEqual(actual.sort(), [...bundledNames].sort());
});

for (const name of bundledNames) {
  test(`S2.3 — ${name}: v3, hashes, golden seeds, catalog references and reproducible builds`, { skip: cliMissing }, async () => {
    const file = recipeFiles[name];
    const committed = path.join(path.dirname(file), name + '.bundle');
    const manifest = JSON.parse(await readFile(path.join(committed, 'manifest.json'), 'utf8'));
    assert.equal(manifest.schemaVersion, 3);
    assert.equal(manifest.recipe.name, name);
    assert.equal(manifest.recipe.mode, 'per-candidate');
    assert.deepEqual(manifest.recipe.kinds, ['sql']);
    for (const kind of ['text', 'values', 'labels']) assert.match(manifest.recipe.fingerprints[kind], /^sha256:[0-9a-f]{64}$/);
    const seeds = (await readdir(path.join(path.dirname(file), 'tests'))).filter((p) => /\.ya?ml$/.test(p)).sort().map((p) => 'tests/' + p);
    assert.deepEqual(manifest.recipe.tests, seeds);
    for (const [rel, hash] of Object.entries(manifest.files)) assert.equal(sha(await readFile(path.join(committed, rel))), hash, rel);
    const entities = new Set(['obligation', 'state_history', 'approvals', name + '_verdict']);
    async function scan(dir) {
      for (const e of await readdir(dir, { withFileTypes: true })) {
        const p = path.join(dir, e.name);
        if (e.isDirectory() && e.name !== 'tests' && e.name !== 'stub') await scan(p);
        else if (e.name.endsWith('.ttrm')) for (const m of (await readFile(p, 'utf8')).matchAll(/def entity\s+(\w+)/g)) entities.add(m[1]);
      }
    }
    await scan(path.join(hartlandRoot, 'model'));
    await scan(path.join(committed, 'catalog'));
    for (const object of manifest.recipe.objectsRead) assert.ok(entities.has(object.split('.').at(-1)), object);
    if (['monitor_inbound', 'settle'].includes(name)) {
      assert.deepEqual([...new Set(manifest.recipe.parts.map((p) => p.storage))].sort(), ['automation_db', 'erp_db']);
      assert.ok(manifest.islands.flatMap((i) => i.outputs).some((o) => o.combine));
    }
    for (const out of reproOutputs) {
      assert.deepEqual(await tree(path.join(out, name, name + '.bundle')), await tree(committed));
    }
  });
}

test('S2.3 — winback SQL selects the highest two bands and excludes recent orders and recent mail', { skip: cliMissing }, async () => {
  const libDir = path.resolve(path.dirname(realpathSync(CLI)), '../lib');
  assert.ok(existsSync(libDir), `recipe CLI library directory missing: ${libDir}`);
  const lib = path.join(libDir, '*');
  const probe = path.join(automationDir, 'tests/WinbackSqlProbe.java');
  const bundle = path.join(automationDir, 'winback/winback.bundle');
  const result = await run('java', ['--class-path', lib, probe, bundle], { maxBuffer: 4 << 20 });
  assert.match(result.stdout, /premium=\[2, 3\]/);
  assert.match(result.stdout, /standard=\[1\]/);
});
