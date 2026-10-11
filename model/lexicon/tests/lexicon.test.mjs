// Stage 2.5 T5/T6 — lexicon parse-clean, en/cs twin parity, diacritic folding,
// bilingual valueLabels coverage. Mocked/unit: parses the whole model/ tree as one
// project (project-harness.mjs) plus runs the real desugarLexicon/foldId pipeline from
// @tatrman/semantics, no live DB. Run: node --test model/lexicon/tests/lexicon.test.mjs
// (from the hartland repo root).

import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { loadHartlandProject, ACCEPTED_RESIDUAL_CODES, hartlandRoot } from '../../tests/project-harness.mjs';

const tatrmanPackages = process.env.TATRMAN_PACKAGES ?? path.resolve(hartlandRoot, '../tatrman/packages');
const tatrmanSemantics = path.join(tatrmanPackages, 'semantics/dist/index.js');
const { desugarLexicon, foldId } = await import(tatrmanSemantics);

const project = await loadHartlandProject();

// ⚑ RV-P6.5 (2026-08-10, Bora): the md-targeted sugar files — `measures.ttrm` (md.measure.*,
// md.dimension.*) and `examples.ttrm` (md.cubelet.*) — were REMOVED in both locales. md is
// unusable in its current form (the merged Golem's query door cannot render an `md.` ref: a
// measure names no object and no aggregation, and the Veles ModelBundle carries no md layer to
// ask), and md gets its own exercise. `channels.ttrm` stays — its targets are `er.entity.*`.
const LEXICON_FILES = [
  'model/lexicon/en/channels.ttrm',
  'model/lexicon/cs/channels.ttrm',
  'model/lexicon/cs/reasons.ttrm',
];

// All canonical lexicon entries across every lexicon file, tagged with their real
// declared locale (desugarLexicon reads it straight off `model lexicon locale <id>`).
const allEntries = [];
for (const [uri, ast] of project.asts) {
  if (!uri.includes('/model/lexicon/')) continue;
  allEntries.push(...desugarLexicon(ast).entries);
}

function allDefsOfKind(kind) {
  const out = [];
  for (const [uri, ast] of project.asts) {
    for (const def of ast.definitions ?? []) {
      if (def.kind === kind) out.push({ def, uri });
    }
  }
  return out;
}

test('T6.1 — parse-clean: every model/lexicon/{en,cs}/*.ttrm parses with zero errors', () => {
  const offenders = [];
  for (const file of LEXICON_FILES) {
    const errors = project.parseErrorsByFile.get(file);
    assert.ok(errors !== undefined, `${file} not found by the harness`);
    if (errors.length) offenders.push(`${file}: ${JSON.stringify(errors[0])}`);
  }
  assert.deepEqual(offenders, [], `parse errors: ${offenders.join('; ')}`);
});

test('T6.2 — no unresolved `for:` anywhere (zero unexpected diagnostics project-wide)', () => {
  const offenders = [];
  for (const [file, codes] of project.diagnosticsByFile) {
    for (const code of codes) if (!ACCEPTED_RESIDUAL_CODES.has(code)) offenders.push(`${file}: ${code}`);
  }
  assert.deepEqual(offenders, [], `unexpected diagnostics: ${offenders.join('; ')}`);
  // Was >=11 when measures.ttrm + examples.ttrm were here; the three channel families in
  // each locale are what survives the md removal.
  assert.ok(allEntries.length >= 6, `expected >=6 lexicon entries, got ${allEntries.length}`);
});

test('T6.3 — en/cs twin parity: every measure/channel family has BOTH an en and a cs term resolving to the SAME target', () => {
  // md families removed with their files (see the ⚑ above); the twin-parity invariant is
  // what the channel families still assert, and it is the half that never depended on md.
  const FAMILIES = [
    'er.entity.catalog_sales', 'er.entity.web_sales', 'er.entity.store_sales',
  ];
  const terms = allEntries.filter((e) => e.entryKind === 'term');
  const problems = [];
  for (const target of FAMILIES) {
    const en = terms.find((e) => e.locale === 'en' && e.target === target);
    const cs = terms.find((e) => e.locale === 'cs' && e.target === target);
    if (!en) problems.push(`${target}: no en term`);
    if (!cs) problems.push(`${target}: no cs term`);
  }
  assert.deepEqual(problems, [], problems.join('; '));
});

