// Phase 2 DONE bar — the phase exit (Stage 2.6 T6.6). Each assertion here is already
// covered by its owning stage's suite; this file exists as the single place that states
// the roll-up explicitly, so "is Phase 2 done" has one direct answer instead of an
// implication across 6 files. Run: node --test model/tests/phase2-done.test.mjs.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { loadHartlandProject, ACCEPTED_RESIDUAL_CODES, hartlandRoot } from './project-harness.mjs';

const project = await loadHartlandProject();

test('DONE 1 — the model loads clean: zero parse errors anywhere under model/', () => {
  const offenders = [];
  for (const [file, errors] of project.parseErrorsByFile) if (errors.length) offenders.push(file);
  assert.deepEqual(offenders, [], `parse errors: ${offenders.join(', ')}`);
});

test('DONE 2 — resolves against both connection descriptors (schema-identical, one physical model)', async () => {
  const toml = await readFile(path.join(hartlandRoot, 'model/connections.toml'), 'utf-8');
  const connections = [...toml.matchAll(/id\s*=\s*"([^"]+)"/g)].map((m) => m[1]);
  // The two WORLDS, exactly — BM-8's "one world per delivery".
  assert.deepEqual(connections, ['pg-hartland-us', 'pg-hartland-cz'], 'an undeclared connection appeared');
  // "Schema-identical" = every descriptor declares schema="dbo", the modeler.toml handle everything
  // above resolved against. The handle is a catalog label, not a database schema.
  const schemas = [...toml.matchAll(/schema\s*=\s*"([^"]+)"/g)].map((m) => m[1]);
  assert.ok(schemas.every((s) => s === 'dbo'), `every connection must target the same schema handle: ${schemas.join(', ')}`);
});

test('DONE 3 — ResolveArea("hartland") is green', () => {
  const resolved = project.areaTable.get('hartland');
  assert.ok(resolved);
  assert.ok(resolved.resolvedEntities.length > 0);
});

test('DONE 4 — ListQueries returns 23: the 17 q.hartland.* with params + the six logical queries', () => {
  // veles lists every `def query` it loaded (ListQueries; GetModel's namedQueries), a logical query too.
  // A `def query` in a `model er` file is a logical query (LQ): not a q.hartland.* pattern, and agents are
  // meant to ask over the entity stacked on it (LQ-6) — model/er/customer_revenue.ttrm says why its name
  // is its own. If veles stops listing logical queries, this becomes 17 again.
  const db = [];
  const logical = [];
  for (const [, ast] of project.asts) {
    for (const def of ast.definitions ?? []) {
      if (def.kind === 'query') (ast.modelDirective?.modelCode === 'er' ? logical : db).push(def.name);
    }
  }
  assert.equal(db.length, 17, 'the D-2 roster + LR\'s channel_revenue_monthly_yoy (2026-10-10) + warehouse_stockout_week_count (2026-10-11)');
  assert.deepEqual(logical.sort(), ['placed_order_q', 'returns_monthly_by_category', 'returns_union', 'revenue_per_customer', 'sales_union', 'stockouts_monthly_dc'], 'the logical queries (LQ 2026-10-18, BI-4 2026-10-22, md/hop HP-H 2026-10-24, CN-P6 S6.1 2026-10-24)');
  assert.equal(db.length + logical.length, 23);
});

test('DONE 5 — cs + en lexicon resolves (zero unresolved for:, project-wide)', () => {
  const offenders = [];
  for (const [file, codes] of project.diagnosticsByFile) {
    for (const code of codes) if (!ACCEPTED_RESIDUAL_CODES.has(code)) offenders.push(`${file}: ${code}`);
  }
  assert.deepEqual(offenders, []);
});

test('DONE 6 — no net_profit/cost column reachable anywhere under model/', async () => {
  const { readdir } = await import('node:fs/promises');
  async function walk(dir) {
    const out = [];
    for (const e of await readdir(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) { if (e.name === '.schema-ref') continue; out.push(...await walk(p)); }
      else if (e.name.endsWith('.ttrm')) out.push(p);
    }
    return out;
  }
  const files = await walk(path.join(hartlandRoot, 'model'));
  const BANNED = /net_profit|wholesale_cost|list_price|net_paid|margin/i;
  const offenders = [];
  for (const f of files) {
    const text = await readFile(f, 'utf-8');
    const codeLines = text.split('\n').filter((l) => !l.trim().startsWith('//'));
    if (BANNED.test(codeLines.join('\n'))) offenders.push(path.relative(hartlandRoot, f));
  }
  assert.deepEqual(offenders, [], `profit/cost token in non-comment code: ${offenders.join(', ')}`);
});

test('DONE 7 — both Shems exist with prompts mounted (assembly contract; see agents/tests/shems.test.mjs for the full check)', async () => {
  const { readdir } = await import('node:fs/promises');
  for (const shem of ['golem-hartland', 'golem-hartland-finance']) {
    const shemYaml = await readFile(path.join(hartlandRoot, `agents/golem/shems/${shem}/shem.yaml`), 'utf-8');
    assert.ok(shemYaml.includes('visibility_roles'), `${shem}: no visibility_roles`);
    for (const locale of ['en', 'cs']) {
      const files = await readdir(path.join(hartlandRoot, `agents/golem/shems/${shem}/prompts/${locale}`));
      assert.ok(files.length > 0, `${shem}/prompts/${locale} is empty`);
    }
  }
});
