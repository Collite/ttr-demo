// Stage 2.4 T5/T6 — cubelet<->fact binding completeness, aggregation, conformed-dim
// sharing, single-Money-revenue (currency-per-connection at the model tier).
// Mocked/unit: parses the whole model/ tree as one project (project-harness.mjs), no
// live DB. Run: node --test model/binding/tests/md2db.test.mjs (from the hartland root).

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadHartlandProject, ACCEPTED_RESIDUAL_CODES } from '../../tests/project-harness.mjs';

const EXPECTED_CUBELETS = [
  'storeSales', 'webSales', 'marketplaceSales',
  'storeReturns', 'webReturns', 'catalogReturns', 'inventory',
];

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

test('T6.1 — parse-clean: measures.ttrm, cubelets.ttrm, md2db.ttrm parse with zero errors', () => {
  const offenders = [];
  for (const [file, errors] of project.parseErrorsByFile) {
    if (['model/md/measures.ttrm', 'model/md/cubelets.ttrm', 'model/binding/md2db.ttrm'].includes(file) && errors.length) {
      offenders.push(`${file}: ${JSON.stringify(errors[0])}`);
    }
  }
  assert.deepEqual(offenders, [], `parse errors: ${offenders.join('; ')}`);
});

test('T6.2 — zero unexpected diagnostics project-wide (no md/shape-measure-mismatch, md/grain-ref-unknown, etc.)', () => {
  const offenders = [];
  for (const [file, codes] of project.diagnosticsByFile) {
    for (const code of codes) if (!ACCEPTED_RESIDUAL_CODES.has(code)) offenders.push(`${file}: ${code}`);
  }
  assert.deepEqual(offenders, [], `unexpected diagnostics: ${offenders.join('; ')}`);
});

test('T6.3 — cubelet<->fact completeness: every cubelet has an md2db_cubelet, shape wide, full grain+measure coverage', () => {
  const cubelets = allDefsOfKind('cubelet');
  const cubeletNames = cubelets.map(({ def }) => def.name);
  assert.deepEqual([...cubeletNames].sort(), [...EXPECTED_CUBELETS].sort());

  const bindings = allDefsOfKind('md2dbCubelet');
  const bindingByCubelet = new Map(bindings.map(({ def }) => [def.cubeletRef.split('.').pop(), def]));

  const problems = [];
  for (const { def: cubelet } of cubelets) {
    const binding = bindingByCubelet.get(cubelet.name);
    if (!binding) { problems.push(`${cubelet.name}: no md2db_cubelet`); continue; }
    if (binding.shape?.shape !== 'wide') problems.push(`${cubelet.name}: shape is not wide`);
    for (const grainRef of cubelet.grain) {
      if (!(grainRef in binding.attributes)) problems.push(`${cubelet.name}: grain '${grainRef}' unbound`);
    }
    for (const measureRef of cubelet.measures) {
      if (!(measureRef in binding.measures)) problems.push(`${cubelet.name}: measure '${measureRef}' unbound`);
    }
  }
  assert.deepEqual(problems, [], problems.join('; '));
});

test('T6.4 — single Money revenue: exactly one revenue measure, bound exactly once per fact (currency is a display fact, not a 2nd measure/binding)', () => {
  const measures = allDefsOfKind('measure');
  const revenueMeasures = measures.filter(({ def }) => def.name === 'revenue');
  assert.equal(revenueMeasures.length, 1, `expected exactly 1 'revenue' measure, got ${revenueMeasures.length}`);
  assert.equal(revenueMeasures[0].def.domainRef, 'md.Money', 'revenue must be Money-domained');

  const salesCubelets = ['storeSales', 'webSales', 'marketplaceSales'];
  const bindings = allDefsOfKind('md2dbCubelet');
  for (const name of salesCubelets) {
    const binding = bindings.find(({ def }) => def.cubeletRef === `md.${name}`);
    assert.ok(binding, `no md2db_cubelet for ${name}`);
    assert.ok('revenue' in binding.def.measures, `${name} doesn't bind revenue`);
  }
  // No per-currency duplicate cubelet/binding (e.g. no "marketplaceSalesUSD"/"...CZK").
  const cubeletNames = allDefsOfKind('cubelet').map(({ def }) => def.name);
  const currencySuffixed = cubeletNames.filter((n) => /usd|czk/i.test(n));
  assert.deepEqual(currencySuffixed, [], `found currency-suffixed cubelet(s): ${currencySuffixed.join(', ')}`);
});

test('T6.5 — aggregation correctness: revenue/returnAmount=sum, orderCount=countDistinct, onHandQty=semiAdditive+validBy', () => {
  const byName = new Map(allDefsOfKind('measure').map(({ def }) => [def.name, def]));
  assert.equal(byName.get('revenue').aggregation.default, 'sum');
  assert.equal(byName.get('returnAmount').aggregation.default, 'sum');
  assert.equal(byName.get('orderCount').aggregation.default, 'countDistinct');
  assert.equal(byName.get('lineCount').aggregation.default, 'count');
  const onHand = byName.get('onHandQty');
  assert.equal(onHand.measureClass, 'semiAdditive');
  assert.ok(onHand.validBy, 'semiAdditive onHandQty must declare validBy (md/semiadditive-no-validby)');
});

