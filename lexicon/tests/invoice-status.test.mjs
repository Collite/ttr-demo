// «nezaplacená» and «po splatnosti» — the Hartland demo's invoice words (2026-11-09). Both must show as recognised
// terms in the first answer bubble; the first is also the filter status = 'open'.
//
//   1. «nezaplacená» and its cases are declared MEMBER rows on `invoice.status`'s value `open`
//      (lexicon/aliases/invoice-status.lex.yaml) — the restriction the query door applies.
//   2. No phrase «nezaplacené faktury»: the longest covered span wins, so a phrase on the concept would take the span
//      from the member and the answer would lose the filter (the Golem reads no concept binding).
//   3. The bare «po splatnosti» is a form of `cn.OverdueInvoice` (model/lexicon/cs/cn.ttrm) — a highlight only — and
//      the longer customer phrase still reaches `DebtorCustomer` as a whole.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { lexicon, isCs, wholePhraseHits } from './archive.mjs';

const rowsFor = (term) => lexicon.entries.filter((e) => isCs(e) && e.termNormalized === term);

const UNPAID = ['nezaplacená', 'nezaplacené', 'nezaplacených', 'nezaplacenou', 'nezaplaceným', 'nezaplacenými', 'nezaplaceno'];

test('«nezaplacená» and its cases are declared EXACT members of invoice.status = open', () => {
  for (const form of UNPAID) {
    const rows = rowsFor(form);
    assert.equal(rows.length, 1, `${form}: ${JSON.stringify(rows.map((r) => r.targetRef))}`);
    assert.equal(rows[0].targetRef, 'er.entity.invoice.status.open', form);
    assert.equal(rows[0].targetClass, 'MEMBER', form);
    assert.equal(rows[0].method, 'EXACT', form);
    assert.equal(rows[0].sourceTag, 'DECLARED', form);
  }
});

test('no phrase takes «nezaplacené faktury» from the member', () => {
  const hits = wholePhraseHits('Které nezaplacené faktury má zákazník?', isCs);
  assert.deepEqual(hits.map((e) => `${e.termNormalized} → ${e.targetRef}`), []);
});

test('the bare «po splatnosti» is the overdue invoice; the longer phrases keep their own readings', () => {
  const bare = rowsFor('po splatnosti');
  assert.deepEqual(bare.map((e) => e.targetRef), ['cn.OverdueInvoice']);

  const longest = (q) => wholePhraseHits(q, isCs).sort((a, b) => b.termNormalized.length - a.termNormalized.length)[0];
  assert.equal(longest('Které faktury jsou po splatnosti?').targetRef, 'cn.OverdueInvoice');
  assert.equal(longest('Kteří zákazníci po splatnosti mají objednávky?').targetRef, 'cn.DebtorCustomer');
  assert.equal(longest('Ukaž faktury po splatnosti').termNormalized, 'faktury po splatnosti');
});
