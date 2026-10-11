// Stage 2.2 T6 — entity/relationship resolution, er2db completeness, measures policy.
// Mocked/unit: parses the whole model/ tree as one project (project-harness.mjs), no
// live DB. Run: node --test model/er/tests/er.test.mjs (from the hartland repo root).

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadHartlandProject, ACCEPTED_RESIDUAL_CODES } from '../../tests/project-harness.mjs';

// D-5 roster (05-d-ttrm-spec.md) — the 19 D-5 entities, no D-5-Out entity (time_dim, web_site,
// web_page, catalog_page, ship_mode, dbgen_version) — plus `channel_sales` (2026-09-24), the
// all-channel view-backed fact that lets "revenue by channel" be asked on the fast path.
const EXPECTED_ENTITIES = [
  'store_sales', 'web_sales', 'catalog_sales', 'channel_sales',
  'store_returns', 'web_returns', 'catalog_returns',
  'inventory', 'date_dim', 'item', 'customer', 'customer_address',
  'customer_demographics', 'household_demographics', 'income_band',
  'store', 'warehouse', 'reason', 'promotion', 'call_center',
];
const D5_OUT = ['time_dim', 'web_site', 'web_page', 'catalog_page', 'ship_mode', 'dbgen_version'];

const BANNED_MEASURE_TOKENS = ['net_profit', 'net_paid', 'wholesale_cost', 'list_price', 'margin'];

const project = await loadHartlandProject();

function allDefsOfKind(kind) {
  const out = [];
  for (const [uri, ast] of project.asts) {
    for (const def of ast.definitions ?? []) {
      if (def.kind === kind) out.push({ def, uri });
    }
  }
  return out;
}

test('T6.1 — parse-clean: every model/er + model/binding file parses with zero errors', () => {
  const offenders = [];
  for (const [file, errors] of project.parseErrorsByFile) {
    if ((file.startsWith('model/er/') || file.startsWith('model/binding/')) && errors.length) {
      offenders.push(`${file}: ${JSON.stringify(errors[0])}`);
    }
  }
  assert.deepEqual(offenders, [], `parse errors: ${offenders.join('; ')}`);
});

test('T6.2 — exactly the D-5 entities (+ channel_sales) are declared, no D-5-Out entity', () => {
  const entities = allDefsOfKind('entity').map((e) => e.def.name);
  const missing = EXPECTED_ENTITIES.filter((e) => !entities.includes(e));
  const stray = D5_OUT.filter((e) => entities.includes(e));
  assert.deepEqual(missing, [], `missing entities: ${missing.join(', ')}`);
  assert.deepEqual(stray, [], `D-5-Out entities present: ${stray.join(', ')}`);
  assert.equal(entities.length, EXPECTED_ENTITIES.length, `expected exactly ${EXPECTED_ENTITIES.length} entities, got ${entities.length}: ${entities.join(', ')}`);
});

test('T6.3 — no unresolved references anywhere in the project (er/relations/binding cross-refs all resolve)', () => {
  const offenders = [];
  for (const [file, codes] of project.diagnosticsByFile) {
    for (const code of codes) {
      if (!ACCEPTED_RESIDUAL_CODES.has(code)) offenders.push(`${file}: ${code}`);
    }
  }
  assert.deepEqual(offenders, [], `unexpected diagnostics: ${offenders.join('; ')}`);
});

test('T6.4 — every def relation from/to/binding.fk resolves', () => {
  const relations = allDefsOfKind('relation');
  assert.ok(relations.length > 0, 'expected at least one def relation');
  const dangling = [];
  for (const { def } of relations) {
    for (const [label, idNode] of [['from', def.from], ['to', def.to]]) {
      const res = project.resolver.resolveReference(
        { path: idNode.path, parts: idNode.parts },
        { schemaCode: 'er', namespace: 'entity' },
      );
      if (!res.resolved) dangling.push(`${def.name}.${label}: ${idNode.path}`);
    }
    if (def.binding?.fk) {
      const res = project.resolver.resolveReference(
        { path: def.binding.fk.path, parts: def.binding.fk.parts },
        { schemaCode: 'db', namespace: 'dbo' },
      );
      if (!res.resolved) dangling.push(`${def.name}.binding.fk: ${def.binding.fk.path}`);
    }
  }
  assert.deepEqual(dangling, [], `dangling relation refs: ${dangling.join('; ')}`);
});

