// AU-hartland P0·S0.2 — the extension's words: the value labels of every enumerated attribute, the documents'
// terms in both locales, and the ⚑AU-H-3 rule (Bora, 2026-10-17: keep „Reklamace“ — and „Objednávka“ — with a
// rule). project/kantheon/features/automation-agents/implementation/hartland/contracts.md §1–§2.
//
// Two sources, on purpose. The value labels are read from the MODEL (they are attribute properties); everything
// a question meets is read from the COMMITTED ARCHIVE (lexicon/tests/archive.mjs): what the matcher serves is
// that file, and `just check-lexicon` proves it is what the sources compile to.
//
// Run: node --test model/lexicon/tests/automation-lexicon.test.mjs   (or `just verify-model`)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadHartlandProject } from '../../tests/project-harness.mjs';
import { isCs, isEn, lexicon } from '../../../lexicon/tests/archive.mjs';

// contracts §1–§2: every enumerated attribute and its values (the physical codes the generator writes).
const ENUMS = {
  order: {
    state: ['placed', 'held', 'released', 'cancelled'],
    held_for: ['Sales', 'AR', 'both'],
  },
  invoice: { status: ['open', 'paid'] },
  return_request: { state: ['received', 'decided', 'closed'] },
  return_request_line: {
    state: ['received', 'rejected', 'settling', 'awaiting_goods', 'goods_received', 'not_returned', 'closed'],
    reason: ['damaged', 'did_not_arrive', 'wrong_size', 'other'],
    requested_resolution: ['refund', 'exchange', 'replacement'],
    way: ['refund_no_return', 'replacement_no_return', 'exchange', 'refund_after_return'],
  },
  return_receipt: { condition: ['ok', 'damaged', 'missing'] },
  credit_note: { status: ['issued', 'paid'] },
  reorder_proposal: { state: ['proposed', 'approved', 'rejected', 'started'] },
  winback_mail: { offer: ['premium', 'standard'] },
};

// The `channel` attributes are enumerated too ('web' · 'marketplace') and carry NO value labels: «web»,
// «tržiště», "web", "marketplace" are the channel words of the three sales facts, and a label would make
// every channel question meet a second reading.
const UNLABELLED_CHANNELS = [['order', 'channel'], ['sales_line', 'channel'], ['price_list', 'channel'], ['return_request', 'channel']];

// Each document's plural, per locale. The en plural is mostly the entity's `labelPlural` (lang `cs|en` in the
// archive); the cs one is declared in model/lexicon/cs/automation.ttrm.
const PLURALS = {
  order: ['orders', 'objednávky'],
  sales_line: ['sales lines', 'řádky objednávky'],
  price_list: ['price lists', 'ceníky'],
  customer_price: ['customer prices', 'individuální ceny'],
  invoice: ['invoices', 'faktury'],
  warehouse_outage: ['outages', 'výpadky skladu'],
  return_request: ['return requests', 'reklamace'],
  return_request_line: ['return request lines', 'řádky reklamace'],
  return_receipt: ['receipts', 'příjemky vratek'],
  credit_note: ['credit notes', 'dobropisy'],
  refund_payment: ['refunds', 'úhrady'],
  replacement_shipment: ['replacement shipments', 'náhradní zásilky'],
  document_flow: ['document flow', 'toky dokladů'],
  reorder_proposal: ['reorder proposals', 'návrhy na doobjednání'],
  winback_mail: ['win-back mails', 'win-back e-maily'],
};
const AU_ENTITIES = Object.keys(PLURALS);

const project = await loadHartlandProject();
const entities = new Map();
for (const [uri, ast] of project.asts) {
  if (uri.startsWith('stock://')) continue;
  for (const def of ast.definitions ?? []) if (def.kind === 'entity') entities.set(def.name, def);
}
const attributeOf = (entity, name) => entities.get(entity)?.attributes?.find((a) => a.name === name);

const ref = (entity) => `er.entity.${entity}`;
const isAu = (targetRef) => AU_ENTITIES.some((e) => targetRef === ref(e) || targetRef.startsWith(`${ref(e)}.`));
const langsOf = (e) => e.lang.split('|');
const fold = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
const rowsOf = (term, lang) => lexicon.entries.filter((e) => e.termNormalized === term && lang(e));

