// The gate's shape (SO-demo P0·S0.1 T2–T3, contracts §2, D-28; review-121) — the parts a later edit could quietly
// undo: the job name master's protection requires, the ttr-core ref coming only from toolchain.lock, the toolchain
// cache keyed by the commit, the Kotlin loader built at veles's version and run exactly when the lock says so.
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
const justfileText = await readText('justfile');
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

test('W2 — exactly two ttr-core checkouts, both in the action: the toolchain at the ref, the loader at veles\'s tag', () => {
  const uses = gateSteps.filter((s) => s.uses === './hartland/.github/actions/toolchain');
  assert.equal(uses.length, 1);
  for (const [name, steps] of [['model-gate.yml', gateSteps], ['regenerate.yml', regenSteps]]) {
    assert.deepEqual(steps.filter((s) => s.with?.repository === 'Collite/ttr-core'), [],
      `${name}: a ttr-core checkout of its own bypasses toolchain.lock`);
    assert.ok(!steps.some((s) => /gradlew|pnpm install/.test(s.run ?? '')), `${name}: a toolchain build of its own`);
  }
  const checkouts = actionSteps.filter((s) => s.with?.repository === 'Collite/ttr-core').map((s) => [s.with.path, s.with.ref]);
  assert.deepEqual(checkouts, [
    ['tatrman', '${{ env.TTR_CORE_REF }}'],
    ['ttr-loader', 'grammar/v${{ env.VELES_TTR_METADATA }}'],
  ]);
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

test('W4 — the caches: keyed by the commit (a re-cut tag misses), one path list, builds only on a miss', () => {
  const restores = actionSteps.filter((s) => s.uses?.startsWith('actions/cache/restore@'));
  const saves = actionSteps.filter((s) => s.uses?.startsWith('actions/cache/save@'));
  assert.equal(restores.length, 2);
  assert.equal(saves.length, 2);
  const [restore, loaderRestore] = [restores.find((s) => s.id === 'restore'), restores.find((s) => s.id === 'loader-restore')];
  assert.ok(restore && loaderRestore);
  assert.match(restore.with.key, /\$\{\{ env\.TTR_CORE_SHA \}\}/);
  assert.match(loaderRestore.with.key, /\$\{\{ env\.TTR_LOADER_SHA \}\}/);
  for (const [sha, dir] of [['TTR_CORE_SHA', 'tatrman'], ['TTR_LOADER_SHA', 'ttr-loader']]) {
    const writes = actionSteps.findIndex((s) => new RegExp(`${sha}=\\$\\(git -C ${dir} rev-parse HEAD\\)`).test(s.run ?? ''));
    const checkout = actionSteps.findIndex((s) => s.with?.repository === 'Collite/ttr-core' && s.with.path === dir);
    assert.ok(checkout >= 0 && writes > checkout, `${sha} is written after the ${dir} checkout`);
  }
  // The toolchain's path list lives once, in the env; restore and save both read it.
  for (const s of [restore, saves.find((s) => s.with.key === '${{ steps.restore.outputs.cache-primary-key }}')]) {
    assert.equal(s.with.path, '${{ env.TOOLCHAIN_CACHE_PATHS }}');
  }
  const list = actionSteps.find((s) => /TOOLCHAIN_CACHE_PATHS<<EOF/.test(s.run ?? ''));
  for (const want of ['tatrman/node_modules', 'tatrman/packages/*/node_modules', 'tatrman/packages/*/dist',
    'tatrman/packages/kotlin/*/build/install']) {
    assert.ok(list.run.split('\n').some((l) => l.includes(`'${want}'`)), `cached: ${want}`);
  }
  assert.equal(saves.find((s) => s.with.key === '${{ steps.loader-restore.outputs.cache-primary-key }}')?.with.path,
    loaderRestore.with.path);
  const builds = actionSteps.filter((s) => /gradlew|pnpm install/.test(s.run ?? ''));
  assert.ok(builds.length >= 3);
  for (const s of builds) assert.match(s.if ?? '', /cache-hit != 'true'/, `${s.name}: builds on a hit`);
  assert.ok(!('outputs' in action), 'no cache-hit output: nothing reads it');
});

test('W5 — the Kotlin loader: veles\'s version, stamped, run exactly when the lock says strict-load', () => {
  // Every Gradle line that names the loader stamps the version and builds in ttr-loader/, never in tatrman/.
  const loaderBuilds = actionSteps.filter((s) => /ttr-metadata-cli/.test(s.run ?? ''));
  assert.equal(loaderBuilds.length, 1);
  for (const s of loaderBuilds) {
    assert.match(s.run, /-Pversion="\$VELES_TTR_METADATA"/);
    assert.match(s.run, /--no-configuration-cache/);
    assert.equal(s['working-directory'], 'ttr-loader');
  }
  const recipe = justfileText.split('\nbuild-loader')[1]?.split('\n\n')[0] ?? '';
  assert.match(recipe, /ttr-metadata-cli:installDist/, 'justfile: build-loader builds the loader');
  assert.match(recipe, /-Pversion="\$VELES_TTR_METADATA"/, 'justfile: build-loader stamps the version');
  // Every loader step in the action runs only when asked for AND the lock turns the strict load on.
  const isLoaderStep = (s) => /ttr-loader|TTR_LOADER_SHA|loader-restore/.test(JSON.stringify({ ...s, if: undefined }));
  const loaderSteps = actionSteps.filter(isLoaderStep);
  assert.equal(loaderSteps.length, 5, 'checkout, commit, restore, build, save');
  for (const s of loaderSteps) {
    assert.match(s.if ?? '', /inputs\.with-loader == 'true' && env\.STRICT_LOAD == 'true'/, `${s.name ?? s.uses}`);
  }
  assert.equal(gateSteps.find((s) => s.uses === './hartland/.github/actions/toolchain').with?.['with-loader'], 'true');
  assert.notEqual(regenSteps.find((s) => s.uses === './hartland/.github/actions/toolchain').with?.['with-loader'], 'true',
    'regenerate never pays for the loader');

  const lexicon = gateSteps.findIndex((s) => s.run === 'just check-lexicon');
  const load = gateSteps.findIndex((s) => s.name === 'load with the Kotlin loader');
  assert.ok(lexicon >= 0 && load > lexicon);
  const step = gateSteps[load];
  assert.equal(step.if, "env.STRICT_LOAD == 'true'", 'no other guard: a missing CLI must fail the load');
  assert.match(step.run, /^just load-model\b/);
  // `| tee` under the runner's default `bash -e` (no pipefail) would turn a red load green.
  assert.equal(step.shell, 'bash');
  const notice = gateSteps.find((s) => s.if === "env.STRICT_LOAD != 'true'");
  assert.match(notice?.run ?? '', /::notice title=strict load off::/);
  for (const [name, text] of [['model-gate.yml', gateText], ['action.yml', actionText], ['regenerate.yml', regenText]]) {
    const ifs = [...text.matchAll(/^\s*if:(.*)$/gm)].map((m) => m[1]);
    assert.ok(!ifs.some((c) => /build\/install/.test(c)), `${name}: a step guarded on what a build happened to produce`);
  }
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