test('T6.5 — er2db completeness: every entity has an er2db_entity, every attribute has an er2db_attribute', () => {
  const entities = allDefsOfKind('entity');
  const er2dbEntities = allDefsOfKind('er2dbEntity');
  const er2dbAttributes = allDefsOfKind('er2dbAttribute');

  const boundEntityPaths = new Set(er2dbEntities.map((e) => e.def.entity.path));
  const boundAttrPaths = new Set(er2dbAttributes.map((a) => a.def.attribute.path));

  const unboundEntities = [];
  const unboundAttributes = [];
  for (const { def } of entities) {
    const entityPath = `er.entity.${def.name}`;
    if (!boundEntityPaths.has(entityPath)) unboundEntities.push(entityPath);
    for (const attr of def.attributes ?? []) {
      const attrPath = `er.entity.${def.name}.${attr.name}`;
      if (!boundAttrPaths.has(attrPath)) unboundAttributes.push(attrPath);
    }
  }
  assert.deepEqual(unboundEntities, [], `entities without er2db_entity: ${unboundEntities.join(', ')}`);
  assert.deepEqual(unboundAttributes, [], `attributes without er2db_attribute: ${unboundAttributes.join(', ')}`);
});

test('T6.6 — ResolveArea("hartland") is green: non-empty, contains the 3 channel facts', () => {
  const resolved = project.areaTable.get('hartland');
  assert.ok(resolved, 'area "hartland" not found');
  assert.ok(resolved.resolvedEntities.length > 0, 'resolvedEntities is empty');
  for (const fact of ['catalog_sales', 'store_sales', 'web_sales']) {
    assert.ok(
      resolved.resolvedEntities.includes(`hartland.er.entity.${fact}`),
      `resolvedEntities missing ${fact}: ${resolved.resolvedEntities.join(', ')}`,
    );
  }
});

test('T6.7 — measures policy (D-6a): no profit/margin/cost token in any er attribute or entity name', () => {
  const offenders = [];
  for (const { def, uri } of allDefsOfKind('entity')) {
    for (const attr of def.attributes ?? []) {
      if (BANNED_MEASURE_TOKENS.some((t) => attr.name.includes(t))) {
        offenders.push(`${uri}: ${def.name}.${attr.name}`);
      }
    }
  }
  assert.deepEqual(offenders, [], `profit/margin attribute leaked into er: ${offenders.join(', ')}`);
});

// LR ⚑LR-9 (C-5·4) — the DC-scope persona's row rule narrows channel_sales and web_sales by their
// distribution centre, so the model says how each reaches one. channel_sales' reach is NULLABLE: a
// store line is not fulfilled by a DC (`warehouse_sk` is NULL there), so the join keeps only web and
// marketplace lines — exactly what the persona's rule leaves them. web_sales follows catalog_sales.
const objectEntry = (node, key) => node?.entries?.find((e) => e.key === key)?.value;

test('LR ⚑LR-9 — channel_sales and web_sales reach the distribution centre; a store line reaches none', () => {
  const byName = (kind, name) => allDefsOfKind(kind).find((d) => d.def.name === name)?.def;
  const expected = [
    ['channel_sales', 'rel_channel_sales_warehouse', 'db.dbo.fk_chs_warehouse', 'db.dbo.channel_sales.warehouse_sk', '0..1'],
    ['web_sales', 'rel_web_sales_warehouse', 'db.dbo.fk_ws_warehouse', 'db.dbo.web_sales.ws_warehouse_sk', '1'],
  ];
  for (const [entity, relation, fk, column, to] of expected) {
    const e = byName('entity', entity);
    assert.ok(e?.attributes?.some((a) => a.name === 'warehouse'), `${entity} has no 'warehouse' attribute`);

    const r = byName('relation', relation);
    assert.ok(r, `${relation} is not declared`);
    assert.equal(r.from.path, `er.entity.${entity}`);
    assert.equal(r.to.path, 'er.entity.warehouse');
    assert.equal(r.binding?.fk?.path, fk);
    assert.equal(objectEntry(r.cardinality, 'to')?.value, to, `${relation} cardinality.to`);

    const bound = allDefsOfKind('er2dbAttribute').find((a) => a.def.attribute.path === `er.entity.${entity}.warehouse`);
    assert.equal(objectEntry(bound?.def.target, 'column')?.path, column, `${entity}.warehouse binds to ${column}`);
  }
});
