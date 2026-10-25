// CN-P6 S6.1 (= AU-hartland P5 S5.1) — the Hartland conceptual package: model/cn/*.ttrm, its bindings
// (model/binding/cn.ttrm), the `channel_returns` ground of `Return`, `PlacedOrder` materialized, the words
// (model/lexicon/{cs,en}/cn.ttrm).
//
// Two reports, one golden. `ttr cn hygiene` (Kotlin, `just cn-hygiene`) writes model/cn/tests/hygiene.md —
// `just check-cn-hygiene` keeps it fresh — and the editor's report (@tatrman/semantics) must print the same up to
// `## Definitions`, which only the Kotlin tool checks (CN-D29). A-H-5 (design `11` §8) is read off the golden:
// no md-grounded concept without its hop, and no md2er authored.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { loadHartlandProject, hartlandRoot, tatrmanPackages } from '../../tests/project-harness.mjs';
import { lexicon } from '../../../lexicon/tests/archive.mjs';

const semantics = await import(path.join(tatrmanPackages, 'semantics/dist/index.js'));
const project = await loadHartlandProject();
const golden = await readFile(path.join(hartlandRoot, 'model/cn/tests/hygiene.md'), 'utf-8');

const root = hartlandRoot.endsWith('/') ? hartlandRoot : hartlandRoot + '/';
const docs = [...project.asts]
  .filter(([uri]) => uri.startsWith('file://'))
  .map(([uri, ast]) => ({
    uri,
    ast,
    packageName: semantics.effectivePackage(ast, uri.slice('file://'.length), root, project.manifest.packages),
    schemaCode: ast.modelDirective?.modelCode ?? 'db',
    namespace: ast.modelDirective?.schema ?? '',
  }));
const report = semantics.cnHygieneReport(docs, project.resolver);

const defs = (pred) => [...project.asts]
  .filter(([uri]) => uri.startsWith('file://'))
  .flatMap(([uri, ast]) => (ast.definitions ?? []).filter((d) => pred(d, ast)).map((def) => ({ def, uri, ast })));
const cnDefs = defs((_, ast) => ast.modelDirective?.modelCode === 'cn');
const named = (stereotype) => cnDefs.filter(({ def }) => def.stereotype === stereotype || def.kind === stereotype).map(({ def }) => def.name).sort();

// The S6.1 list (T2, T4) on the estate's names. `Inventory`, `WarehouseOutage`, `PriceList` and `CustomerPrice` are the
// events the definitions read (DC-9, DC-2); `Party` was dropped (Q16-5).
const KINDS = ['Channel', 'Invoice', 'Item', 'ReturnReason', 'Store', 'Warehouse'];
const ROLES = ['Customer'];
const EVENTS = ['CustomerPrice', 'Inventory', 'Invoicing', 'Order', 'OrderLine', 'PriceList', 'Return', 'ReturnLine', 'ReturnRequest', 'Sale', 'WarehouseOutage'];
const PHASES = [
  'AbusiveReturner', 'BoughtHereLine', 'DebtorCustomer', 'HeldOrder', 'InStockAtCenter', 'LateReturnLine', 'MarketplaceSale',
  'MispricedLine', 'OverdueInvoice', 'PendingOrder', 'PlacedOrder', 'ReceivedReturnLine', 'ShortLine', 'SmallValueLine',
  'StoreSale', 'WebSale',
];

test('C1 — the package parses clean: model/cn, its binding file and the two new er files', () => {
  const files = ['model/cn/concepts.ttrm', 'model/cn/qualities.ttrm', 'model/cn/phases.ttrm', 'model/binding/cn.ttrm',
    'model/er/channel_returns.ttrm', 'model/er/placed_order.ttrm', 'model/lexicon/cs/cn.ttrm', 'model/lexicon/en/cn.ttrm'];
  for (const f of files) assert.deepEqual(project.parseErrorsByFile.get(f), [], `${f} parses with no error`);
});

test('C2 — the concepts are the S6.1 list, every one of them defined once', () => {
  assert.deepEqual(named('kind'), KINDS);
  assert.deepEqual(named('role'), ROLES);
  assert.deepEqual(named('event'), EVENTS);
  assert.deepEqual(named('phase'), PHASES);
  const all = cnDefs.map(({ def }) => def.name);
  assert.deepEqual(all.filter((n, i) => all.indexOf(n) !== i), [], 'one cn name space');
});

test('C3 — A-H-5: every md-grounded concept reaches er through the derived hop; no md2er is authored', () => {
  const grades = {};
  for (const c of report.concepts) grades[c.grade] = (grades[c.grade] ?? 0) + 1;
  assert.equal(grades['md-grounded-hop-missing'] ?? 0, 0, 'md-grounded-hop-missing = 0');
  assert.match(golden, /^\d+ concepts — \d+ er-grounded · \d+ md-grounded · \d+ ungrounded$/m, 'the golden: no hop-missing grade either');
  const md2er = defs((d) => /^md2er/i.test(d.kind));
  assert.deepEqual(md2er.map(({ def }) => def.name), [], 'no md2er anywhere under model/');
});

