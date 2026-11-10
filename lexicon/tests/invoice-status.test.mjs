// «nezaplacená» and «po splatnosti» — the Hartland demo's invoice words (2026-11-09). Both must show as recognised
// terms in the first answer bubble; the first is also the filter status = 'open'.
//
//   1. «nezaplacená» and its cases are declared MEMBER rows on `invoice.status`'s value `open`
//      (lexicon/aliases/invoice-status.lex.yaml) — they reach a question only where the adjective is its own mention
//      (the predicate: «faktury, které jsou nezaplacené»).
//   2. In front of its noun the adjective is folded into the noun's anchor phrase (a member is never an anchor), so
//      «nezaplacené faktury» is ONE span — and it must be a phrase of `cn.OpenInvoice`, in every case a question uses.
//      Live on hartland 2026-11-10 (turn 81e9548d) it was not: G1_UNBOUND, and the turn was refused.
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

test('«nezaplacené faktury» is ONE span, and it is a phrase of the open invoice in every case a question uses', () => {
  const PHRASES = [
    'nezaplacená faktura', 'nezaplacené faktury', 'nezaplacených faktur', 'nezaplacenou fakturu',
    'nezaplacenými fakturami', 'nezaplaceným fakturám', 'nezaplacených fakturách', 'nezaplacenou fakturou',
  ];
  for (const phrase of PHRASES) {
    assert.deepEqual(rowsFor(phrase).map((e) => `${e.targetRef} ${e.targetClass}`), ['cn.OpenInvoice MODEL_OBJECT'], phrase);
  }
  // Bora's demo question (hartland turn 81e9548d) and the customer phrasing reach the phrase whole.
  for (const [question, phrase] of [
    ['Kteří zákazníci mají za minulý měsíc nezaplacené faktury?', 'nezaplacené faktury'],
    ['Zákazníci s nezaplacenými fakturami', 'nezaplacenými fakturami'],
  ]) {
    const hits = wholePhraseHits(question, isCs).map((e) => `${e.termNormalized} → ${e.targetRef}`);
    assert.deepEqual(hits, [`${phrase} → cn.OpenInvoice`], question);
  }
});

test('«neuhrazená» keeps its phrases, in the same cases', () => {
  for (const phrase of ['neuhrazené faktury', 'neuhrazenými fakturami', 'neuhrazených fakturách']) {
    assert.deepEqual(rowsFor(phrase).map((e) => e.targetRef), ['cn.OpenInvoice'], phrase);
  }
});

test('the bare «po splatnosti» is the overdue invoice; the longer phrases keep their own readings', () => {
  const bare = rowsFor('po splatnosti');
  assert.deepEqual(bare.map((e) => e.targetRef), ['cn.OverdueInvoice']);

  const longest = (q) => wholePhraseHits(q, isCs).sort((a, b) => b.termNormalized.length - a.termNormalized.length)[0];
  assert.equal(longest('Které faktury jsou po splatnosti?').targetRef, 'cn.OverdueInvoice');
  assert.equal(longest('Kteří zákazníci po splatnosti mají objednávky?').targetRef, 'cn.DebtorCustomer');
  assert.equal(longest('Ukaž faktury po splatnosti').termNormalized, 'faktury po splatnosti');
});
