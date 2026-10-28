// scripts/regenerate-push.sh (SO-demo P0·S0.2, review-121 R9) — regenerate.yml's push step: commit the rebuilt
// generated/ and push it to the branch, and when a save moved the branch during the build, regenerate on the new head
// instead of failing the run. Mocked: a local bare repo as `origin`, shallow clones as the CI checkout and as the
// Studio's saves, and a stub toolchain whose archive is derived from the model's content (so a model edit moves it,
// as W-4 says the real one does). Needs git, just and python3. Run: node --test model/tests/regenerate-push.test.mjs.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { appendFile, chmod, cp, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const BRANCH = 'model/u/1';
const ID = ['-c', 'user.name=t', '-c', 'user.email=t@t'];

// The stub CLI: writes a digest of model/'s content to its `--out` (just runs recipes in the checkout).
const STUB = `#!/usr/bin/env bash
set -euo pipefail
out=""
while [ $# -gt 0 ]; do [ "$1" = "--out" ] && out="$2"; shift; done
find model -type f | sort | xargs cat | sha256sum | cut -c1-16 > "$out"
`;
const built = (model) => `${createHash('sha256').update(model).digest('hex').slice(0, 16)}\n`;

// A fresh origin with the branch at a head whose generated/ is current, and helpers over it.
async function fixture() {
  const work = await mkdtemp(path.join(tmpdir(), 'regenerate-push-'));
  const origin = path.join(work, 'origin.git');
  const stub = path.join(work, 'stub');
  await writeFile(stub, STUB);
  await chmod(stub, 0o755);
  // LAYOUTS_CLI `true`: the Golem's layouts are left as they are here (regenerate-local.test.mjs covers them).
  const env = { ...process.env, RESOLVE_CLI: stub, LEXICON_CLI: stub, LAYOUTS_CLI: 'true', BOT_NAME: 'bot[bot]', BOT_EMAIL: '1+bot[bot]@users.noreply.github.com' };
  delete env.GH_TOKEN;
  const git = (dir, ...args) => execFileSync('git', ['-C', dir, ...args], { encoding: 'utf-8' }).trim();

  execFileSync('git', ['init', '-q', '--bare', origin]);
  const seed = path.join(work, 'seed');
  for (const d of ['model/er', 'generated', 'scripts']) await mkdir(path.join(seed, d), { recursive: true });
  const scripts = ['toolchain-lock.py', 'regenerate-local.sh', 'regenerate-push.sh', 'cn-model-snapshot.mjs'].map((s) => `scripts/${s}`);
  for (const f of ['justfile', 'toolchain.lock', ...scripts]) await cp(path.join(root, f), path.join(seed, f));
  const model0 = 'model er\npackage hartland\n';
  await writeFile(path.join(seed, 'model/er/one.ttrm'), model0);
  await writeFile(path.join(seed, 'generated/resolved-packages.json'), built(model0));
  await writeFile(path.join(seed, 'generated/lexicon.tar.zst'), built(model0));
  // build-lexicon also packs model/ (the real script, no toolchain): seed it current, as the lexicon is.
  execFileSync('node', [path.join(seed, 'scripts/cn-model-snapshot.mjs')], { stdio: 'ignore' });
  execFileSync('git', ['init', '-q', seed]);
  git(seed, ...ID, 'add', '.');
  git(seed, ...ID, 'commit', '-q', '-m', 'base');
  git(seed, 'push', '-q', origin, `HEAD:refs/heads/${BRANCH}`);

  let n = 0;
  const clone = (name = `c${++n}`) => {
    const dir = path.join(work, name);
    execFileSync('git', ['clone', '-q', '--depth', '1', '--branch', BRANCH, `file://${origin}`, dir]);
    return dir;
  };
  // A Studio save: a model edit committed and pushed from its own clone (generated/ left stale, as a save leaves it).
  const save = async (line) => {
    const dir = clone();
    await appendFile(path.join(dir, 'model/er/one.ttrm'), `// ${line}\n`);
    git(dir, ...ID, 'commit', '-q', '-am', `save: ${line}`);
    git(dir, 'push', '-q', 'origin', `HEAD:refs/heads/${BRANCH}`);
    return git(dir, 'rev-parse', 'HEAD');
  };
  const run = (dir, script, args = [], extra = {}) =>
    spawnSync('bash', [path.join(dir, 'scripts', script), ...args], { cwd: dir, encoding: 'utf-8', env: { ...env, ...extra } });
  const head = () => git(origin, 'rev-parse', `refs/heads/${BRANCH}`);
  const show = (rev, file) => git(origin, 'show', `${rev}:${file}`);
  return { work, origin, git, clone, save, run, head, show, done: () => rm(work, { recursive: true, force: true }) };
}