test('C4 — the landings the acceptance reads: Sale on `sales` (A-CN-100), revenue on its column through its bearer (L16-6)', () => {
  const expected = {
    'cn.Sale': 'er.entity.sales',
    'cn.Channel': 'er.entity.sales.channel',
    'cn.revenue': 'er.entity.sales.ext_sales_price',
    'cn.quantity': 'er.entity.sales.quantity',
    'cn.Return': 'er.entity.channel_returns',
    'cn.return_amount': 'er.entity.channel_returns.return_amt',
    'cn.returned_quantity': 'er.entity.channel_returns.return_quantity',
    'cn.Customer': 'er.entity.customer',
    'cn.Item': 'er.entity.item',
    'cn.Warehouse': 'er.entity.warehouse',
    'cn.PlacedOrder': 'er.entity.placed_order',
  };
  for (const [ref, er] of Object.entries(expected)) {
    assert.ok(golden.includes(`| ${ref} |`), `${ref} is in the golden`);
    const line = golden.split('\n').find((l) => l.startsWith(`| ${ref} |`));
    assert.ok(line.split('|').some((cell) => cell.trim().split(' ')[0] === er), `${ref} lands on ${er}: ${line}`);
  }
});

test('C5 — the editor\'s report is the golden up to `## Definitions` (the parity CnHygieneSpec holds in ttr-core)', () => {
  const editor = semantics.renderCnHygieneMarkdown(report);
  const cut = (s) => s.slice(0, s.indexOf('## Definitions'));
  assert.equal(cut(editor), cut(golden));
});

test('C6 — the golden has no error: no dangling grounding, no phase as default, no error-grade definition', () => {
  const section = (title) => golden.split(`## ${title}`)[1].split('\n## ')[0].trim();
  assert.equal(section('Dangling groundings'), 'None.');
  assert.equal(section('Phase as default sense'), 'None.');
  const definitions = section('Definitions').split('\n').filter((l) => l.startsWith('- '));
  assert.deepEqual(definitions.filter((l) => / \((error|warning)\) /.test(l)), [], 'no error- or warning-grade definition finding');
  // The only kind left is `cn/definition-unreachable(md)`: the recipe world has no md face, by design (S0.3).
  assert.deepEqual(definitions.filter((l) => !l.includes('cn/definition-unreachable(md) (hygiene)')), []);
});

test('C7 — every parameter a definition reads is a `def parameter` of the automation package', async () => {
  const automation = await readFile(path.join(hartlandRoot, 'automation/automation.ttrm'), 'utf-8');
  const declared = new Set([...automation.matchAll(/^def parameter (\w+)/gm)].map((m) => m[1]));
  const read = new Set();
  for (const f of ['model/cn/qualities.ttrm', 'model/cn/phases.ttrm']) {
    const text = await readFile(path.join(hartlandRoot, f), 'utf-8');
    for (const m of text.matchAll(/:([a-z_]+)/g)) if (m[1] !== 'as_of') read.add(m[1]);
  }
  assert.deepEqual([...read].sort(), ['abuse_share', 'return_window', 'small_value', 'tolerance']);
  for (const p of read) assert.ok(declared.has(p), `:${p} is declared in automation/automation.ttrm`);
});

test('C8 — PlacedOrder grounds to the entity `ttr cn materialize` wrote: the query of its definition, no label', () => {
  const entity = defs((d) => d.kind === 'entity' && d.name === 'placed_order')[0]?.def;
  const query = defs((d) => d.kind === 'query' && d.name === 'placed_order_q')[0]?.def;
  assert.ok(entity && query, 'placed_order and placed_order_q exist');
  assert.equal(query.sourceText.value.trim(), 'SELECT "order".order_number\nFROM "order"\nWHERE "order".state = \'placed\'');
  assert.equal(entity.displayLabel, undefined, 'no label: a label is a lexicon term');
  assert.deepEqual((entity.attributes ?? []).map((a) => a.name), ['order_number']);
});

test('C9 — channel_returns is the cousin of sales: three branches over the returns facts, CAST channel, not conversational', () => {
  const query = defs((d) => d.kind === 'query' && d.name === 'returns_union')[0].def;
  const sql = query.sourceText.value;
  const branches = sql.split(/\bUNION ALL\b/);
  assert.equal(branches.length, 3);
  for (const [i, [channel, fact]] of [['store', 'store_returns'], ['web', 'web_returns'], ['marketplace', 'catalog_returns']].entries()) {
    assert.match(branches[i], new RegExp(`CAST\\('${channel}' AS VARCHAR\\(16\\)\\) AS channel`));
    assert.match(branches[i], new RegExp(`FROM ${fact}\\s*$`));
  }
  const entity = defs((d) => d.kind === 'entity' && d.name === 'channel_returns')[0].def;
  for (const [i, attr] of (entity.attributes ?? []).entries()) {
    for (const b of branches) assert.equal(b.split('FROM')[0].replace(/^\s*sql\s*/, '').replace(/^SELECT /, '').split(/,(?![^(]*\))/)[i].trim().split(/\s+AS\s+/).at(-1), attr.name, `column ${i} is ${attr.name}`);
  }
  assert.equal(entity.displayLabel, undefined, 'no displayLabel');
  assert.equal(entity.labelPlural, undefined, 'no labelPlural');
  assert.equal(entity.semantics, undefined, 'no semantics { measures }');
  assert.deepEqual(lexicon.entries.filter((e) => e.targetRef?.startsWith('er.entity.channel_returns')).map((e) => e.termNormalized), [], 'no word names it');
});