test('control — the archive decodes, and a row every build carries is in it', () => {
  // A probe that cannot find its control is broken, not informative (lexicon-archive-staleness).
  const tržby = rowsOf('tržby', isCs).map((e) => e.targetRef);
  assert.deepEqual(tržby, ['er.entity.sales.ext_sales_price']);
});

test('S0.2 — every enumerated attribute labels every one of its values, in en AND cs, and nothing else', () => {
  const problems = [];
  for (const [entity, attrs] of Object.entries(ENUMS)) {
    for (const [name, codes] of Object.entries(attrs)) {
      const attr = attributeOf(entity, name);
      if (!attr) { problems.push(`${entity}.${name}: no such attribute`); continue; }
      const entries = attr.valueLabels?.entries ?? [];
      const keys = entries.map((e) => e.key);
      if (JSON.stringify([...keys].sort()) !== JSON.stringify([...codes].sort())) problems.push(`${entity}.${name}: labels [${keys}], values [${codes}]`);
      for (const e of entries) {
        for (const lang of ['en', 'cs']) if (!e.label?.entries?.[lang]?.trim()) problems.push(`${entity}.${name}.${e.key}: no ${lang} label`);
      }
    }
  }
  assert.deepEqual(problems, [], problems.join('; '));
});

test('S0.2 — no AU `channel` attribute is labelled (the channel words are the value labels of `sales.channel`)', () => {
  const labelled = UNLABELLED_CHANNELS.filter(([e, a]) => {
    const attr = attributeOf(e, a);
    assert.ok(attr, `${e}.${a} not found`);
    return (attr.valueLabels?.entries ?? []).length > 0;
  });
  assert.deepEqual(labelled, []);
});

test('S0.2 — every value label reached the archive as a MEMBER of its attribute, in both locales', () => {
  const problems = [];
  for (const [entity, attrs] of Object.entries(ENUMS)) {
    for (const name of Object.keys(attrs)) {
      for (const e of attributeOf(entity, name).valueLabels.entries) {
        const target = `${ref(entity)}.${name}.${e.key}`;
        for (const [lang, isLang] of [['en', isEn], ['cs', isCs]]) {
          const term = e.label.entries[lang].toLowerCase();
          const row = rowsOf(term, isLang).find((r) => r.targetRef === target);
          if (!row) problems.push(`«${term}» (${lang}) does not reach ${target}`);
          else if (row.targetClass !== 'MEMBER') problems.push(`«${term}» → ${target} is ${row.targetClass}`);
        }
      }
    }
  }
  assert.deepEqual(problems, [], problems.join('; '));
});

test('S0.2 — every document has its label and a plural, in en AND cs', () => {
  const problems = [];
  for (const entity of AU_ENTITIES) {
    const label = entities.get(entity)?.displayLabel?.entries ?? {};
    const [enPlural, csPlural] = PLURALS[entity];
    for (const [lang, isLang, singular, plural] of [['en', isEn, label.en, enPlural], ['cs', isCs, label.cs, csPlural]]) {
      if (!singular) { problems.push(`${entity}: no ${lang} displayLabel`); continue; }
      for (const term of [singular.toLowerCase(), plural]) {
        if (!rowsOf(term, isLang).some((r) => r.targetRef === ref(entity))) problems.push(`«${term}» (${lang}) does not reach ${ref(entity)}`);
      }
    }
  }
  assert.deepEqual(problems, [], problems.join('; '));
});

// ⚑AU-H-3 rule 1 — the bare word, in every case and number, is the DOCUMENT and nothing else; EXACT, so each
// form meets it in the class the label does (a form reached only through the lemma scores 0.1 lower).
// The nominative is the entity's label (METADATA); the other forms are declared in cs/automation.ttrm.
const RULE_WORDS = {
  return_request: ['reklamace', 'reklamaci', 'reklamací', 'reklamacím', 'reklamacích', 'reklamacemi'],
  order: ['objednávka', 'objednávky', 'objednávce', 'objednávku', 'objednávkou', 'objednávek', 'objednávkám', 'objednávkách', 'objednávkami'],
};

test('⚑AU-H-3 rule 1 — every case form of «reklamace» / «objednávka» is the document (EXACT), and only it', () => {
  const problems = [];
  for (const [entity, forms] of Object.entries(RULE_WORDS)) {
    for (const form of forms) {
      const rows = rowsOf(form, isCs);
      const refs = [...new Set(rows.map((e) => e.targetRef))];
      if (refs.length !== 1 || refs[0] !== ref(entity)) problems.push(`«${form}» → ${refs.join(', ') || 'nothing'}`);
      for (const e of rows) if (e.method !== 'EXACT') problems.push(`«${form}» is ${e.method}`);
    }
  }
  assert.deepEqual(problems, [], problems.join('; '));
});

