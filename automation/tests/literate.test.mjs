// AU-hartland P3 S3.1: the H-1 document owns its canonical program and provenance.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFile } from 'node:child_process';
import { mkdtemp, readFile, rm, cp, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { promisify } from 'node:util';
import { hartlandRoot } from '../../model/tests/project-harness.mjs';

const run = promisify(execFile);
const relative = 'automation/release_order/release_order.md';
const recipeDir = path.join(hartlandRoot, path.dirname(relative));
const script = path.join(hartlandRoot, 'scripts/build-recipes.py');
const cli = process.env.TTRP_CLI ?? path.join(process.env.TTRP_SRC ?? path.join(hartlandRoot, '.modeler/toolchains/ttrp'), 'packages/kotlin/ttrp-cli/build/install/ttrp-cli/bin/ttrp-cli');

test('S3.1 — H-1 provenance covers its five containers and points inside the source document', async () => {
  const source = await readFile(path.join(hartlandRoot, relative), 'utf8');
  const sidecar = JSON.parse(await readFile(path.join(recipeDir, 'release_order.ttrd'), 'utf8'));
  const canonical = await readFile(path.join(recipeDir, 'release_order.ttrp'), 'utf8');
  assert.equal(sidecar.document, 'release_order.md');
  assert.equal(sidecar.documentSha, createHash('sha256').update(source).digest('hex'));
  assert.deepEqual(Object.keys(sidecar.nodes).sort(), ['overdue', 'placed_orders', 'price_differences', 'shortfall', 'verdict']);
  for (const [name, node] of Object.entries(sidecar.nodes)) {
    for (const span of [node.span, node.paragraph]) {
      assert.ok(span[0] >= 0 && span[0] < span[1] && span[1] <= source.length, `${name}: Markdown span`);
    }
    assert.ok(node.generatedSpan[0] >= 0 && node.generatedSpan[1] <= canonical.length, `${name}: canonical span`);
    assert.ok(source.slice(...node.span).includes(name), `${name}: owning fence`);
    assert.ok(canonical.slice(...node.generatedSpan).includes(name), `${name}: generated container`);
  }
  const readme = await readFile(path.join(recipeDir, 'release_order/README.md'), 'utf8');
  const manifest = JSON.parse(await readFile(path.join(recipeDir, 'release_order.bundle/manifest.json'), 'utf8'));
  for (const route of manifest.recipe.roles.routes) assert.ok(readme.includes(route.because), route.name);
});

test('S3.1 — building H-1 reproduces canonical program, provenance and explanation', async () => {
  const tmp = await mkdtemp(path.join(os.tmpdir(), 'h1-literate-'));
  try {
    await run('python3', [script, '--cli', cli, '--recipe', path.join(hartlandRoot, relative), '--out', tmp], { maxBuffer: 4 << 20 });
    for (const file of ['release_order.ttrp', 'release_order.ttrd', 'release_order/README.md']) {
      assert.equal(await readFile(path.join(tmp, 'release_order', file), 'utf8'), await readFile(path.join(recipeDir, file), 'utf8'), file);
    }
  } finally { await rm(tmp, { recursive: true, force: true }); }
});

test('S3.1 — document and canonical edits fail the read-only drift check', async () => {
  const tmp = await mkdtemp(path.join(os.tmpdir(), 'h1-drift-'));
  const root = path.join(tmp, 'hartland');
  try {
    for (const entry of ['modeler.toml', 'model', 'automation', 'authoring-stubs', 'scripts']) {
      await cp(path.join(hartlandRoot, entry), path.join(root, entry), { recursive: true });
    }
    const args = [path.join(root, 'scripts/build-recipes.py'), '--cli', cli, '--literate-check'];
    await run('python3', args, { maxBuffer: 4 << 20 });
    const doc = path.join(root, relative);
    const original = await readFile(doc, 'utf8');
    await writeFile(doc, original.replace('Every placed order', 'Every placed Order'));
    await assert.rejects(run('python3', args), (e) => e.code === 3 && /TTRP-DOC-003/.test(e.stderr));
    assert.equal(await readFile(doc, 'utf8'), original.replace('Every placed order', 'Every placed Order'));
    await writeFile(doc, original);
    const canonical = path.join(root, 'automation/release_order/release_order.ttrp');
    const old = await readFile(canonical, 'utf8');
    const edited = old.replace('n_short > 0', 'n_short > 1');
    assert.notEqual(edited, old);
    await writeFile(canonical, edited);
    await assert.rejects(run('python3', args), (e) => e.code === 3 && /TTRP-DOC-003/.test(e.stderr));
    assert.equal(await readFile(canonical, 'utf8'), edited, 'check must not repair the hand edit');
  } finally { await rm(tmp, { recursive: true, force: true }); }
});
