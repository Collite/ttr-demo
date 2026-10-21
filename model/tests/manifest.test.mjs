// modeler.toml `[bindings] required` (SO-demo P0·S0.2 T5, C-6, D-22/D-25): a Studio-authored entity or attribute
// must be bound at creation — the synthesizer refuses an unbound one (ttr-core contracts §1.2), and er.test.mjs
// T6.5 is the second check. Read through the toolchain's own manifest reader, so the test also says the pinned
// reader accepts the table (it keeps unknown tables until ttr-core SO-core P0 reads this one).
// Run: node --test model/tests/manifest.test.mjs.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const tatrmanPackages = process.env.TATRMAN_PACKAGES ?? path.resolve(root, '../tatrman/packages');
const { parseManifest, resolveManifest, validateManifest } = await import(path.join(tatrmanPackages, 'semantics/dist/index.js'));

const manifest = parseManifest(await readFile(path.join(root, 'modeler.toml'), 'utf-8'));

test('M1 — [bindings] required = true, the only key of the table', () => {
  assert.deepEqual(manifest.bindings, { required: true });
});

test('M2 — the pinned manifest reader resolves and validates the manifest clean', () => {
  assert.deepEqual(validateManifest(resolveManifest(manifest, root)), []);
});