test('T6.4 — diacritic resolution: Czech forms fold to the same id as their ascii-stripped variant', () => {
  const cases = [
    ['tržba', 'trzba'],
    ['vyprodáno', 'vyprodano'],
    ['distribuční centrum', 'distribucni centrum'],
    ['míra vrácení', 'mira vraceni'],
  ];
  for (const [accented, ascii] of cases) {
    assert.equal(foldId(accented), foldId(ascii), `foldId('${accented}') should equal foldId('${ascii}')`);
  }
  // The isolated late-delivery reason, both locales, fold to distinguishable-but-related ids.
  assert.equal(foldId('Nedorazilo včas'), foldId('nedorazilo vcas'));
  assert.notEqual(foldId('Nedorazilo včas'), foldId('Did not get it on time'));
});

test('T6.5 — term->target correctness: no duplicate (locale, target, form) triple', () => {
  const terms = allEntries.filter((e) => e.entryKind === 'term');
  const seen = new Map(); // "locale|target|foldedForm" -> term name
  const duplicates = [];
  for (const e of terms) {
    for (const form of e.forms ?? []) {
      const key = `${e.locale}|${e.target}|${foldId(form)}`;
      if (seen.has(key) && seen.get(key) !== e.name) {
        duplicates.push(`${key} (${seen.get(key)} vs ${e.name})`);
      }
      seen.set(key, e.name);
    }
  }
  assert.deepEqual(duplicates, [], `duplicate forms: ${duplicates.join('; ')}`);
});

test('T6.6 — bilingual valueLabels coverage: every reason (35), category (10), DC (5) member has both en and cs', () => {
  const reasonCode = allDefsOfKind('dimension').find(({ def }) => def.name === 'ReturnReason').def
    .attributes.find((a) => a.name === 'reasonCode');
  const categoryCode = allDefsOfKind('dimension').find(({ def }) => def.name === 'Product').def
    .attributes.find((a) => a.name === 'categoryCode');
  const dcCode = allDefsOfKind('dimension').find(({ def }) => def.name === 'DistributionCentre').def
    .attributes.find((a) => a.name === 'dcCode');

  function checkCoverage(attr, expectedCount, label) {
    const entries = attr.valueLabels?.entries ?? [];
    assert.equal(entries.length, expectedCount, `${label}: expected ${expectedCount} members, got ${entries.length}`);
    const untranslated = entries.filter((e) => !e.label.entries.en || !e.label.entries.cs).map((e) => e.key);
    assert.deepEqual(untranslated, [], `${label}: untranslated members: ${untranslated.join(', ')}`);
  }
  checkCoverage(reasonCode, 35, 'reason');
  checkCoverage(categoryCode, 10, 'category');
  checkCoverage(dcCode, 5, 'DC');

  // The isolated late-delivery reason (sk 3) — S3/S-9's clear-of-the-others signal.
  const late = reasonCode.valueLabels.entries.find((e) => e.key === '3');
  assert.ok(late, 'reason sk=3 not found');
  assert.equal(late.label.entries.en, 'Did not get it on time');
  assert.equal(late.label.entries.cs, 'Nedorazilo včas');
});

test('T6.7 — no orphan term/example: every `for:` resolves through the real resolver', () => {
  const dangling = [];
  for (const { def, uri } of [...allDefsOfKind('term'), ...allDefsOfKind('example'), ...allDefsOfKind('pattern')]) {
    const forRef = def.target; // AST field name for the `for:` keyword
    if (!forRef) { dangling.push(`${uri}: ${def.name} has no for:`); continue; }
    const res = project.resolver.resolveReference(
      { path: forRef.path, parts: forRef.parts },
      { schemaCode: '', namespace: '' },
    );
    if (!res.resolved) dangling.push(`${uri}: ${def.name} -> ${forRef.path}`);
  }
  assert.deepEqual(dangling, [], `dangling for: targets: ${dangling.join('; ')}`);
});
