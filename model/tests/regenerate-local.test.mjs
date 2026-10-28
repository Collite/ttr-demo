// scripts/regenerate-local.sh (SO-demo P0·S0.2 T1, contracts §1, D-21) — the regenerate job's logic, which
// regenerate.yml runs as-is. Mocked: a throwaway git checkout with this repo's justfile and lock, and stub CLIs
// that write a known resolved-packages.json, archive and Golem layout — no toolchain. Asserts the exit codes the
// workflow branches on (0 nothing stale, 10 rebuilt), the loop guard (a second run on the committed result is 0), and
// that model/ is never touched outside model/layouts/agent/ (the Golem's layouts, the build's own folder). Needs git, just and python3 (the gate has all three).
// Run: node --test model/tests/regenerate-local.test.mjs.

import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { chmod, cp, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const script = path.join(root, 'scripts/regenerate-local.sh');

let work;
let checkout;
const git = (...args) => execFileSync('git', ['-C', checkout, ...args], { encoding: 'utf-8' });

// A stub CLI: finds `--out <file>` among its arguments and writes $STUB_CONTENT there, plus $STUB_MODEL_WRITE
// (a path under the checkout) when set — the misbehaving toolchain the model guard is for.
const STUB = `#!/usr/bin/env bash
set -euo pipefail
out=""
while [ $# -gt 0 ]; do [ "$1" = "--out" ] && out="$2"; shift; done
printf '%s' "\${STUB_CONTENT:?}" > "$out"
if [ -n "\${STUB_MODEL_WRITE:-}" ]; then echo "// touched" >> "\${STUB_MODEL_WRITE}"; fi
`;

// The gen-layouts stub: writes $STUB_CONTENT into the Golem's layout, as `just gen-layouts` rewrites the folder.
const LAYOUTS_STUB = `#!/usr/bin/env bash
set -euo pipefail
printf '%s' "\${STUB_CONTENT:?}" > model/layouts/agent/agent_x.ttrg
`;

function run(env = {}) {
  return spawnSync('bash', [script, checkout], {
    encoding: 'utf-8',
    env: {
      ...process.env,
      RESOLVE_CLI: path.join(work, 'stub'),
      LEXICON_CLI: path.join(work, 'stub'),
      LAYOUTS_CLI: path.join(work, 'layouts-stub'),
      STUB_CONTENT: 'v1',
      ...env,
    },
  });
}

before(async () => {
  work = await mkdtemp(path.join(tmpdir(), 'regenerate-local-'));
  checkout = path.join(work, 'hartland');
  await mkdir(path.join(checkout, 'model/er'), { recursive: true });
  await mkdir(path.join(checkout, 'model/layouts/agent'), { recursive: true });
  await mkdir(path.join(checkout, 'generated'), { recursive: true });
  await mkdir(path.join(checkout, 'scripts'), { recursive: true });
  for (const f of ['justfile', 'toolchain.lock', 'scripts/toolchain-lock.py', 'scripts/cn-model-snapshot.mjs']) {
    await cp(path.join(root, f), path.join(checkout, f));
  }
  await writeFile(path.join(checkout, 'model/er/one.ttrm'), 'model er\npackage hartland\n');
  await writeFile(path.join(checkout, 'model/layouts/agent/agent_x.ttrg'), 'v0');
  await writeFile(path.join(checkout, 'generated/resolved-packages.json'), 'v0');
  await writeFile(path.join(checkout, 'generated/lexicon.tar.zst'), 'v0');
  // build-lexicon also packs model/ (scripts/cn-model-snapshot.mjs, the real script: it needs no toolchain).
  await writeFile(path.join(checkout, 'generated/model.tar.zst'), 'v0');
  await writeFile(path.join(work, 'stub'), STUB);
  await chmod(path.join(work, 'stub'), 0o755);
  await writeFile(path.join(work, 'layouts-stub'), LAYOUTS_STUB);
  await chmod(path.join(work, 'layouts-stub'), 0o755);
  execFileSync('git', ['init', '-q', checkout]);
  git('-c', 'user.name=t', '-c', 'user.email=t@t', 'add', '.');
  git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-m', 'base');
});

after(async () => {
  await rm(work, { recursive: true, force: true });
});

test('R1 — a stale generated/ is rebuilt and left in the tree: exit 10, only generated/ and the Golem\'s layouts changed', async () => {
  const r = run();
  assert.equal(r.status, 10, r.stderr + r.stdout);
  assert.deepEqual(git('status', '--porcelain').split('\n').filter(Boolean).sort(), [
    ' M generated/lexicon.tar.zst',
    ' M generated/model.tar.zst',
    ' M generated/resolved-packages.json',
    ' M model/layouts/agent/agent_x.ttrg',
  ]);
  assert.equal(await readFile(path.join(checkout, 'generated/lexicon.tar.zst'), 'utf-8'), 'v1');
  git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-am', 'regenerate');
});

test('R2 — the loop guard: run again on the committed result → exit 0, "nothing stale", the tree clean', () => {
  const r = run();
  assert.equal(r.status, 0, r.stderr + r.stdout);
  assert.match(r.stdout, /nothing stale/);
  assert.equal(git('status', '--porcelain'), '');
});

test('R3 — a toolchain that writes into model/ outside the Golem\'s layouts is refused (exit 1) — the job never commits authored model/**', () => {
  const r = run({ STUB_CONTENT: 'v2', STUB_MODEL_WRITE: path.join(checkout, 'model/er/one.ttrm') });
  assert.equal(r.status, 1, r.stderr + r.stdout);
  assert.match(r.stderr, /model\//);
  git('checkout', '-q', '--', '.');
});

test('R4 — a ../tatrman not at the lock\'s ref is refused (exit 2) before anything is built', () => {
  const tatrman = path.join(work, 'tatrman'); // the checkout's side-by-side toolchain
  execFileSync('git', ['init', '-q', tatrman]);
  execFileSync('git', ['-C', tatrman, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '--allow-empty', '-m', 'not the pinned tag']);
  const env = { ...process.env };
  delete env.RESOLVE_CLI;
  delete env.LEXICON_CLI;
  delete env.LAYOUTS_CLI;
  const r = spawnSync('bash', [script, checkout], { encoding: 'utf-8', env });
  assert.equal(r.status, 2, r.stderr + r.stdout);
  assert.match(r.stderr, /toolchain\.lock/);
  assert.equal(git('status', '--porcelain'), '');
});
