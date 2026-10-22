// Stage 2.2 T6 — entity/relationship resolution, er2db completeness, measures policy.
// Mocked/unit: parses the whole model/ tree as one project (project-harness.mjs), no
// live DB. Run: node --test model/er/tests/er.test.mjs (from the hartland repo root).

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadHartlandProject, ACCEPTED_RESIDUAL_CODES } from '../../tests/project-harness.mjs';

// D-5 roster (05-d-ttrm-spec.md) — the 19 D-5 entities, no D-5-Out entity (time_dim, web_site,
// web_page, catalog_page, ship_mode, dbgen_version) — plus `channel_sales` (2026-09-24), the
// all-channel view-backed fact that lets "revenue by channel" be asked on the fast path — plus
// `customer_revenue` (LQ, 2026-10-18), stacked on the logical query `er.query.revenue_per_customer`, and
// `dc_stockout_month` (BI-4, 2026-10-22), stacked on `er.query.stockouts_monthly_dc`.
const EXPECTED_ENTITIES = [
  'store_sales', 'web_sales', 'catalog_sales', 'channel_sales', 'customer_revenue', 'dc_stockout_month',
  'store_returns', 'web_returns', 'catalog_returns',
  'inventory', 'date_dim', 'item', 'customer', 'customer_address',
  'customer_demographics', 'household_demographics', 'income_band',
  'store', 'warehouse', 'reason', 'promotion', 'call_center',
  // AU (automation agents) S0.1 — the H-1/H-2 extension and the H-3/H-5 write-back entities; their shape
  // is asserted by model/tests/automation-extension.test.mjs, this roster only keeps the count exact.
  'order', 'sales_line', 'price_list', 'customer_price', 'invoice', 'warehouse_outage',
  'return_request', 'return_request_line', 'return_receipt', 'credit_note', 'refund_payment',
  'replacement_shipment', 'document_flow', 'reorder_proposal', 'winback_mail',
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

test('T6.2 — exactly the D-5 entities (+ channel_sales, + the AU extension) are declared, no D-5-Out entity', () => {
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

// An entity stacked on a query (LQ) binds to the query's OUTPUT columns, not to db columns, so it has
// no er2db_entity / er2db_attribute to give: its binding is the inline `target: { query: … }`, and the
// metadata service checks its attributes against the query's output (T-LQ below pins the shape).
function stackedOnQuery(def) {
  const target = def.binding?.kind === 'block' ? def.binding.target : undefined;
  return !!target && 'entries' in target && target.entries.some((e) => e.key === 'query');
}

test('T6.5 — er2db completeness: every entity has an er2db_entity, every attribute has an er2db_attribute', () => {
  const entities = allDefsOfKind('entity').filter(({ def }) => !stackedOnQuery(def));
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

// ttr-demo#62 remedy 3 (Bora, 2026-10-12) — "How many stores do we have?" is 6, not 12. `store` keeps
// SCD-2 history (12 rows for 6 stores), and the composer once counted the rows. TTR-M says it in its own
// vocabulary — the `valid_from`/`valid_to` validity pair on the row's history dates — and in the one
// place today's reader looks: the composer is shown the FIRST line of an entity's description
// (kantheon PlanComposer.describeFirstLine) and no semantic role, so that line names both ways to count.
test('#62 — store says it is SCD-2: the validity pair on its history columns, and how to count it', () => {
  const store = allDefsOfKind('entity').find((d) => d.def.name === 'store')?.def;
  assert.ok(store, 'no entity store');
  const roleOf = (name) => store.attributes.find((a) => a.name === name)?.semantics?.entries?.role;
  assert.equal(roleOf('rec_start_date'), 'valid_from', 'store.rec_start_date is not role valid_from');
  assert.equal(roleOf('rec_end_date'), 'valid_to', 'store.rec_end_date is not role valid_to');
  for (const [attr, column] of [['rec_start_date', 'db.dbo.store.s_rec_start_date'], ['rec_end_date', 'db.dbo.store.s_rec_end_date']]) {
    const bound = allDefsOfKind('er2dbAttribute').find((a) => a.def.attribute.path === `er.entity.store.${attr}`);
    assert.equal(objectEntry(bound?.def.target, 'column')?.path, column, `store.${attr} binds to ${column}`);
  }
  const firstLine = store.description.value.split('\n').map((l) => l.trim()).find(Boolean);
  for (const needle of ['store_id', 'rec_end_date']) assert.ok(firstLine.includes(needle), `the description's first line names no ${needle}: ${firstLine}`);
});

test('T-LQ — customer_revenue is stacked on a logical query: declared in a model er file, no parameters, relations by join pairs', () => {
  const stacked = allDefsOfKind('entity').filter(({ def }) => stackedOnQuery(def));
  assert.deepEqual(stacked.map(({ def }) => def.name).sort(), ['customer_revenue', 'dc_stockout_month']);
  const { def: entity, uri } = stacked.find(({ def }) => def.name === 'customer_revenue');

  const target = entity.binding.target.entries.find((e) => e.key === 'query').value;
  assert.equal(target.path, 'er.query.revenue_per_customer', 'the binding names the logical query by its er.query qname');

  const ast = project.asts.get(uri);
  assert.equal(ast.modelDirective?.modelCode, 'er', 'the query lives in a `model er` file — that is what makes it logical');
  const query = (ast.definitions ?? []).find((d) => d.kind === 'query' && d.name === 'revenue_per_customer');
  assert.ok(query, 'the logical query is declared beside the entity');
  assert.equal(query.parameters ?? undefined, undefined, 'a logical query takes no parameters');
  // Not named after the entity: veles still lists a logical query (ListQueries, GetModel namedQueries), and
  // golem's descriptor lookup tries a query's local name before an entity's (model/er/customer_revenue.ttrm).
  const entityNames = new Set(allDefsOfKind('entity').map(({ def }) => def.name));
  assert.ok(!entityNames.has(query.name), `the logical query shares its local name with an entity: ${query.name}`);

  // Every attribute is unbound, so each names the query output column of its own name: the SELECT list
  // must produce exactly those names (the metadata service's output check, mirrored statically).
  // `sourceText.value` is the body as the TS AST carries it (the queries suite reads the same field).
  const body = query.sourceText?.value ?? '';
  assert.match(body, /^\s*select\b[\s\S]*\bfrom\b/i, `the body is no SELECT … FROM: ${JSON.stringify(body)}`);
  const select = body.slice(body.search(/select/i) + 6, body.search(/\bfrom\b/i));
  const outputs = select.split(',').map((c) => c.trim().split(/\s+as\s+|\./i).pop().trim());
  assert.deepEqual(outputs.sort(), (entity.attributes ?? []).map((a) => a.name).sort());

  // No foreign key in ANY form: neither `binding: { fk: db.dbo.fk_x }` nor the bare `binding: db.dbo.fk_x`.
  // A stacked entity has no table, so a relation from it states `join:` pairs and binds nothing.
  for (const name of ['rel_customer_revenue_hdemo', 'rel_customer_revenue_customer']) {
    const rel = allDefsOfKind('relation').find(({ def }) => def.name === name)?.def;
    assert.ok(rel, `${name} is declared`);
    assert.equal(rel.binding ?? undefined, undefined, `${name}: a stacked entity has no foreign key, so the relation has no binding`);
    assert.ok(rel.join, `${name} states join: pairs`);
  }

  // All time: no date attribute and no relation to the calendar, and the descriptions say so.
  const attrs = (entity.attributes ?? []).map((a) => a.name);
  assert.ok(!attrs.some((a) => /date|year_month|month|quarter/.test(a)), `customer_revenue gained a date-like attribute: ${attrs}`);
  const toCalendar = allDefsOfKind('relation').filter(({ def }) => def.from?.path === 'er.entity.customer_revenue' && def.to?.path === 'er.entity.date_dim');
  assert.deepEqual(toCalendar.map(({ def }) => def.name), [], 'customer_revenue reaches the calendar');
  for (const [what, text] of [['entity', entity.description?.value], ['query', query.description?.value]]) {
    assert.match(text ?? '', /all[- ]time/i, `the ${what}'s description does not say it is all time: ${text}`);
  }

  // No code facet: `customer` holds `customer_id` as its code; a second head with the same pattern would split a
  // code-shaped literal between the two.
  assert.equal(entity.semantics?.entries?.code ?? undefined, undefined, 'customer_revenue declares a code facet');
  assert.deepEqual(entity.semantics?.entries?.measures, ['revenue'], 'revenue stays the measure');
});

/** The select list of a body's OUTERMOST SELECT: past any WITH, at parenthesis depth 0, split on top-level commas. */
function outerSelectList(body) {
  const tokens = [];
  let depth = 0;
  let start = 0;
  let inSelect = false;
  for (let i = 0; i < body.length; i++) {
    const c = body[i];
    if (c === '(') depth++;
    else if (c === ')') depth--;
    if (depth !== 0) continue;
    const word = /^\w+/.exec(body.slice(i))?.[0]?.toLowerCase();
    const atWord = word && (i === 0 || !/\w/.test(body[i - 1]));
    if (atWord && word === 'select') { inSelect = true; start = i + 6; tokens.length = 0; }
    else if (atWord && word === 'from' && inSelect) { tokens.push(body.slice(start, i)); return tokens; }
    else if (c === ',' && inSelect) { tokens.push(body.slice(start, i)); start = i + 1; }
  }
  return tokens;
}

// BI-4 (contracts C-22, 2026-10-22). The dataset of Superset's "DC meltdown — stock-outs" dashboard and the object the
// Golem binds monthly stock-out questions to: one row per distribution center per month.
test('T-LQ-BI — dc_stockout_month is stacked on the logical query stockouts_monthly_dc: entities only, parameterless, the seed\'s stock-out week', () => {
  const found = allDefsOfKind('entity').find(({ def }) => def.name === 'dc_stockout_month');
  assert.ok(found, 'dc_stockout_month is declared');
  const { def: entity, uri } = found;
  assert.equal(objectEntry(entity.binding.target, 'query')?.path, 'er.query.stockouts_monthly_dc');

  const ast = project.asts.get(uri);
  assert.equal(ast.modelDirective?.modelCode, 'er', 'the query lives in a `model er` file — that is what makes it logical');
  const query = (ast.definitions ?? []).find((d) => d.kind === 'query' && d.name === 'stockouts_monthly_dc');
  assert.ok(query, 'the logical query is declared beside the entity');
  assert.equal(query.parameters ?? undefined, undefined, 'parameterless (D-23): a dashboard and the Golem read it as it is');
  const entityNames = new Set(allDefsOfKind('entity').map(({ def }) => def.name));
  assert.ok(!entityNames.has(query.name), `the logical query shares its local name with an entity: ${query.name}`);

  // Over entities, never the physical layer: no db name, no TPC-DS column.
  const body = query.sourceText?.value ?? '';
  assert.doesNotMatch(body, /\bdb\.|\bdbo\b|\b(inv|w|d)_\w+/i, 'the body names a table or a physical column');

  // A stock-out week is the seed's (and warehouse_stockout_week_count's): at least half of the DC's rows for the
  // week at zero. Counted per weekly snapshot first, then per month — hence a WITH, and the OUTER select list must
  // produce exactly the attributes (each unbound, so each names the output column of its own name).
  assert.match(body, /=\s*0\s+then\s+1\s+else\s+0/i, 'a zero row is quantity_on_hand = 0');
  assert.match(body, /2\s*\*\s*[\w.]*zero_rows\s*>=\s*[\w.]*total_rows/i, 'a stock-out week is at least half of the rows at zero');
  assert.match(body, /group by[^)]*as_of_date/i, 'the weekly step groups by the snapshot');
  const outputs = outerSelectList(body).map((c) => c.trim().split(/\s+as\s+|\./i).pop().trim());
  assert.deepEqual([...outputs].sort(), (entity.attributes ?? []).map((a) => a.name).sort());

  // No foreign key: relations state join pairs — to its DC, and to the calendar day the month starts on, so a
  // question's year or quarter narrows the months.
  const relations = allDefsOfKind('relation').map(({ def }) => def).filter((r) => r.from?.path === 'er.entity.dc_stockout_month');
  const pairs = Object.fromEntries(relations.map((r) => {
    assert.equal(r.binding ?? undefined, undefined, `${r.name}: a stacked entity has no foreign key, so the relation has no binding`);
    return [r.to.path, (r.join?.items ?? []).map((o) => [objectEntry(o, 'from')?.path, objectEntry(o, 'to')?.path])];
  }));
  assert.deepEqual(pairs, {
    'er.entity.warehouse': [['er.entity.dc_stockout_month.warehouse', 'er.entity.warehouse.sk']],
    'er.entity.date_dim': [['er.entity.dc_stockout_month.month_start', 'er.entity.date_dim.cal_date']],
  });

  // The label names the object. A label is a METADATA term and outranks a declared phrase (ttr-demo#62), so it
  // must not be the stock-out words a question asks with: «Kolik týdnů v roce 2025 mělo Brno DC výpadky zásob?»
  // (act 3.5) stays the saved query's.
  const fold = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  for (const label of [...Object.values(entity.displayLabel?.entries ?? {}), entity.labelPlural ?? '']) {
    assert.doesNotMatch(fold(label), /^(vypadky zasob|stock ?outs?|stock ?out weeks)$/, `the label «${label}» is a stock-out phrase`);
  }
  assert.deepEqual(entity.semantics?.entries?.measures, ['stockout_weeks'], 'stock-out weeks are the measure');
  assert.ok((entity.description?.value ?? '').includes('at least half'), 'the description says what a stock-out week is');
});
