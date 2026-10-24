// A city is asked inflected — «zákazníci z Prahy», «stav zásob v Brně», «v Českých Budějovicích» — and the database stores
// it in the base form. On 2026-10-21 the composer wrote `warehouse.city = 'Brně'` (0 rows): no vocabulary held the
// city, so the word reached it unbound and was copied as written. Two guards:
//
//   1. the customer's city is a MEMBER vocabulary, searched by TYPOS(1) — a method lex-matcher compares on its lemma
//      axis (nlp lemmatises the query and the members alike; EXACT would compare the written form), so the resolver
//      binds the stored name and the filter reads city = 'Praha'. Within one hop of `customer` (and the channel facts),
//      never of `sales`: the bare-city headline beat keeps its distribution centre.
//      The store's and the DC's cities stay unsearchable: each is named after its city („Brno“, „Brno DC“) and
//      store_name / warehouse_name already carry the word — a second attribute on the same entity would only split it.
//   2. the composer, for a value nothing grounded, writes the base form (prompts/cs/intent.yaml).

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { lexicon, repoRoot } from './archive.mjs';

const targets = lexicon.targets;

test('the customer\'s city is a member vocabulary, searched on the lemma axis (TYPOS, not EXACT)', () => {
  assert.equal(targets['er.entity.customer_address.city']?.memberVocabulary, true);
  const parties = readFileSync(path.join(repoRoot, 'model/er/parties.ttrm'), 'utf-8');
  const address = parties.slice(parties.indexOf('def entity customer_address'), parties.indexOf('def entity customer_demographics'));
  assert.match(address, /def attribute city\s+\{[^\n]*search \{ searchable method: TYPOS\(\d\) \}/);
});

test('the customer\'s address is in reach of a customer, never of `sales` (the bare-city beat keeps its DC)', () => {
  const from = (targets['er.entity.customer_address']?.reachedFrom ?? []).map((r) => r.factRef);
  assert.ok(from.includes('er.entity.customer'), `reached from: ${from}`);
  assert.ok(!from.includes('er.entity.sales'), `reached from: ${from}`);
});

test('the store\'s and the DC\'s cities stay unsearchable — their names already carry the city word', () => {
  for (const ref of ['er.entity.store.city', 'er.entity.warehouse.city']) {
    assert.notEqual(targets[ref]?.memberVocabulary, true, `${ref} is not a member vocabulary`);
  }
  for (const ref of ['er.entity.store.store_name', 'er.entity.warehouse.warehouse_name']) {
    assert.equal(targets[ref]?.memberVocabulary, true, `${ref} is a member vocabulary`);
  }
});

test('the composer writes a value nothing grounded in its base form, never as the question inflects it', () => {
  const prompt = readFileSync(path.join(repoRoot, 'agents/golem/shems/golem-hartland/prompts/cs/intent.yaml'), 'utf-8');
  assert.match(prompt, /«v Brně» → 'Brno'/);
  assert.match(prompt, /nikdy ne tvar, v jakém stojí v otázce/);
});
