// S3.3: one executable per recipe, two documents, and locale-specific native provenance/explanations.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir, mkdtemp, cp, writeFile, rm } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import path from 'node:path';
import os from 'node:os';
import { hartlandRoot } from '../../model/tests/project-harness.mjs';
const run = promisify(execFile);
const sources = {
  'release_order/release_order': ['release_order/release_order'],
  'handling-a-return-request': ['decide_return/decide_return', 'monitor_inbound/monitor_inbound', 'settle/settle'],
  'reorder_proposals/reorder_proposals': ['reorder_proposals/reorder_proposals'],
  'winback/winback': ['winback/winback'],
  'ops/no_run_since/no_run_since': ['ops/no_run_since/no_run_since'],
  'ops/obligation_due_passed/obligation_due_passed': ['ops/obligation_due_passed/obligation_due_passed'],
};
const automation = path.join(hartlandRoot, 'automation');
const fences = s => s.match(/^```[^\n]*\n[\s\S]*?^```[ \t]*$/gm);
test('S3.3 — the twin inventory covers every literate source and all eight recipes', async () => {
  const actual = [];
  async function visit(dir) {
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      const file = path.join(dir, entry.name);
      if (entry.isDirectory() && !entry.name.endsWith('.bundle')) await visit(file);
      if (entry.isFile() && entry.name.endsWith('.md') && !entry.name.endsWith('.cs.md')
          && /^```ttrp(?:\s|$)/m.test(await readFile(file, 'utf8'))) {
        actual.push(path.relative(automation, file).slice(0, -3));
      }
    }
  }
  await visit(automation);
  assert.deepEqual(actual.sort(), Object.keys(sources).sort());
  assert.equal(Object.values(sources).flat().length, 8);
});

for (const [document, recipes] of Object.entries(sources)) {
  test(`S3.3 — ${document}: Czech twin copies every executable block and owns native provenance`, async () => {
    const en = await readFile(path.join(automation, document + '.md'), 'utf8');
    const cs = await readFile(path.join(automation, document + '.cs.md'), 'utf8');
    assert.deepEqual(fences(cs), fences(en), 'TTR-P and SQL blocks copied verbatim');
    assert.doesNotMatch(cs, /značk/iu, 'tag stays tag in Czech');
    assert.notEqual(cs, en, 'prose is translated');
    const parameters = [...en.matchAll(/parameters:\s*\[([^\]]+)\]/g)].flatMap(m => m[1].split(',').map(s => s.trim()));
    const pkg = await readFile(path.join(automation, 'automation.ttrm'), 'utf8');
    for (const param of parameters) {
      const label = new RegExp(`def parameter ${param}\\s*\\{[^\\n]*cs: "([^"]+)"`).exec(pkg)?.[1];
      assert.ok(label, param);
      assert.ok(cs.includes(label), `${param}: Czech lexicon label in business prose`);
    }
    for (const recipe of recipes) {
      const side = JSON.parse(await readFile(path.join(automation, recipe + '.cs.ttrd'), 'utf8'));
      const canonical = await readFile(path.join(automation, recipe + '.ttrp'), 'utf8');
      assert.equal(side.document, path.basename(document) + '.cs.md');
      assert.equal(side.documentSha, createHash('sha256').update(cs).digest('hex'));
      assert.ok(Object.keys(side.nodes).length >= 3);
      for (const [name, node] of Object.entries(side.nodes)) {
        assert.ok(cs.slice(...node.span).includes(name), `${name}: source fence`);
        assert.ok(canonical.slice(...node.generatedSpan).includes(name), `${name}: canonical container`);
        assert.ok(node.paragraph[0] < node.paragraph[1], `${name}: linked Czech prose`);
      }
      if (!document.startsWith('ops/')) {
        const dir = recipes.length > 1 ? path.dirname(recipe) : document;
        const readme = await readFile(path.join(automation, dir, 'README.cs.md'), 'utf8');
        assert.match(readme, /## O čem recept rozhoduje/);
        assert.match(readme, /## Parametry/);
      }
    }
  });
}

test('S3.3 — Czech prose and explanation drift fail without repairing committed artifacts', async () => {
  const tmp = await mkdtemp(path.join(os.tmpdir(), 'cz-drift-'));
  const root = path.join(tmp, 'hartland');
  const cli = process.env.TTRP_CLI ?? path.join(process.env.TTRP_SRC ?? path.join(hartlandRoot, '.modeler/toolchains/ttrp'), 'packages/kotlin/ttrp-cli/build/install/ttrp-cli/bin/ttrp-cli');
  try {
    for (const entry of ['modeler.toml', 'model', 'automation', 'authoring-stubs', 'scripts']) {
      await cp(path.join(hartlandRoot, entry), path.join(root, entry), { recursive: true });
    }
    const args = [path.join(root, 'scripts/build-recipes.py'), '--cli', cli, '--recipe', path.join(root, 'automation/winback/winback.md'), '--literate-check'];
    await run('python3', args, { maxBuffer: 4 << 20 });
    const doc = path.join(root, 'automation/winback/winback.cs.md');
    const original = await readFile(doc, 'utf8');
    const proseEdit = original.replace('Zákazníci, kteří', 'Zákazníci, již');
    assert.notEqual(proseEdit, original);
    await writeFile(doc, proseEdit);
    await assert.rejects(run('python3', args), e => e.code === 3 && /TTRP-DOC-003/.test(e.stderr));
    assert.equal(await readFile(doc, 'utf8'), proseEdit);
    const codeEdit = original.replace('top_band = 1', 'top_band = 0');
    await writeFile(doc, codeEdit);
    await assert.rejects(run('python3', args), e => e.code === 3 && /canonical differs from English/.test(e.stderr));
    assert.equal(await readFile(doc, 'utf8'), codeEdit);
    await writeFile(doc, original);
    const readme = path.join(root, 'automation/winback/winback/README.cs.md');
    await writeFile(readme, 'hand edit');
    await assert.rejects(run('python3', args), e => e.code === 3 && /TTRP-DOC-003/.test(e.stderr));
    assert.equal(await readFile(readme, 'utf8'), 'hand edit');
  } finally { await rm(tmp, { recursive: true, force: true }); }
});