// The CI checkout after a save: cloned, regenerated (exit 10), not yet pushed.
async function builtCheckout(f) {
  await f.save('the save the dispatch was for');
  const ci = f.clone('ci');
  const r = f.run(ci, 'regenerate-local.sh');
  assert.equal(r.status, 10, r.stderr + r.stdout);
  return ci;
}

test('P1 — the branch moved during the build: regenerated on the new head and pushed', async () => {
  const f = await fixture();
  try {
    const ci = await builtCheckout(f);
    const moved = await f.save('a save during the build');
    const r = f.run(ci, 'regenerate-push.sh', [BRANCH]);
    assert.equal(r.status, 0, r.stderr + r.stdout);
    assert.equal((r.stdout.match(/push attempt/g) ?? []).length, 2, 'one rejected push, one after regenerating');
    assert.match(r.stdout, /moved during the build — regenerating on its new head/);
    const head = f.head();
    assert.notEqual(head, moved);
    assert.match(f.git(f.origin, 'log', '-1', '--format=%s', head), /^regenerate: generated\/ for /);
    assert.equal(f.git(f.origin, 'rev-parse', `${head}^`), moved, 'the bot commit sits on the moved head');
    const model = `${f.show(moved, 'model/er/one.ttrm')}\n`;
    assert.equal(`${f.show(head, 'generated/lexicon.tar.zst')}\n`, built(model), 'built from the NEW head\'s model');
    assert.deepEqual(f.git(f.origin, 'diff', '--name-only', moved, head).split('\n').sort(),
      ['generated/lexicon.tar.zst', 'generated/model.tar.zst', 'generated/resolved-packages.json']);
  } finally {
    await f.done();
  }
});

test('P2 — the branch moved to a head whose generated/ is current: exit 0, origin unchanged', async () => {
  const f = await fixture();
  try {
    const ci = await builtCheckout(f);
    // Someone else regenerated the same head first.
    const other = f.clone('other');
    assert.equal(f.run(other, 'regenerate-local.sh').status, 10);
    // Regeneration also creates model.tar.zst when the save removed the old archive.
    // Stage the full generated/ bundle, as the real push script does; -am misses new files.
    f.git(other, 'add', 'generated');
    f.git(other, ...ID, 'commit', '-q', '-am', 'regenerated elsewhere');
    f.git(other, 'push', '-q', 'origin', `HEAD:refs/heads/${BRANCH}`);
    const current = f.head();
    const r = f.run(ci, 'regenerate-push.sh', [BRANCH]);
    assert.equal(r.status, 0, r.stderr + r.stdout);
    assert.match(r.stdout, /the new head is current — nothing to push/);
    assert.equal(f.head(), current);
  } finally {
    await f.done();
  }
});

test('P3 — a push refused for another reason (a declining hook) fails at once, no retry', async () => {
  const f = await fixture();
  try {
    const ci = await builtCheckout(f);
    const before = f.head();
    const hook = path.join(f.origin, 'hooks/pre-receive');
    await writeFile(hook, '#!/bin/sh\necho "declined by policy" >&2\nexit 1\n');
    await chmod(hook, 0o755);
    const r = f.run(ci, 'regenerate-push.sh', [BRANCH]);
    assert.equal(r.status, 1, r.stderr + r.stdout);
    assert.equal((r.stdout.match(/push attempt/g) ?? []).length, 1);
    assert.match(r.stderr, /not retried/);
    assert.equal(f.head(), before);
  } finally {
    await f.done();
  }
});

