// The report folders (SO-demo P1·S1.1; report.yaml v1 = ttr-core SO-core contracts §3.1, C-8; LQ-5): every
// model/reports/<id>/ is a report.yaml + template.xlsx whose program is a `def query` the model loads and whose tables
// take only that program's output columns. master has no report yet — the first is the demo branch's (S1.2) — so RP3
// runs the same check on inline cases: a check that never fails would pass an empty folder and a broken one alike.
// The schema file (report.schema.json) is ttr-core SO-core P2's; until it ships, these are the rules by hand.
// Run: node --test model/reports/tests/report.test.mjs.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { access, readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import { loadHartlandProject, hartlandRoot } from '../../tests/project-harness.mjs';

// js-yaml borrowed from the sibling tatrman checkout, as model/queries/tests/queries.test.mjs does.
const tatrmanPackages = process.env.TATRMAN_PACKAGES ?? path.resolve(hartlandRoot, '../tatrman/packages');
const yaml = await import(
  path.resolve(tatrmanPackages, '../node_modules/.pnpm/js-yaml@4.1.1/node_modules/js-yaml/dist/js-yaml.mjs')
);

const reportsDir = path.join(hartlandRoot, 'model/reports');
const project = await loadHartlandProject();

// ── A query's output columns: the names of its outermost SELECT list ─────────────────────────────────────────────
// What LQ-3 calls `outputColumnNames` — the loader computes it in Kotlin; here, the SELECT list read as text: the
// first SELECT outside every parenthesis (a CTE's own SELECTs are inside one), up to its FROM; an item's name is its
// alias (`AS x`, or a trailing bare word), else a column's last dotted part. null when an item has no name.

function stripSql(sql) {
  // blank out comments and string literals, keeping offsets, so neither can fake a keyword, a comma or a paren
  return sql
    .replace(/--[^\n]*/g, (m) => ' '.repeat(m.length))
    .replace(/\/\*[\s\S]*?\*\//g, (m) => ' '.repeat(m.length))
    .replace(/'(?:[^']|'')*'/g, (m) => `'${' '.repeat(m.length - 2)}'`);
}

export function outputColumns(sql) {
  const s = stripSql(sql);
  let depth = 0;
  let start = -1;
  let end = -1;
  const items = [];
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (c === '(') depth++;
    else if (c === ')') depth--;
    else if (depth === 0 && /\w/.test(c) && !/\w/.test(s[i - 1] ?? '')) {
      const word = /^\w+/.exec(s.slice(i))[0].toUpperCase();
      if (start < 0 && word === 'SELECT') { start = i + word.length; items.push(start); }
      else if (start >= 0 && word === 'FROM') { end = i; break; }
    } else if (depth === 0 && start >= 0 && c === ',') items.push(i + 1);
  }
  if (start < 0 || end < 0) return null;
  const bounds = [...items, end + 1];
  const names = [];
  for (let k = 0; k < items.length; k++) {
    const item = sql.slice(bounds[k], bounds[k + 1] - 1).replace(/^\s*(?:DISTINCT|ALL)\s+/i, '').trim();
    const alias = /(?:\bAS\s+|(?<=[\w)\]"`])\s+)["[`]?([A-Za-z_]\w*)["\]`]?$/i.exec(item);
    const column = /^(?:[A-Za-z_]\w*\.)*([A-Za-z_]\w*)$/.exec(item);
    names.push(column ? column[1] : alias ? alias[1] : null);
  }
  return names;
}

// ── The programs a report may name: `er.query.<q>` (a logical query) and `db.query.<q>` (C-8 §3.1) ───────────────
// The lane is the symbol's schema, not the file's `model` line: `model query` (q_hartland.ttrm) registers db queries.
const queryDefs = new Map();
for (const [uri, ast] of project.asts) {
  for (const def of ast.definitions ?? []) if (def.kind === 'query') queryDefs.set(`${uri}#${def.name}`, def);
}
const programs = new Map();
for (const s of project.symbols.all()) {
  if (s.kind !== 'query') continue;
  const def = queryDefs.get(`${s.documentUri}#${s.name}`);
  programs.set(`${s.schemaCode}.query.${s.name}`, {
    lane: s.schemaCode,
    params: (def?.parameters ?? []).map((p) => p.name),
    columns: def?.sourceText?.value ? outputColumns(def.sourceText.value) : null,
  });
}

// ── The rules (C-8 §3.1) ──────────────────────────────────────────────────────────────────────────────────────────
const KEYS = ['id', 'title', 'version', 'program', 'params', 'refresh', 'sheets', 'history', 'roles'];
const PARAM_KINDS = ['text', 'int', 'float', 'bool', 'datetime', 'entity'];

