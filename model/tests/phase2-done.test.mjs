// Phase 2 DONE bar — the phase exit (Stage 2.6 T6.6). Each assertion here is already
// covered by its owning stage's suite; this file exists as the single place that states
// the roll-up explicitly, so "is Phase 2 done" has one direct answer instead of an
// implication across 6 files. Run: node --test model/tests/phase2-done.test.mjs.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { loadHartlandProject, ACCEPTED_RESIDUAL_CODES, hartlandRoot, isOwnModelFile } from './project-harness.mjs';

const project = await loadHartlandProject();

test('DONE 1 — the model loads clean: zero parse errors anywhere under model/', () => {
  const offenders = [];
  for (const [file, errors] of project.parseErrorsByFile) if (errors.length) offenders.push(file);
  assert.deepEqual(offenders, [], `parse errors: ${offenders.join(', ')}`);
});

test('DONE 2 — resolves against both connection descriptors (schema-identical, one physical model)', async () => {
  const toml = await readFile(path.join(hartlandRoot, 'model/connections.toml'), 'utf-8');
  const connections = [...toml.matchAll(/id\s*=\s*"([^"]+)"/g)].map((m) => m[1]);
  // The two WORLDS are still exactly two and still first — BM-8's "one world per delivery" is what
  // this line has always been about. IE-P2·S2.3 added a third descriptor, `pg-entry`, and it is not
  // a world: it is a different DATABASE holding a different package's tables (`db.dbo.investment_*`,
  // synced into model/investment/), routed to by qname prefix, and live at the same time as
  // whichever world is delivered.
  assert.deepEqual(connections.filter((c) => c.startsWith('pg-hartland-')), ['pg-hartland-us', 'pg-hartland-cz']);
  assert.ok(connections.includes('pg-entry'), 'the investment book has no connection descriptor (IE-C26)');
  assert.deepEqual(connections, ['pg-hartland-us', 'pg-hartland-cz', 'pg-entry'], 'an undeclared connection appeared');
  // "Schema-identical" = every descriptor declares schema="dbo", the modeler.toml handle everything
  // above resolved against — including pg-entry, whose tables are physically in `public` and whose
  // db layer says `dbo` anyway, because the query door resolves unqualified DB identifiers there
  // (S2.3·D1b). The handle is a catalog label, not a database schema.
  const schemas = [...toml.matchAll(/schema\s*=\s*"([^"]+)"/g)].map((m) => m[1]);
  assert.ok(schemas.every((s) => s === 'dbo'), `every connection must target the same schema handle: ${schemas.join(', ')}`);
});

test('DONE 3 — ResolveArea("hartland") is green', () => {
  const resolved = project.areaTable.get('hartland');
  assert.ok(resolved);
  assert.ok(resolved.resolvedEntities.length > 0);
});

test('DONE 4 — ListQueries returns exactly 16 q.hartland.* with params', () => {
  // ⛔ IE-P2·S2.3: this counted EVERY query in the project while its name promised
  // `q.hartland.*`, so the synced investment package pushed it to 22 and the failure read as a
  // regression in a roster nobody had touched. Scoped to the files this repo authors; the seven
  // that arrived with the sync are asserted in model/queries/tests/queries.test.mjs T6.7.
  let own = 0;
  let synced = 0;
  for (const [uri, ast] of project.asts) {
    for (const def of ast.definitions ?? []) {
      if (def.kind !== 'query') continue;
      if (isOwnModelFile(uri)) own++; else synced++;
    }
  }
  assert.equal(own, 16, 'the D-2 roster + LR\'s channel_revenue_monthly_yoy (2026-10-10)');
  // Nine since IE-P3·S3.1 (period_values + portfolio_header joined the seven); nineteen since
  // IA-P3·S3.1 (the ten Browse programs, kantheon contracts IA-C35 … IA-C42); twenty since IA-P3·S3.3
  // (`clients_list`); twenty-one since IA-P4·S4.1 (`conversion_rates`).
  assert.equal(synced, 21, 'the 21 q.investment.* programs, synced from kantheon');
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
