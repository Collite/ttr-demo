// toolchain.lock (SO-demo P0·S0.1 T1, ⚑SO-P-4; review-121 R4/R6) — the pins the gate and the regenerate workflow
// read, through the one reader scripts/toolchain-lock.py. Its values reach $GITHUB_ENV and shell `export`s, so the
// reader shape-checks every one. That the workflows take the ref from it (and from nowhere else) is
// model/tests/workflows.test.mjs. Run: node --test model/tests/toolchain-lock.test.mjs.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const reader = path.join(root, 'scripts/toolchain-lock.py');

// The lock is two tables of string (or boolean) keys — a full TOML parser is not needed (and hartland has no deps).
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
    const pair = line.match(/^([A-Za-z0-9_-]+)\s*=\s*(?:"([^"]*)"|(true|false))$/);
    assert.ok(pair && current, `toolchain.lock: not a key = "string" | bool line inside a table: ${raw}`);
    current[pair[1]] = pair[2] ?? pair[3] === 'true';
  }
  return tables;
}

const lockText = await readFile(path.join(root, 'toolchain.lock'), 'utf-8');
const lock = readLock(lockText);

// Runs the reader over `text` written to a temp lock.
async function readerOn(text) {
  const dir = await mkdtemp(path.join(tmpdir(), 'toolchain-lock-'));
  try {
    const file = path.join(dir, 'toolchain.lock');
    await writeFile(file, text);
    return spawnSync('python3', [reader, file], { encoding: 'utf-8' });
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

test('T1.1 — the lock: [ttr-core] ref; [veles] image, ttr-metadata and strict-load', () => {
  assert.deepEqual(Object.keys(lock).sort(), ['automation-preview', 'ttr-core', 'ttrp', 'veles']);
  assert.deepEqual(Object.keys(lock['ttr-core']), ['ref']);
  assert.deepEqual(Object.keys(lock.veles), ['image', 'ttr-metadata', 'strict-load']);
});

test('T1.2 — [ttr-core].ref is a grammar release tag, the [veles] pins plain versions, strict-load a boolean', () => {
  assert.match(lock['ttr-core'].ref, /^grammar\/v\d+\.\d+\.\d+$/);
  assert.match(lock.veles.image, /^\d+\.\d+\.\d+$/);
  assert.match(lock.veles['ttr-metadata'], /^\d+\.\d+\.\d+$/);
  assert.equal(typeof lock.veles['strict-load'], 'boolean');
});

test('T1.3 — scripts/toolchain-lock.py (the reader the workflows use) prints the same pins', () => {
  const out = execFileSync('python3', [reader], { encoding: 'utf-8' });
  assert.deepEqual(out.trim().split('\n'), [
    `TTR_CORE_REF=${lock['ttr-core'].ref}`,
    `VELES_IMAGE=${lock.veles.image}`,
    `VELES_TTR_METADATA=${lock.veles['ttr-metadata']}`,
    `TTRP_REF=${lock.ttrp.ref}`,
    `STRICT_LOAD=${lock.veles['strict-load']}`,
    `TTRP_VERSION=${lock.ttrp.version ?? lock.ttrp.ref.replace("grammar/v", "")}`,
    `AU_PREVIEW_SERVER_REF=${lock["automation-preview"]["server-ref"]}`,
  ]);
});

test('T1.4 — a pin missing or empty is refused, naming it (an empty ref = an unpinned checkout)', async () => {
  for (const [name, text, key] of [
    ['no-veles', '[ttr-core]\nref = "grammar/v0.16.1"\n', '[veles].image'],
    ['empty-ref', '[ttr-core]\nref = ""\n[veles]\nimage = "0.11.14"\nttr-metadata = "0.16.0"\nstrict-load = false\n', '[ttr-core].ref'],
    ['no-strict-load', '[ttr-core]\nref = "grammar/v0.16.1"\n[veles]\nimage = "0.11.14"\nttr-metadata = "0.16.0"\n', '[veles].strict-load'],
  ]) {
    const run = await readerOn(text + '[ttrp]\nref = "grammar/v9.9.9"\n');
    assert.notEqual(run.status, 0, `${name}: the reader accepted it`);
    assert.equal(run.stdout, '', `${name}: nothing may reach $GITHUB_ENV`);
    assert.ok(run.stderr.includes(key), `${name}: stderr must name ${key}: ${run.stderr}`);
  }
});

test('T1.5 — a value of the wrong shape is refused, naming the key (they reach $GITHUB_ENV and `export`)', async () => {
  // Each case rewrites the lock's line that STARTS WITH `from`. Every pin is matched by its key's prefix, not its
  // value, so a pin bump does not break this test (the [ttr-core] ref did at grammar/v0.18.1, CN-P4 S4.5, and the
  // [veles] pins at veles 0.11.15, md/hop HP-H); the [ttrp] ref is a commit sha and never starts with `grammar/v`.
  const cases = [
    ['ref = "grammar/v', 'ref = "grammar/v0.17.0$(true)"', '[ttr-core].ref'],
    ['ref = "grammar/v', 'ref = "main"', '[ttr-core].ref'],
    ['ref = "grammar/v', 'ref = "grammar/v0.17.0 x"', '[ttr-core].ref'],
    ['ttr-metadata = "', 'ttr-metadata = "0.16"', '[veles].ttr-metadata'],
    // A TOML escape: the decoded value carries a newline, i.e. a second env line.
    ['ttr-metadata = "', 'ttr-metadata = "0.16.0\\nX=1"', '[veles].ttr-metadata'],
    ['image = "', 'image = "v0.11.14"', '[veles].image'],
    ['strict-load = ', 'strict-load = "yes"', '[veles].strict-load'],
  ];
  for (const [from, to, key] of cases) {
    const at = lockText.split('\n').findIndex((l) => l.startsWith(from));
    assert.ok(at >= 0, `the lock has no line starting ${from}`);
    const lines = lockText.split('\n');
    lines[at] = to;
    const run = await readerOn(lines.join('\n'));
    assert.notEqual(run.status, 0, `${to}: the reader accepted it`);
    assert.equal(run.stdout, '', `${to}: nothing may reach $GITHUB_ENV`);
    assert.ok(run.stderr.includes(key), `${to}: stderr must name ${key}: ${run.stderr}`);
  }
});

for (const [ref, version, accepted] of [
  ['grammar/v9.9.9', '9.9.9', true], ['grammar/v9.9.9', null, true],
  ['grammar/v9.9.9', '9.9.8', false], ['a'.repeat(40), null, false],
  ['a'.repeat(40), '9.9.9', false], ['a'.repeat(40), '9.9.9-au.1', true],
  ['main', null, false], ['a'.repeat(40), '9.9.9-au.1\\nEVIL=1', false],
]) {
  test(`TTR-P pin ${ref} version ${version}: ${accepted ? 'accepted' : 'refused'}`, async () => {
    const text = lockText.replace(/\[ttrp\][\s\S]*?(?=\n\[|$)/,
      `[ttrp]\nref = "${ref}"\n${version == null ? '' : `version = "${version}"\n`}`);
    const run = await readerOn(text);
    if (accepted) {
      assert.equal(run.status, 0, run.stderr);
      assert.ok(run.stdout.includes(`TTRP_VERSION=${version ?? ref.replace('grammar/v', '')}`));
    } else {
      assert.notEqual(run.status, 0);
      assert.equal(run.stdout, '');
      assert.match(run.stderr, /\[ttrp\]\.(ref|version)/);
    }
  });
}

test('preview runtime pin refuses malformed or missing commits before exporting any environment', async () => {
  for (const ref of ['master', '', 'a'.repeat(39), '$(true)', 'a'.repeat(40) + '\\nEVIL=1']) {
    const run = await readerOn(lockText.replace(/^server-ref = .*$/m, `server-ref = "${ref}"`));
    assert.notEqual(run.status, 0);
    assert.equal(run.stdout, '');
    assert.match(run.stderr, /\[automation-preview\]\.server-ref/);
  }
  const run = await readerOn(lockText.replace(/^server-ref = .*$/m, ''));
  assert.notEqual(run.status, 0);
  assert.equal(run.stdout, '');
});
