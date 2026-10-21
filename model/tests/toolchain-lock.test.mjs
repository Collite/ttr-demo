// toolchain.lock (SO-demo P0·S0.1 T1, ⚑SO-P-4) — the two pins the gate and the regenerate workflow read,
// through the one reader scripts/toolchain-lock.py. That the workflows take the ref from it (and from nowhere
// else) is model/tests/workflows.test.mjs. Run: node --test model/tests/toolchain-lock.test.mjs.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

// The lock is two tables of string keys — a full TOML parser is not needed (and hartland has no deps).
function readLock(text) {
  const tables = {};
  let current = null;
  for (const raw of text.split('\n')) {
    const line = raw.replace(/\s+#.*$/, '').replace(/^#.*$/, '').trim();
    if (!line) continue;
    const header = line.match(/^\[([A-Za-z0-9_-]+)\]$/);
    if (header) {
      current = tables[header[1]] = {};
      continue;
    }
    const pair = line.match(/^([A-Za-z0-9_-]+)\s*=\s*"([^"]*)"$/);
    assert.ok(pair && current, `toolchain.lock: not a key = "string" line inside a table: ${raw}`);
    current[pair[1]] = pair[2];
  }
  return tables;
}

const lock = readLock(await readFile(path.join(root, 'toolchain.lock'), 'utf-8'));

test('T1.1 — the lock has exactly the two tables, each with its one key', () => {
  assert.deepEqual(Object.keys(lock).sort(), ['ttr-core', 'veles']);
  assert.deepEqual(Object.keys(lock['ttr-core']), ['ref']);
  assert.deepEqual(Object.keys(lock.veles), ['ttr-metadata']);
});

test('T1.2 — [ttr-core].ref is a grammar release tag, [veles].ttr-metadata a plain version', () => {
  assert.match(lock['ttr-core'].ref, /^grammar\/v\d+\.\d+\.\d+$/);
  assert.match(lock.veles['ttr-metadata'], /^\d+\.\d+\.\d+$/);
});

test('T1.3 — scripts/toolchain-lock.py (the reader the workflows use) prints the same pins', () => {
  const out = execFileSync('python3', [path.join(root, 'scripts/toolchain-lock.py')], { encoding: 'utf-8' });
  assert.deepEqual(out.trim().split('\n'), [
    `TTR_CORE_REF=${lock['ttr-core'].ref}`,
    `VELES_TTR_METADATA=${lock.veles['ttr-metadata']}`,
  ]);
});

test('T1.4 — the reader refuses a lock with a pin missing or empty (an empty ref = an unpinned checkout)', async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'toolchain-lock-'));
  try {
    for (const [name, text] of [
      ['no-veles', '[ttr-core]\nref = "grammar/v0.16.1"\n'],
      ['empty-ref', '[ttr-core]\nref = ""\n[veles]\nttr-metadata = "0.16.0"\n'],
    ]) {
      const file = path.join(dir, `${name}.lock`);
      await writeFile(file, text);
      const run = spawnSync('python3', [path.join(root, 'scripts/toolchain-lock.py'), file], { encoding: 'utf-8' });
      assert.notEqual(run.status, 0, `${name}: the reader accepted it`);
      assert.equal(run.stdout, '', `${name}: nothing may reach $GITHUB_ENV`);
    }
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
