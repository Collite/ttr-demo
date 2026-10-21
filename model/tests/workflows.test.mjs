// The gate's shape (SO-demo P0·S0.1 T2–T3, contracts §2, D-28) — the parts a later edit could quietly undo:
// the job name master's protection requires, the ttr-core ref coming only from toolchain.lock, the toolchain
// cache keyed by that ref, and the Kotlin-loader step guarded until the pinned ref ships its CLI.
// Static: parses the YAML, runs nothing. Run: node --test model/tests/workflows.test.mjs.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

// js-yaml borrowed from the sibling tatrman checkout, as model/queries/tests/queries.test.mjs does.
const tatrmanPackages = process.env.TATRMAN_PACKAGES ?? path.resolve(root, '../tatrman/packages');
const yaml = await import(
  path.resolve(tatrmanPackages, '../node_modules/.pnpm/js-yaml@4.1.1/node_modules/js-yaml/dist/js-yaml.mjs')
);

const readText = (rel) => readFile(path.join(root, rel), 'utf-8');
const gateText = await readText('.github/workflows/model-gate.yml');
const actionText = await readText('.github/actions/toolchain/action.yml');
const gate = yaml.load(gateText);
const action = yaml.load(actionText);
const gateSteps = gate.jobs['model-gate'].steps;
const actionSteps = action.runs.steps;

test('W1 — the job is still `model-gate`: the required status check on master (#85) is that name', () => {
  assert.deepEqual(Object.keys(gate.jobs), ['model-gate']);
});

test('W2 — the gate builds no toolchain of its own: one toolchain action, no second ttr-core checkout', () => {
  const uses = gateSteps.filter((s) => s.uses === './hartland/.github/actions/toolchain');
  assert.equal(uses.length, 1);
  const ownCheckout = gateSteps.filter((s) => s.with?.repository === 'Collite/ttr-core');
  assert.deepEqual(ownCheckout, [], 'a ttr-core checkout in the gate bypasses toolchain.lock');
  assert.ok(!gateSteps.some((s) => /gradlew|pnpm install/.test(s.run ?? '')), 'a toolchain build in the gate');
});

test('W3 — the ttr-core ref comes from toolchain.lock and is written nowhere else', () => {
  const read = actionSteps.findIndex((s) => /scripts\/toolchain-lock\.py/.test(s.run ?? ''));
  const checkout = actionSteps.findIndex((s) => s.with?.repository === 'Collite/ttr-core');
  assert.ok(read >= 0 && checkout > read, 'the lock is read before the checkout');
  assert.match(actionSteps[read].run, /GITHUB_ENV/);
  assert.equal(actionSteps[checkout].with.ref, '${{ env.TTR_CORE_REF }}');
  for (const [name, text] of [['model-gate.yml', gateText], ['action.yml', actionText]]) {
    const code = text.split('\n').filter((l) => !/^\s*#/.test(l)).join('\n');
    assert.doesNotMatch(code, /grammar\/v\d/, `${name}: a grammar ref outside toolchain.lock`);
  }
});

test('W4 — the toolchain cache: keyed by the ref, the same paths restored and saved, builds only on a miss', () => {
  const restore = actionSteps.find((s) => s.uses?.startsWith('actions/cache/restore@'));
  const save = actionSteps.find((s) => s.uses?.startsWith('actions/cache/save@'));
  assert.ok(restore && save);
  assert.match(restore.with.key, /\$\{\{ env\.TTR_CORE_REF \}\}/);
  assert.equal(save.with.key, '${{ steps.restore.outputs.cache-primary-key }}');
  assert.equal(save.with.path, restore.with.path);
  for (const want of ['tatrman/node_modules', 'tatrman/packages/*/dist', 'tatrman/packages/kotlin/*/build/install']) {
    assert.ok(restore.with.path.split('\n').includes(want), `cached: ${want}`);
  }
  const builds = actionSteps.filter((s) => /gradlew|pnpm install/.test(s.run ?? ''));
  assert.ok(builds.length >= 2);
  for (const s of builds) assert.match(s.if ?? '', /cache-hit != 'true'/, `${s.name}: builds on a hit`);
});

test('W5 — the Kotlin loader: built and run only once the pinned ref has the CLI, after check-lexicon', () => {
  const build = actionSteps.find((s) => /ttr-metadata-cli:installDist/.test(s.run ?? ''));
  assert.ok(build, 'the action builds ttr-metadata-cli');
  assert.match(build.if, /hashFiles\('tatrman\/packages\/kotlin\/ttr-metadata-cli\/build\.gradle\.kts'\)/);
  assert.ok(!/ttr-metadata-cli/.test(actionSteps.find((s) => /ttr-lexicon-cli/.test(s.run ?? '')).run),
    'in the lexicon step, an unknown Gradle task fails the build before the module exists');

  const lexicon = gateSteps.findIndex((s) => s.run === 'just check-lexicon');
  const load = gateSteps.findIndex((s) => s.name === 'load with the Kotlin loader');
  assert.ok(lexicon >= 0 && load > lexicon);
  const step = gateSteps[load];
  assert.match(step.if, /hashFiles\('tatrman\/packages\/kotlin\/ttr-metadata-cli\/build\/install\/\*\*'\)/);
  assert.match(step.run, /^just load-model\b/);
  // `| tee` under the runner's default `bash -e` (no pipefail) would turn a red load green.
  assert.equal(step.shell, 'bash');
});
