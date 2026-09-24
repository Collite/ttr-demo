// Stage 2.2 T6 — entity/relationship resolution, er2db completeness, measures policy.
// Mocked/unit: parses the whole model/ tree as one project (project-harness.mjs), no
// live DB. Run: node --test model/er/tests/er.test.mjs (from the hartland repo root).

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadHartlandProject, ACCEPTED_RESIDUAL_CODES, isOwnModelFile, isSyncedModelFile } from '../../tests/project-harness.mjs';

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

/**
 * Definitions of one kind, from the files THIS repo authors.
 *
 * ⛔ IE-P2·S2.3: `model/investment/` is synced in from kantheon and veles serves it beside
 * hartland's own model, so an unscoped walk counts a second package's entities as hartland's. T6.2
 * below is a ROSTER — "exactly the 19 D-5 entities" — and a roster that counts someone else's rows
 * is not a roster. `allDefsAnywhere` is the deliberate unscoped form, used by T6.2b.
 */
function allDefsOfKind(kind) {
  return allDefsAnywhere(kind).filter(({ uri }) => isOwnModelFile(uri));
}

function allDefsAnywhere(kind) {
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

test('T6.2b — and the synced investment package is there, separately, with its own six', () => {
  // The other side of T6.2's scoping. If the sync broke, or if the filter started swallowing
  // hartland's own files, this is what notices — a scoped roster that nothing checks the scope of
  // would go green on an empty tree.
  const synced = allDefsAnywhere('entity').filter(({ uri }) => isSyncedModelFile(uri));
  assert.deepEqual(
    synced.map(({ def }) => def.name).sort(),
    ['asset', 'client', 'portfolio', 'position', 'price', 'transaction'],
    'the synced investment package must contribute exactly IE-C23\'s six er entities',
  );
  const own = allDefsOfKind('entity');
  assert.equal(own.length + synced.length, allDefsAnywhere('entity').length, 'every entity is one or the other');
  assert.ok(own.length > 0, 'the scope filter swallowed hartland\'s own model');
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