test('P4 — out of attempts while the branch keeps moving: exit 1, "the branch kept moving"', async () => {
  const f = await fixture();
  try {
    const ci = await builtCheckout(f);
    const moved = await f.save('a save during the build');
    const r = f.run(ci, 'regenerate-push.sh', [BRANCH], { REGENERATE_PUSH_ATTEMPTS: '1' });
    assert.equal(r.status, 1, r.stderr + r.stdout);
    assert.match(r.stderr, /the branch kept moving/);
    assert.equal(f.head(), moved);
  } finally {
    await f.done();
  }
});

test('P6 — with GH_TOKEN set the push still works, and the token is never written to .git/config (R11)', async () => {
  const f = await fixture();
  try {
    const ci = await builtCheckout(f);
    await f.save('a save during the build'); // the retry path fetches with the token too
    const token = 'ghs_regenerate_push_test_token';
    const r = f.run(ci, 'regenerate-push.sh', [BRANCH], { GH_TOKEN: token });
    assert.equal(r.status, 0, r.stderr + r.stdout);
    const config = await readFile(path.join(ci, '.git/config'), 'utf-8');
    const basic = Buffer.from(`x-access-token:${token}`).toString('base64');
    assert.ok(!config.includes(token) && !config.includes(basic), 'the token reached .git/config');
    assert.ok(!r.stdout.includes(token) && !r.stderr.includes(token), 'the token reached the log');
  } finally {
    await f.done();
  }
});

test('P5 — anything modified outside generated/ is refused before a commit, and nothing is reset', async () => {
  const f = await fixture();
  try {
    const ci = await builtCheckout(f);
    const headBefore = f.git(ci, 'rev-parse', 'HEAD');
    await appendFile(path.join(ci, 'model/er/one.ttrm'), '// someone\'s edit\n');
    const r = f.run(ci, 'regenerate-push.sh', [BRANCH]);
    assert.equal(r.status, 1, r.stderr + r.stdout);
    assert.match(r.stderr, /outside generated\//);
    assert.equal(f.git(ci, 'rev-parse', 'HEAD'), headBefore, 'nothing committed');
    assert.match(await readFile(path.join(ci, 'model/er/one.ttrm'), 'utf-8'), /someone's edit/, 'nothing reset');
    assert.match(f.git(ci, 'status', '--porcelain'), /generated\/lexicon\.tar\.zst/);
  } finally {
    await f.done();
  }
});

test('P7 — a rebuilt Golem layout (model/layouts/agent/) is committed beside generated/ (Bora\'s ruling 2026-10-28)', async () => {
  const f = await fixture();
  try {
    await f.save('a new entity in the agent\'s area');
    const ci = f.clone('ci');
    // The gen-layouts stub: the Golem's layout lists what the model holds, as agent-layout.mjs's area closure does.
    const stub = path.join(f.work, 'layouts-stub');
    await writeFile(stub, '#!/usr/bin/env bash\nset -euo pipefail\nmkdir -p model/layouts/agent\n'
      + 'find model/er -type f | sort | xargs cat | sha256sum | cut -c1-16 > model/layouts/agent/agent_x.ttrg\n');
    await chmod(stub, 0o755);
    const layouts = { LAYOUTS_CLI: stub };
    const regen = f.run(ci, 'regenerate-local.sh', [], layouts);
    assert.equal(regen.status, 10, regen.stderr + regen.stdout);
    const before = f.head();
    const r = f.run(ci, 'regenerate-push.sh', [BRANCH], layouts);
    assert.equal(r.status, 0, r.stderr + r.stdout);
    assert.deepEqual(f.git(f.origin, 'diff', '--name-only', before, f.head()).split('\n').sort(),
      ['generated/lexicon.tar.zst', 'generated/model.tar.zst', 'generated/resolved-packages.json', 'model/layouts/agent/agent_x.ttrg']);
  } finally {
    await f.done();
  }
});