test('⚑AU-H-3 rule 2 — the returns facts keep their channel-qualified names (longer spans than the bare word)', () => {
  const FACTS = [
    [isCs, 'reklamace z prodejen', 'er.entity.store_returns'],
    [isCs, 'reklamace z webu', 'er.entity.web_returns'],
    [isCs, 'reklamace z tržiště', 'er.entity.catalog_returns'],
    [isEn, 'store returns', 'er.entity.store_returns'],
  ];
  const problems = [];
  for (const [isLang, term, target] of FACTS) {
    const refs = [...new Set(rowsOf(term, isLang).map((e) => e.targetRef))];
    if (refs.length !== 1 || refs[0] !== target) problems.push(`«${term}» → ${refs.join(', ') || 'nothing'}`);
  }
  // The sales facts' names went with their labels at md/hop HP-H (⚑H-7: sources of `sales` only). «objednávky z
  // tržiště» is now the bare «objednávky» — the AU order document, by rule 1, whose `channel` says web or
  // marketplace — beside the marketplace channel word; none of these phrases reaches a channel fact.
  for (const [isLang, term] of [[isCs, 'objednávky z tržiště'], [isCs, 'webové objednávky'], [isEn, 'web orders'], [isEn, 'marketplace orders']]) {
    const refs = rowsOf(term, isLang).map((e) => e.targetRef);
    if (refs.length) problems.push(`«${term}» still reaches ${refs.join(', ')}`);
  }
  assert.deepEqual(problems, [], problems.join('; '));
});

test('⚑AU-H-3 rule 3 — no TOKENS phrase holds a «reklamace» or «objednávka» word (one word would reach it)', () => {
  const words = new Set(Object.values(RULE_WORDS).flat());
  const holding = lexicon.entries
    .filter((e) => e.method === 'TOKENS' && e.termNormalized.split(' ').some((w) => words.has(w)))
    .map((e) => `«${e.termNormalized}» → ${e.targetRef}`);
  assert.deepEqual(holding, []);
});

// The two words the AU labels would have claimed from the estate are left bare: «výpadek / výpadky» (the stockout
// word, act 3.5 «… výpadky zásob?») and «vratka / vratky» (#62, store-family.test.mjs).
test('S0.2 — the bare «výpadek» is no term (act 3.5\'s stockout word stays unclaimed)', () => {
  const claimed = ['výpadek', 'výpadku', 'výpadky', 'výpadků', 'výpadkem', 'výpadcích'].filter((w) => rowsOf(w, isCs).length);
  assert.deepEqual(claimed, []);
});

// The words AU's own attributes share — the same state on the request and its line, and «výměna» both asked for
// and settled — are the one meaning on two attributes; the question's head chooses. Pinned, so a new one is a
// decision and not an accident.
const AU_SHARED = [
  'cs|přijato', 'cs|uzavřeno', 'cs|výměna', 'cs|zamítnuto',
  'en|closed', 'en|exchange', 'en|received', 'en|rejected',
];

test('S0.2 — AU claims no word the pre-AU vocabulary binds (any class, either locale, diacritics folded)', () => {
  const others = new Map();
  for (const e of lexicon.entries) {
    if (isAu(e.targetRef)) continue;
    for (const l of langsOf(e)) others.set(`${l}|${fold(e.termNormalized)}`, e.targetRef);
  }
  const claims = [];
  const shared = new Map();
  for (const e of lexicon.entries.filter((r) => isAu(r.targetRef))) {
    for (const l of langsOf(e)) {
      const key = `${l}|${fold(e.termNormalized)}`;
      if (others.has(key)) claims.push(`«${e.termNormalized}» (${l}) → ${e.targetRef}, already ${others.get(key)}`);
      const k = `${l}|${e.termNormalized}`;
      shared.set(k, new Set([...(shared.get(k) ?? []), e.targetRef]));
    }
  }
  assert.deepEqual(claims, [], claims.join('; '));
  const internal = [...shared].filter(([, refs]) => refs.size > 1).map(([k]) => k).sort();
  assert.deepEqual(internal, AU_SHARED);
});