export function reportProblems({ folder, report, hasTemplate }) {
  const problems = [];
  const r = report ?? {};
  for (const key of Object.keys(r)) if (!KEYS.includes(key)) problems.push(`unknown key ${key}`);
  if (!/^[a-z][a-z0-9_]*$/.test(r.id ?? '')) problems.push(`id ${r.id} is not ^[a-z][a-z0-9_]*$`);
  if (r.id !== folder) problems.push(`id ${r.id} is not the folder ${folder}`);
  if (typeof r.title?.en !== 'string') problems.push('title.en missing');
  if (r.version !== 1) problems.push(`version ${r.version} is not 1`);
  const program = programs.get(r.program);
  if (!/^(er|db)\.query\.\w+$/.test(r.program ?? '')) problems.push(`program ${r.program} is not er.query.<q> or db.query.<q>`);
  else if (!program) problems.push(`program ${r.program} is not a loaded def query`);
  if (!Array.isArray(r.params)) problems.push('params is not a list');
  else {
    if (program?.lane === 'er' && r.params.length) problems.push(`an er.query program takes no params (LQ-5): ${r.program}`);
    for (const p of r.params) {
      if (!PARAM_KINDS.includes(p?.kind)) problems.push(`param ${p?.name}: kind ${p?.kind}`);
      if (program?.lane === 'db' && !program.params.includes(p?.name)) problems.push(`param ${p?.name} is not a parameter of ${r.program}`);
    }
  }
  if (r.refresh !== undefined && !['daily', 'hourly', 'manual'].includes(r.refresh)) problems.push(`refresh ${r.refresh}`);
  if (!Array.isArray(r.sheets) || r.sheets.length === 0) problems.push('no sheets');
  for (const sheet of Array.isArray(r.sheets) ? r.sheets : []) {
    if (typeof sheet?.sheet !== 'string') problems.push('a sheet without a name');
    for (const [anchor, table] of Object.entries(sheet?.tables ?? {})) {
      if (!Array.isArray(table?.columns) || table.columns.length === 0) { problems.push(`table ${anchor}: no columns`); continue; }
      if (!program) continue;
      if (!program.columns || program.columns.includes(null)) { problems.push(`${r.program}: its output columns cannot be read`); continue; }
      const extra = table.columns.filter((c) => !program.columns.includes(c));
      if (extra.length) problems.push(`table ${anchor}: ${extra.join(', ')} not output by ${r.program}`);
    }
  }
  if (r.history !== undefined && !/^\d+d$/.test(r.history?.keep ?? '')) problems.push(`history.keep ${r.history?.keep}`);
  if (r.roles !== undefined && !(Array.isArray(r.roles) && r.roles.every((x) => typeof x === 'string'))) problems.push('roles is not a list of strings');
  if (!hasTemplate) problems.push('template.xlsx missing');
  return problems;
}

// ── The tests ─────────────────────────────────────────────────────────────────────────────────────────────────────

test('RP1 — the SELECT-list reader agrees with the model: customer_revenue is bound to exactly its query\'s output', () => {
  // LQ-3: a stacked entity's attributes are its query's output columns; the loader checks the same pair.
  const attributes = project.symbols.all()
    .filter((s) => s.kind === 'attribute' && s.parent === 'hartland.er.entity.customer_revenue').map((s) => s.name);
  assert.deepEqual(programs.get('er.query.revenue_per_customer').columns, attributes);
  assert.deepEqual(outputColumns('WITH a AS (SELECT x FROM t) SELECT DISTINCT a.x, COUNT(*) n, y AS "z" FROM a'), ['x', 'n', 'z']);
});

test('RP2 — every report folder under model/reports/ passes (none on master until the demo branch merges)', async () => {
  const folders = (await readdir(reportsDir, { withFileTypes: true }))
    .filter((e) => e.isDirectory() && e.name !== 'tests').map((e) => e.name);
  for (const folder of folders) {
    const dir = path.join(reportsDir, folder);
    const report = yaml.load(await readFile(path.join(dir, 'report.yaml'), 'utf-8'));
    const hasTemplate = await access(path.join(dir, 'template.xlsx')).then(() => true, () => false);
    assert.deepEqual(reportProblems({ folder, report, hasTemplate }), [], `model/reports/${folder}`);
  }
});

test('RP3 — the rules catch what they are for (inline cases over er.query.revenue_per_customer)', () => {
  const good = {
    id: 'customer_totals', title: { en: 'Customer totals' }, version: 1,
    program: 'er.query.revenue_per_customer', params: [], refresh: 'daily',
    sheets: [{ sheet: 'Summary', scalars: { title: '{{title}}' }, tables: { ROWS: { columns: ['customer_id', 'revenue'] } } }],
    history: { keep: '90d' }, roles: ['kantheon-role-finance'],
  };
  const check = (patch, opts = {}) =>
    reportProblems({ folder: 'customer_totals', report: { ...good, ...patch }, hasTemplate: true, ...opts });
  assert.deepEqual(check({}), []);
  assert.deepEqual(check({}, { folder: 'other' }), ['id customer_totals is not the folder other']);
  assert.deepEqual(check({}, { hasTemplate: false }), ['template.xlsx missing']);
  assert.deepEqual(check({ program: 'er.query.nope' }), ['program er.query.nope is not a loaded def query']);
  assert.deepEqual(check({ params: [{ name: 'year', kind: 'int' }] }),
    ['an er.query program takes no params (LQ-5): er.query.revenue_per_customer']);
  assert.deepEqual(check({ sheets: [{ sheet: 'Summary', tables: { ROWS: { columns: ['customer_id', 'margin'] } } }] }),
    ['table ROWS: margin not output by er.query.revenue_per_customer']);
  assert.deepEqual(check({ colour: 'red' }), ['unknown key colour']);
  assert.deepEqual(
    check({ program: 'db.query.channel_revenue_yoy', params: [{ name: 'year', kind: 'int' }, { name: 'month', kind: 'int' }],
      sheets: [{ sheet: 'Summary', tables: { ROWS: { columns: ['channel', 'yoy_pct'] } } }] }),
    ['param month is not a parameter of db.query.channel_revenue_yoy'],
  );
});
