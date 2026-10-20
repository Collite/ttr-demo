// AU-hartland-P2 · S2.2 — the eight recipes as `.ttrp` (D-25, D-80, D-85; `17` §3–§4, `04` H-3/H-5).
// What ttr-core can check is checked here, through the toolchain's own CLI: `ttrp explain` (the recipe skeleton, from
// the parse, and — from grammar/v0.16.1, ttr-core P1 — the RecipeChecker's section: the mode verdict and each
// context's class) and `ttrp check` (the checker's findings). Every recipe checks with zero diagnostics and is mode
// per-candidate; its parameters are declared, used and the package's; every route of its switch is wired; the four
// `17` recipes ARE ttr-core's shared fixtures.
// What the pinned toolchain cannot check yet is `todo`, naming the ttr-core phase that brings it: the recipe build and
// its manifest (P2 — `ttrp build` refuses a recipe with TTRP-REC-099 until then).
// Run: node --test automation/tests/recipes.test.mjs (from the hartland repo root).

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { existsSync } from 'node:fs';
import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import { promisify } from 'node:util';
import { hartlandRoot } from '../../model/tests/project-harness.mjs';

const run = promisify(execFile);
const tatrmanPackages = process.env.TATRMAN_PACKAGES ?? path.resolve(hartlandRoot, '../tatrman/packages');
// `TTRP_CLI` overrides the sibling-checkout default (the `TTR_LEXICON_CLI` precedent of lexicon/tests/area.test.mjs).
const CLI = process.env.TTRP_CLI ?? path.join(tatrmanPackages, 'kotlin/ttrp-cli/build/install/ttrp-cli/bin/ttrp-cli');
// Skipped locally without a built CLI; in CI (the model gate builds it) a missing CLI is a failure, not a skip.
const cliMissing = !existsSync(CLI) && !process.env.CI && 'ttrp CLI not built — ./gradlew :packages:kotlin:ttrp-cli:installDist in the tatrman checkout';
const FIXTURES = path.join(tatrmanPackages, 'kotlin/ttrp-frontend/src/test/resources/recipes');

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
    const { stdout, stderr } = await run(CLI, [command, file], { maxBuffer: 4 << 20 });
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

const explained = cliMissing ? {} : Object.fromEntries(await Promise.all(Object.entries(recipeFiles).map(async ([n, f]) => [n, await explain(f)])));
const sources = Object.fromEntries(await Promise.all(Object.entries(recipeFiles).map(async ([n, f]) => [n, await readFile(f, 'utf-8')])));

test('S2.2 T1 — every recipe parses and checks with zero diagnostics (`ttrp explain`)', { skip: cliMissing }, () => {
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
// Compared without comments and blank lines. No difference is left: from grammar/v0.16.1 the fixtures carry
// monitor_inbound's `when:` (S2.2 T3) and decide_return's `days(365)` (ttr-core P1's F3), as these recipes do.
const FIXTURE_DELTAS = {};
const lines = (text) => code(text).split('\n').map((l) => l.trimEnd()).filter((l) => l.trim() !== '').join('\n');

for (const name of ['release_order', 'decide_return', 'monitor_inbound', 'settle']) {
  const fixture = path.join(FIXTURES, `${name}.ttrp`);
  test(`S2.2 T2/T3 — ${name} is ttr-core's shared fixture (comments aside)`, { skip: !existsSync(fixture) && !process.env.CI && 'no ttr-core checkout' }, async () => {
    let want = lines(await readFile(fixture, 'utf-8'));
    for (const [re, to] of FIXTURE_DELTAS[name] ?? []) want = want.replace(re, to);
    assert.equal(lines(sources[name]), want);
  });
}

// ── the RecipeChecker (ttr-core P1, grammar/v0.16.1) ──────────────────────────────────────────────────────────────
test('S2.2 T1 — zero diagnostics from the RecipeChecker (`ttrp check`)', { skip: cliMissing }, async () => {
  for (const [name, file] of Object.entries(recipeFiles)) {
    const r = await ttrp('check', file);
    assert.equal(r.code, 0, `${name}:\n${r.out}`);
    assert.equal(r.out.trim(), '', `${name}: findings`);
  }
});

// Every recipe is per-candidate, ops/no_run_since too. The task list expected `set-level, batch` for it, but its one
// context groups each deployment's runs by the deployment, the key, so its verdict depends on that deployment alone
// (06 A-5). Its program runs it hourly in batch either way.
test('S2.2 T1 — the mode verdicts: every recipe per-candidate, no context set-level', { skip: cliMissing }, () => {
  for (const [name, r] of Object.entries(explained)) {
    assert.match(r.out, /^checker · mode per-candidate · /m, `${name}: the mode verdict`);
    const contexts = [...r.out.matchAll(/^ {2}context (\w+) .*\b(lookup|per-candidate|set-level)\b/gm)];
    for (const m of contexts) assert.notEqual(m[2], 'set-level', `${name}: context ${m[1]}`);
  }
});

// ── what the pinned toolchain cannot check yet ────────────────────────────────────────────────────────────────────
test.todo('S2.2 T1 — `ttrp build --json` per recipe: the manifest\'s mode, `kinds` ([sql] + [builtin] where a sugar lowers to one) and parameters — ttr-core P2 (S2.3)');
