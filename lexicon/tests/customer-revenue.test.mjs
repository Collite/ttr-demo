// LQ (logical queries) — the customer-revenue phrases, checked in the COMMITTED ARCHIVE.
//
// The measure `er.entity.customer_revenue.revenue` (the entity stacked on the logical query
// `er.query.revenue_per_customer`) is reached by declared phrases only. The first build declared them
// `method: TOKENS`, and the review of ttr-demo#78 found two ways that answers the wrong question:
//   - a TOKENS row carries its own profile (canonical tokens only), so it drops the file's `folded` rule:
//     «prumerne trzby zakaznika …», typed without diacritics, missed the phrase and bound the bare
//     `tržby` (`sales`; `channel_sales` then) — the average SALES LINE, not the average customer;
//   - a TOKENS row is reached by its fragments, and two of the phrases are built on `per` / `na`, which
//     the stdlib's avg skill (ttr-core#178) keeps out of triggers: "revenue per month", „tržby na tržišti“.
// So the rows are whole phrases under the file's default profile, every Czech case form a question takes
// is spelled out, and this suite holds both.
//
// The phrase check is `wholePhraseHits` (archive.mjs), a deliberately small model of the matcher.
//
// Run: node --test lexicon/tests/customer-revenue.test.mjs   (or `just verify-model`)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isCs, isEn, lexicon, wholePhraseHits } from './archive.mjs';

const MEASURE = 'er.entity.customer_revenue.revenue';
const ENTITY = 'er.entity.customer_revenue';

const PHRASES = {
  en: ['customer revenue', 'customer revenues', 'revenue per customer'],
  cs: ['tržby zákazníka', 'tržba zákazníka', 'tržeb zákazníka', 'tržby zákazníků', 'tržeb zákazníků', 'tržby na zákazníka'],
};

test('control — the bare revenue words still reach the all-channel fact `sales`, and only it', () => {
  // A probe that cannot find its control is broken, not informative (lexicon-archive-staleness).
  for (const [term, lang] of [['tržby', isCs], ['revenue', isEn]]) {
    const refs = lexicon.entries.filter((e) => e.termNormalized === term && lang(e)).map((e) => e.targetRef);
    assert.deepEqual(refs, ['er.entity.sales.ext_sales_price'], `«${term}» → ${refs.join(', ')}`);
  }
});

test('LQ — every customer-revenue phrase is a whole-phrase DECLARED row of the measure, with the folded rule', () => {
  const problems = [];
  for (const [lang, terms] of Object.entries(PHRASES)) {
    for (const term of terms) {
      const rows = lexicon.entries.filter((e) => e.termNormalized === term && (lang === 'cs' ? isCs(e) : isEn(e)));
      const refs = [...new Set(rows.map((e) => e.targetRef))];
      if (refs.length !== 1 || refs[0] !== MEASURE) { problems.push(`«${term}» → ${refs.join(', ') || 'nothing'}`); continue; }
      for (const e of rows) {
        if (e.sourceTag !== 'DECLARED') problems.push(`«${term}» is ${e.sourceTag}`);
        if (e.method === 'TOKENS') problems.push(`«${term}» is TOKENS: its fragments reach it, and it has no folded rule`);
        if (!(e.matchProfile?.rules ?? []).some((r) => r.norm === 'folded' && r.exact != null)) problems.push(`«${term}» has no folded rule`);
      }
    }
  }
  assert.deepEqual(problems, [], problems.join('; '));
  assert.equal(lexicon.targets[MEASURE]?.objectKind, 'measure');
});

test('LQ — nothing reaches the customer-revenue measure or entity through a TOKENS row', () => {
  const tokens = lexicon.entries
    .filter((e) => (e.targetRef === MEASURE || e.targetRef === ENTITY) && e.method === 'TOKENS')
    .map((e) => `«${e.termNormalized}» → ${e.targetRef}`);
  assert.deepEqual(tokens, [], `fragments of these phrases (per, na, zákazníka, customer …) would reach them: ${tokens.join('; ')}`);
});

test('LQ — the acceptance question, with and without diacritics and in its other cases, meets a customer-revenue phrase', () => {
  const QUESTIONS = [
    ['Průměrné tržby zákazníka podle kupního potenciálu domácnosti', isCs],
    ['prumerne trzby zakaznika podle kupniho potencialu domacnosti', isCs],
    ['Průměrné tržby zákazníků podle kupního potenciálu domácnosti', isCs],
    ['prumer trzeb zakazniku podle kupniho potencialu', isCs],
    ['Jaké jsou tržby na zákazníka podle kupního potenciálu?', isCs],
    ['Average customer revenue by household buying potential', isEn],
    ['average revenue per customer by buying potential', isEn],
  ];
  const problems = [];
  for (const [q, lang] of QUESTIONS) {
    const refs = [...new Set(wholePhraseHits(q, lang).map((e) => e.targetRef))];
    if (!refs.includes(MEASURE)) problems.push(`«${q}» meets no customer-revenue phrase (whole-phrase hits: ${refs.join(', ') || 'none'})`);
  }
  assert.deepEqual(problems, [], problems.join('; '));
});

test('LQ — "per" / «na» questions about something else do not reach the customer-revenue measure', () => {
  // The stdlib avg skill's own examples of `per` / `na` naming a grouping or a channel (ttr-core#178).
  const QUESTIONS = [
    ['revenue per month in 2025', isEn],
    ['revenue per store', isEn],
    ['Jaké byly tržby na tržišti v roce 2025?', isCs],
    ['podíl na tržbách podle kanálu', isCs],
  ];
  const problems = [];
  for (const [q, lang] of QUESTIONS) {
    const hits = wholePhraseHits(q, lang).filter((e) => e.targetRef === MEASURE);
    if (hits.length) problems.push(`«${q}» reaches the measure through ${hits.map((e) => `«${e.termNormalized}»`).join(', ')}`);
  }
  assert.deepEqual(problems, [], problems.join('; '));
});