// S6.2 T2: the cn er renderer correlates an event's participant through its relation's `join:` pairs, and an fk-only
// relation has none — `on_hand` (ranging over Inventory) was refused on the live door until the inventory pair stated it.
test('C10 — every relation a cn participant path names states its join pairs beside the fk', async () => {
  const binding = await readFile(path.join(hartlandRoot, 'model/binding/cn.ttrm'), 'utf-8');
  const relations = await readFile(path.join(hartlandRoot, 'model/er/relations.ttrm'), 'utf-8');
  const used = [...new Set([...binding.matchAll(/er\.relation\.(\w+)/g)].map((m) => m[1]))];
  assert.ok(used.length > 20, `${used.length} participant relations`);
  const fkOnly = used.filter((r) => {
    const def = relations.match(new RegExp(`^def relation ${r}\\s*\\{.*\\}\\s*$`, 'm'))?.[0];
    return !def || !/\bjoin:\s*\[/.test(def);
  });
  assert.deepEqual(fkOnly, [], 'participant relations with no join pairs (or not one-line defs in relations.ttrm)');
});

// ---- T6 · the words ----

const terms = (lang) => defs((d, ast) => d.kind === 'term' && ast.modelDirective?.modelCode === 'lexicon' && ast.modelDirective?.locale === lang && String(d.target?.path ?? '').startsWith('cn.'));
const forOf = ({ def }) => def.target.path;

// The phases whose words the Golem would lose a filter to are held back (model/lexicon/cs/cn.ttrm says why): the three
// channel phases (their words are `sales.channel`'s value labels, which the Golem honours), and `Return` — the bare
// «vratka» is no term (lexicon/tests/store-family.test.mjs) and its landing is no conversational object.
const WORDLESS = new Set(['cn.StoreSale', 'cn.WebSale', 'cn.MarketplaceSale']);
const WITH_WORDS = [...PHASES.map((p) => `cn.${p}`).filter((p) => !WORDLESS.has(p)), 'cn.Customer', 'cn.revenue'];

test('T6.1 — every phase but the held-back ones, Customer and revenue have a cs and an en term', () => {
  for (const lang of ['cs', 'en']) {
    const targets = new Set(terms(lang).map(forOf));
    for (const ref of WITH_WORDS) assert.ok(targets.has(ref), `${ref} has a ${lang} term`);
    for (const ref of WORDLESS) assert.ok(!targets.has(ref), `${ref} has no ${lang} term (held back)`);
    assert.ok(!targets.has('cn.Return'), `cn.Return has no ${lang} term (the bare «vratka» stays unclaimed)`);
  }
});

test('T6.2 — `default: true` is on Customer\'s «zákazník» / "customer" and on nothing else; never on a phase', () => {
  const defaults = [...terms('cs'), ...terms('en')].filter(({ def }) => def.default === true);
  assert.deepEqual(defaults.map(forOf).sort(), ['cn.Customer', 'cn.Customer']);
  const archived = lexicon.entries.filter((e) => e.defaultSense);
  assert.deepEqual([...new Set(archived.map((e) => `${e.termNormalized}→${e.targetRef}`))].sort(), ['customer→cn.Customer', 'zákazník→cn.Customer']);
});

test('T6.3 — the archive (v6) carries a concept entry for every concept and the lifts of their landings', () => {
  assert.equal(lexicon.header.schemaVersion, 'ttr-lexicon-compiled/v6');
  const targets = Object.entries(lexicon.targets);
  const concepts = new Set(targets.filter(([, t]) => t.objectKind === 'concept').map(([ref]) => ref));
  for (const name of [...KINDS, ...ROLES, ...EVENTS, ...PHASES]) assert.ok(concepts.has(`cn.${name}`), `cn.${name} has a concept entry`);
  const lifts = (ref) => (lexicon.targets[ref]?.liftsTo ?? []).map((l) => l.qname);
  assert.ok(lifts('er.entity.customer').includes('cn.Customer'), 'customer lifts to Customer');
  assert.ok(lifts('er.entity.sales.ext_sales_price').includes('cn.revenue'), 'the revenue column lifts to revenue');
  assert.ok(lifts('md.measure.revenue').includes('cn.revenue'), 'md.revenue lifts to revenue');
  assert.ok(!targets.some(([, t]) => (t.liftsTo ?? []).some((l) => PHASES.includes(l.qname.slice(3)))), 'no lift lands on a phase (L17-2)');
});