test('T6.6 — conformed-dimension sharing: Product/Calendar/Customer are each referenced by >=2 cubelets', () => {
  const cubelets = allDefsOfKind('cubelet');
  const dimUsage = new Map(); // dimension -> Set(cubelet names)
  for (const { def } of cubelets) {
    for (const grainRef of def.grain) {
      const dim = grainRef.split('.')[0];
      if (!dimUsage.has(dim)) dimUsage.set(dim, new Set());
      dimUsage.get(dim).add(def.name);
    }
  }
  for (const dim of ['Product', 'Calendar', 'Customer']) {
    const users = dimUsage.get(dim) ?? new Set();
    assert.ok(users.size >= 2, `${dim} used by only ${users.size} cubelet(s): ${[...users].join(', ')} — not conformed`);
  }
});

test('T6.8 — FULL-MODEL completeness: every dimension attribute has a physical binding', () => {
  // The gap this closes: T6.3 only checks that cubelet GRAIN KEYS + MEASURES bind. A
  // descriptive/analytic dimension attribute (storeName, dcName, promoName, reasonDesc,
  // productName, Customer.state, Customer.birthYear) has no lint rule forcing it to bind —
  // so the model can "load clean" with those dangling. This asserts each one is physically
  // reachable: a KEY via a cubelet grain binding; a non-key via a BOUND map to its domain
  // (a calc map, or a table-backed map that has an md2db_map).
  const boundMapNames = new Set(allDefsOfKind('md2dbMap').map(({ def }) => def.mapRef.split('.').pop()));
  const boundToDomains = new Set(); // domain qnames reachable via a bound map (calc or md2db_map)
  for (const { def } of allDefsOfKind('mdMap')) {
    if (def.calc != null || boundMapNames.has(def.name)) for (const d of def.to ?? []) boundToDomains.add(d);
  }
  const boundGrainKeys = new Set(); // "Dimension.attr" bound as a grain key in some cubelet
  for (const { def } of allDefsOfKind('md2dbCubelet')) for (const k of Object.keys(def.attributes ?? {})) boundGrainKeys.add(k);

  const unbound = [];
  for (const { def: dim } of allDefsOfKind('dimension')) {
    for (const attr of dim.attributes ?? []) {
      const qual = `${dim.name}.${attr.name}`;
      if (attr.isKey) {
        if (!boundGrainKeys.has(qual)) unbound.push(`${qual} (key: no cubelet grain binding)`);
      } else if (!boundToDomains.has(attr.domainRef)) {
        unbound.push(`${qual} (domain ${attr.domainRef}: no bound map)`);
      }
    }
  }
  assert.deepEqual(unbound, [], `dimension attributes with no physical binding: ${unbound.join('; ')}`);
});

test('T6.7 — no profit/margin/cost measure or domain anywhere in md', () => {
  const BANNED = ['profit', 'margin', 'cost'];
  const offenders = [];
  for (const { def, uri } of allDefsOfKind('measure')) {
    if (BANNED.some((t) => def.name.toLowerCase().includes(t))) offenders.push(`${uri}: measure ${def.name}`);
  }
  for (const { def, uri } of allDefsOfKind('mdDomain')) {
    if (BANNED.some((t) => def.name.toLowerCase().includes(t))) offenders.push(`${uri}: domain ${def.name}`);
  }
  assert.deepEqual(offenders, [], `profit/margin/cost leaked into md: ${offenders.join(', ')}`);
});

test('T6.9 — the calendar\'s month and year calc maps read date_dim: every fact\'s day is an int key, not a date (CN-P6 ⚑S62-2)', () => {
  // Inline, a calc map is a date extraction on the fact's day column; every fact binds Calendar.day to its
  // `*_date_sk` (an int into date_dim), and PostgreSQL has no EXTRACT on an integer — so a month or year filter on
  // any md path failed to run. With a case table the lowering joins date_dim on the key and reads its column.
  for (const { def } of allDefsOfKind('md2dbCubelet')) {
    const day = def.attributes?.['Calendar.day']?.column;
    if (day !== undefined) assert.match(day, /_date_sk$/, `${def.name}: Calendar.day binds ${day}`);
  }
  const caseTable = (map) => allDefsOfKind('md2dbMap').find(({ def }) => def.mapRef === map)?.def;
  assert.deepEqual(caseTable('md.day_to_month')?.columns, { 'md.Day': 'd_date_sk', 'md.Month': 'd_moy' });
  assert.deepEqual(caseTable('md.day_to_year')?.columns, { 'md.Day': 'd_date_sk', 'md.Year': 'd_year' });
});
