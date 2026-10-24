// The layouts (SO-demo P1·S1.1, ttr-demo contracts §6, D-26 beat V; VL contracts §1–§4): the pictures Veles serves on
// /model/layouts — the *sales* layout and the Golem's own. Each is a `.ttrg` under model/layouts/, because Veles
// collects `**/*.ttrg` under model/ as layout files and nothing else (ttr-metadata Source.kt, V-37) — a `.yaml` here
// would never be served. Read and re-written with the toolchain's own reader and writer (`@tatrman/parser/layout`),
// and resolved as a VL writer writes (V-15): every ref the full qname of a card the model has.
// Run: node --test model/layouts/tests/layouts.test.mjs.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import { loadHartlandProject, hartlandRoot } from '../../tests/project-harness.mjs';
import {
  agentLayouts, cardIndex, committedAgentLayouts, readAgents, staleLayouts,
} from '../../../scripts/agent-layout.mjs';

const tatrmanPackages = process.env.TATRMAN_PACKAGES ?? path.resolve(hartlandRoot, '../tatrman/packages');
const { readTtrg, writeTtrg, IDENTIFIER } = await import(path.join(tatrmanPackages, 'parser/dist/layout/index.js'));
const { parseString } = await import(path.join(tatrmanPackages, 'parser/dist/index.js'));

const layoutsDir = path.join(hartlandRoot, 'model/layouts');

async function walkTtrg(dir) {
  const out = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...await walkTtrg(p));
    else if (entry.name.endsWith('.ttrg')) out.push(p);
  }
  return out.sort();
}

// A generated file opens with `//` lines (scripts/agent-layout.mjs); the layout itself is what follows them.
const withoutHeader = (text) => text.replace(/^(?:\/\/[^\n]*\n)+/, '');

const project = await loadHartlandProject();
const cards = cardIndex(project);
const layouts = await Promise.all((await walkTtrg(layoutsDir)).map(async (file) => {
  const text = await readFile(file, 'utf-8');
  return { rel: path.relative(hartlandRoot, file), text, read: readTtrg(text, { fileName: path.basename(file) }) };
}));
const byName = (name) => layouts.find((l) => l.read.ok && l.read.doc.name === name);

test('L0 — the layouts are there: sales and the Golem\'s two', () => {
  assert.deepEqual(layouts.map((l) => l.rel), [
    'model/layouts/agent/agent_hartland.ttrg',
    'model/layouts/agent/agent_hartland_db.ttrg',
    'model/layouts/sales.ttrg',
  ]);
});

test('L1 — every layout parses with the grammar and reads clean, in VL\'s canonical form, named after its file (V-4, V-5)', () => {
  for (const { rel, text, read } of layouts) {
    assert.deepEqual(parseString(text, `file://${rel}`).errors, [], `${rel}: the worker LSP's parser refuses it`);
    assert.ok(read.ok, `${rel}: ${JSON.stringify(read.errors)}`);
    assert.deepEqual(read.warnings, [], `${rel}: warnings`);
    assert.equal(writeTtrg(read.doc), withoutHeader(text), `${rel} is not what a VL writer writes`);
  }
});

test('L2 — names are unique (a name two files declare is served by neither, A-VL-7); the model is er or db', () => {
  const names = layouts.map((l) => l.read.doc.name);
  assert.deepEqual(names.filter((n, i) => names.indexOf(n) !== i), []);
  for (const { rel, read } of layouts) {
    assert.match(read.doc.name, IDENTIFIER, rel);
    assert.ok(['er', 'db'].includes(read.doc.model), `${rel}: model ${read.doc.model}`);
  }
});

test('L3 — every object is a card of the layout\'s model, written as its full qname (V-1, V-15)', () => {
  for (const { rel, read } of layouts) {
    const missing = read.doc.objects.filter((ref) => !cards[read.doc.model].has(ref));
    assert.deepEqual(missing, [], `${rel}: not a ${read.doc.model} card by its full qname`);
  }
});

// The viewer's er.crow card: 200 wide, a 30 px header, 20 px per attribute row (at least one), 6 px foot — ttr-core
// packages/designer/src/skins/card-rows.tsx `cardSize` at the pinned ref. An attribute added later can make two
// hand-placed cards overlap; this says which, before anyone opens the picture.
const ER_CARD_WIDTH = 200;
const erCardHeight = (ref) => {
  const rows = project.symbols.all().filter((s) => s.kind === 'attribute' && s.parent === cards.er.get(ref).qname).length;
  return 30 + Math.max(1, rows) * 20 + 6;
};

test('L4 — sales: the four sales facts and the calendar (contracts §6), every card placed, none overlapping', () => {
  const sales = byName('sales');
  assert.ok(sales, 'no layout named sales');
  const { model, objects, positions } = sales.read.doc;
  assert.equal(model, 'er');
  for (const name of ['store_sales', 'web_sales', 'catalog_sales', 'channel_sales', 'date_dim']) {
    assert.ok(objects.includes(`hartland.er.entity.${name}`), `sales lacks ${name}`);
  }
  assert.deepEqual(objects.filter((ref) => !positions[ref]), [], 'cards without a position');
  const boxes = objects.map((ref) => ({ ref, ...positions[ref], w: ER_CARD_WIDTH, h: erCardHeight(ref) }));
  const overlaps = [];
  for (const [i, a] of boxes.entries()) {
    for (const b of boxes.slice(i + 1)) {
      if (a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h) overlaps.push(`${a.ref} × ${b.ref}`);
    }
  }
  assert.deepEqual(overlaps, []);
});

test('L5 — the Golem\'s layouts are what `just gen-layouts` writes from agents/ and the model now', async () => {
  // Today the one agent def's area (`def area hartland`, `packages: [hartland]`) is the whole package, so both
  // layouts hold every card; a narrower area narrows them, and this comparison is what notices.
  const generated = agentLayouts(project, await readAgents());
  assert.deepEqual(staleLayouts(generated, await committedAgentLayouts()), [], 'run `just gen-layouts` and commit');
});
