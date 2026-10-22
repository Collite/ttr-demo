// BI-4 (contracts C-22) — the stock-out-week phrases, checked in the COMMITTED ARCHIVE.
//
// The measure `er.entity.dc_stockout_month.stockout_weeks` (the entity stacked on the logical query
// `er.query.stockouts_monthly_dc`, model/er/stockouts.ttrm) is reached by declared phrases that name the
// MEASURE — stock-out weeks — never by the bare stock-out words. «Kolik týdnů v roce 2025 mělo Brno DC výpadky
// zásob?» (act 3.5) is the saved query `warehouse_stockout_week_count`'s, through the stock anchor
// («zásob» → inventory) and its own patterns; a row for «výpadky zásob» would be the longer span and take the
// question from it. The month grouping is not in the phrases either: «po měsících» / "monthly" are the calendar's
// (er.entity.date_dim.month), and a phrase that swallowed them would answer one total instead of a series.
//
// Run: node --test lexicon/tests/stockouts.test.mjs   (or `just verify-model`)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isCs, isEn, lexicon, wholePhraseHits } from './archive.mjs';

const MEASURE = 'er.entity.dc_stockout_month.stockout_weeks';
const ENTITY = 'er.entity.dc_stockout_month';
const OURS = (e) => e.targetRef === MEASURE || e.targetRef === ENTITY;

const PHRASES = {
  en: ['stockout weeks'],
  cs: ['týdny s výpadkem zásob', 'týdnů s výpadkem zásob', 'týdny s výpadky zásob', 'týdnů s výpadky zásob'],
};

// Act 3.5 and the saved query's own examples (model/queries/q_hartland.ttrm, run-set/routing a3-5).
const ACT_3_5 = [
  ['Kolik týdnů v roce 2025 mělo Brno DC výpadky zásob?', isCs],
  ['kolik tydnu v roce 2025 melo Brno DC vypadky zasob', isCs],
  ['Kolik týdnů v roce 2025 byly v Brně výpadky zásob?', isCs],
  ['How many weeks in 2025 did Memphis DC have stockouts?', isEn],
];

test('control — the bare stock-out words still reach inventory, and nothing declares «výpadky zásob»', () => {
  const refs = (term, lang) => lexicon.entries.filter((e) => e.termNormalized === term && lang(e)).map((e) => e.targetRef);
  assert.deepEqual(refs('stockout', isEn), ['er.entity.inventory.quantity_on_hand']);
  assert.deepEqual(refs('zásoby', isCs), ['er.entity.inventory.quantity_on_hand']);
  assert.deepEqual(refs('výpadky zásob', isCs), [], 'a «výpadky zásob» row would take act 3.5 from the saved query');
});

test('BI-4 — every stock-out-week phrase is a whole-phrase DECLARED row of the measure, with the folded rule', () => {
  const problems = [];
  for (const [lang, terms] of Object.entries(PHRASES)) {
    for (const term of terms) {
      const rows = lexicon.entries.filter((e) => e.termNormalized === term && (lang === 'cs' ? isCs(e) : isEn(e)));
      const refs = [...new Set(rows.map((e) => e.targetRef))];
      if (refs.length !== 1 || refs[0] !== MEASURE) { problems.push(`«${term}» → ${refs.join(', ') || 'nothing'}`); continue; }
      for (const e of rows) {
        if (e.sourceTag !== 'DECLARED') problems.push(`«${term}» is ${e.sourceTag}`);
        if (e.method === 'TOKENS') problems.push(`«${term}» is TOKENS: its fragments («týdnů», «zásob») would reach it`);
        if (!(e.matchProfile?.rules ?? []).some((r) => r.norm === 'folded' && r.exact != null)) problems.push(`«${term}» has no folded rule`);
      }
    }
  }
  assert.deepEqual(problems, [], problems.join('; '));
  assert.equal(lexicon.targets[MEASURE]?.objectKind, 'measure');
});

test('BI-4 — act 3.5 meets nothing of the new entity: no phrase, no label', () => {
  const problems = [];
  for (const [q, lang] of ACT_3_5) {
    const hits = wholePhraseHits(q, lang).filter(OURS);
    if (hits.length) problems.push(`«${q}» reaches ${hits.map((e) => `«${e.termNormalized}» → ${e.targetRef}`).join(', ')}`);
  }
  assert.deepEqual(problems, [], problems.join('; '));
  const tokens = lexicon.entries.filter((e) => OURS(e) && e.method === 'TOKENS').map((e) => `«${e.termNormalized}»`);
  assert.deepEqual(tokens, [], `fragments would reach the entity: ${tokens.join(', ')}`);
});

test('BI-4 — monthly stock-out questions meet the measure, and keep the calendar\'s month words', () => {
  const QUESTIONS = [
    ['Kolik týdnů s výpadkem zásob měla jednotlivá DC po měsících v roce 2025?', isCs],
    ['tydny s vypadky zasob po mesicich podle DC', isCs],
    ['Stockout weeks by month for each DC in 2025', isEn],
  ];
  const problems = [];
  for (const [q, lang] of QUESTIONS) {
    const hits = wholePhraseHits(q, lang);
    if (!hits.some((e) => e.targetRef === MEASURE)) problems.push(`«${q}» meets no stock-out-week phrase`);
    const swallowed = hits.filter((e) => e.targetRef === MEASURE && /měsíc|mesic|month/.test(e.termNormalized));
    if (swallowed.length) problems.push(`«${q}»: the phrase swallows the month (${swallowed.map((e) => e.termNormalized).join(', ')})`);
  }
  assert.deepEqual(problems, [], problems.join('; '));
});

test('BI-4 — the entity\'s labels are in the archive, and name the object, not the stock-out words', () => {
  const labels = lexicon.entries.filter((e) => e.targetRef === ENTITY && e.sourceTag === 'METADATA').map((e) => e.termNormalized);
  assert.ok(labels.length >= 2, `the entity's labels did not reach the archive: ${labels.join(', ')}`);
  for (const l of labels) assert.doesNotMatch(l, /^(výpadky zásob|stockouts?|stockout weeks)$/, `the label «${l}» is a stock-out phrase`);
});
