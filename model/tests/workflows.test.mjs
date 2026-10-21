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
const regenText = await readText('.github/workflows/regenerate.yml');
const gate = yaml.load(gateText);
const action = yaml.load(actionText);
const regen = yaml.load(regenText);
const gateSteps = gate.jobs['model-gate'].steps;
const actionSteps = action.runs.steps;
const regenJob = regen.jobs.regenerate;
const regenSteps = regenJob.steps;

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
  for (const [name, text] of [['model-gate.yml', gateText], ['action.yml', actionText], ['regenerate.yml', regenText]]) {
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

// ── regenerate.yml (SO-demo P0·S0.2 T3, contracts §1, D-21) ──────────────────────────────────────────────────────

test('G1 — triggered by the BFF\'s dispatch and by a pull request touching what generated/ is built from', () => {
  assert.ok('workflow_dispatch' in regen.on);
  for (const p of ['model/**', 'modeler.toml', 'lexicon/**']) assert.ok(regen.on.pull_request.paths.includes(p), p);
  assert.deepEqual(regen.permissions, { contents: 'read' }, 'GITHUB_TOKEN stays read-only: the push is the App\'s');
  assert.equal(regen.concurrency['cancel-in-progress'], false, 'the BFF waits for its dispatched run\'s conclusion');
});

test('G2 — the job runs on Studio branches and same-repo pull requests only', () => {
  assert.match(regenJob.if, /startsWith\(github\.ref_name, 'model\/'\)/);
  assert.match(regenJob.if, /startsWith\(github\.ref_name, 'demo\/'\)/);
  assert.match(regenJob.if, /github\.event\.pull_request\.head\.repo\.full_name == github\.repository/);
});

test('G3 — the App token: minted only when the secret is set, read through the job env (a step `if:` cannot read secrets)', () => {
  assert.equal(regenJob.env.STUDIO_APP_ID, '${{ secrets.STUDIO_APP_ID }}');
  const mint = regenSteps.find((s) => s.uses?.startsWith('actions/create-github-app-token@'));
  assert.equal(mint.if, "env.STUDIO_APP_ID != ''");
  const checkout = regenSteps.find((s) => s.uses?.startsWith('actions/checkout@'));
  assert.match(checkout.with.token, /steps\.app-token\.outputs\.token/, 'checked out with the App token, the push is the App\'s');
  assert.equal(checkout.with.ref, '${{ env.BRANCH }}', 'the branch head, not a PR merge commit');
});

test('G4 — the job runs the local dry-run script itself, its exit code read with -e off', () => {
  assert.ok(regenSteps.some((s) => s.uses === './hartland/.github/actions/toolchain'));
  const step = regenSteps.find((s) => /regenerate-local\.sh/.test(s.run ?? ''));
  assert.ok(step);
  const lines = step.run.split('\n').map((l) => l.trim());
  const call = lines.findIndex((l) => /regenerate-local\.sh/.test(l));
  assert.ok(lines.slice(0, call).includes('set +e'), '`run:` is bash -e: exit 10 would end the step');
  assert.match(step.run, /10\)\s*echo "stale=true"/);
  assert.match(step.run, /0\)\s*echo "stale=false"/);
});

test('G5 — the push: only when stale and the App token exists; commits generated/ alone', () => {
  const push = regenSteps.find((s) => /git push/.test(s.run ?? ''));
  assert.match(push.if, /steps\.regen\.outputs\.stale == 'true'/);
  assert.match(push.if, /steps\.app-token\.outputs\.token != ''/);
  const adds = [...push.run.matchAll(/git add ([^\n]+)/g)].map((m) => m[1].trim());
  assert.deepEqual(adds, ['-- generated']);
  assert.match(push.run, /commit -m "regenerate: generated\/ for \$\(git rev-parse --short HEAD\)"/);
  assert.match(push.run, /\[bot\]@users\.noreply\.github\.com/);
  assert.ok(!/\$\{\{/.test(push.run), 'no ${{ }} inside run: — a branch name reaches the shell only through env');
});
