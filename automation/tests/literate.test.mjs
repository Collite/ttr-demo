// AU-hartland P3: the business documents own canonical programs and provenance.
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

const returnsDocument = 'automation/handling-a-return-request.md';
const returnsNodes = {
  decide_return: ['received', 'bought_here', 'return_share', 'request_value', 'stock_at_center', 'way'],
  monitor_inbound: ['awaiting', 'receipts', 'age', 'reminded', 'inbound'],
  settle: ['settling', 'open_obligations', 'documents', 'overdue_days', 'settlement'],
};
for (const [name, nodes] of Object.entries(returnsNodes)) {
  test(`S3.2 — ${name} provenance belongs to its section of the shared H-2 document`, async () => {
    const source = await readFile(path.join(hartlandRoot, returnsDocument), 'utf8');
    const dir = path.join(hartlandRoot, 'automation', name);
    const sidecar = JSON.parse(await readFile(path.join(dir, `${name}.ttrd`), 'utf8'));
    const canonical = await readFile(path.join(dir, `${name}.ttrp`), 'utf8');
    assert.equal(sidecar.document, 'handling-a-return-request.md');
    assert.equal(sidecar.documentSha, createHash('sha256').update(source).digest('hex'));
    assert.deepEqual(Object.keys(sidecar.nodes).sort(), [...nodes].sort());
    const skeleton = source.indexOf(`recipe: ${name}\n`);
    const next = source.indexOf('\nrecipe: ', skeleton + 1);
    for (const [id, node] of Object.entries(sidecar.nodes)) {
      for (const span of [node.span, node.paragraph]) {
        assert.ok(span[0] >= skeleton && span[0] < span[1] && span[1] <= (next < 0 ? source.length : next), `${id}: source span`);
      }
      assert.ok(node.generatedSpan[0] >= 0 && node.generatedSpan[0] < node.generatedSpan[1] && node.generatedSpan[1] <= canonical.length);
      assert.ok(source.slice(...node.span).includes(id), `${id}: owning fence`);
      assert.ok(canonical.slice(...node.generatedSpan).includes(id), `${id}: generated container`);
      assert.ok(sidecar.sentences.some((s) => s.nodes.includes(id)), `${id}: linked business prose`);
    }
    const readme = await readFile(path.join(dir, 'README.md'), 'utf8');
    const manifest = JSON.parse(await readFile(path.join(dir, `${name}.bundle/manifest.json`), 'utf8'));
    for (const route of manifest.recipe.roles.routes) if (route.because) assert.ok(readme.includes(route.because), route.name);
  });
}

test('S3.2 — one H-2 build reproduces all three programs, sidecars and explanations', async () => {
  const tmp = await mkdtemp(path.join(os.tmpdir(), 'h2-literate-'));
  try {
    await run('python3', [script, '--cli', cli, '--recipe', path.join(hartlandRoot, returnsDocument), '--out', tmp], { maxBuffer: 4 << 20 });
    for (const name of Object.keys(returnsNodes)) {
      for (const file of [`${name}.ttrp`, `${name}.ttrd`, 'README.md']) {
        assert.equal(await readFile(path.join(tmp, name, file), 'utf8'), await readFile(path.join(hartlandRoot, 'automation', name, file), 'utf8'), `${name}/${file}`);
      }
    }
  } finally { await rm(tmp, { recursive: true, force: true }); }
});

test('S3.2 — H-2 prose and hand edits in each of its programs fail the read-only check', async () => {
  const tmp = await mkdtemp(path.join(os.tmpdir(), 'h2-drift-'));
  const root = path.join(tmp, 'hartland');
  try {
    for (const entry of ['modeler.toml', 'model', 'automation', 'authoring-stubs', 'scripts']) {
      await cp(path.join(hartlandRoot, entry), path.join(root, entry), { recursive: true });
    }
    const args = [path.join(root, 'scripts/build-recipes.py'), '--cli', cli, '--literate-check'];
    await run('python3', args, { maxBuffer: 4 << 20 });
    const doc = path.join(root, returnsDocument);
    const original = await readFile(doc, 'utf8');
    const edited = original.replace('A customer may request', 'A Customer may request');
    assert.notEqual(edited, original);
    await writeFile(doc, edited);
    await assert.rejects(run('python3', args), (e) => e.code === 3 && /TTRP-DOC-003/.test(e.stderr));
    assert.equal(await readFile(doc, 'utf8'), edited);
    await writeFile(doc, original);
    for (const [name, from, to] of [
      ['decide_return', 'share > :abuse_share', 'share >= :abuse_share'],
      ['monitor_inbound', 'days_open > :inbound_close', 'days_open >= :inbound_close'],
      ['settle', 'max_late > 0', 'max_late > 1'],
    ]) {
      const canonical = path.join(root, 'automation', name, `${name}.ttrp`);
      const old = await readFile(canonical, 'utf8');
      const change = old.replace(from, to);
      assert.notEqual(change, old);
      await writeFile(canonical, change);
      await assert.rejects(run('python3', args), (e) => e.code === 3 && /TTRP-DOC-003/.test(e.stderr), name);
      assert.equal(await readFile(canonical, 'utf8'), change, 'check must not repair the hand edit');
      await writeFile(canonical, old);
    }
  } finally { await rm(tmp, { recursive: true, force: true }); }
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

for (const [name, nodes] of Object.entries({
  reorder_proposals: ['selling', 'on_hand', 'weekly_demand', 'cover'],
  winback: ['lapsed', 'band', 'mailed', 'offer'],
  'ops/no_run_since': ['scheduled', 'last_run', 'silence'],
  'ops/obligation_due_passed': ['past_due', 'lateness', 'overdue'],
})) {
  test(`S3.3 — ${name}: English provenance covers its business containers`, async () => {
    const stem = path.basename(name);
    const dir = path.join(hartlandRoot, 'automation', name);
    const source = await readFile(path.join(dir, stem + '.md'), 'utf8');
    const canonical = await readFile(path.join(dir, stem + '.ttrp'), 'utf8');
    const sidecar = JSON.parse(await readFile(path.join(dir, stem + '.ttrd'), 'utf8'));
    assert.equal(sidecar.documentSha, createHash('sha256').update(source).digest('hex'));
    assert.deepEqual(Object.keys(sidecar.nodes).sort(), nodes.sort());
    for (const [id, node] of Object.entries(sidecar.nodes)) {
      assert.ok(source.slice(...node.span).includes(id));
      assert.ok(canonical.slice(...node.generatedSpan).includes(id));
      assert.ok(sidecar.sentences.some(s => s.nodes.includes(id)));
    }
  });
}
