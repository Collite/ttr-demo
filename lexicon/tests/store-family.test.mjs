// ttr-demo#62 — the store family („prodejna“ / store), checked in the COMMITTED ARCHIVE; and since md/hop HP-H
// (2026-10-24, ⚑H-7) the channel words as a whole.
//
// Bora's ruling (2026-10-12): a bare store word reads by its ROLE, so the lexicon must give it
// BOTH readings and let the resolver's slot decide:
//   - GROUPING („podle prodejen“, "by store") → the store dimension, no ask;
//   - FILTER → ask, offering the dimension and the store channel.
// Plus „vratka / vratky“ → the returns measure.
//
// HP-H moved the store CHANNEL from the store fact (`store_sales` and its measure) to a value of the all-channel
// `sales`: `er.entity.sales.channel.store`, declared by `sales.channel`'s value labels, which the resolver binds as
// `er.entity.sales.channel#store` and the door restricts by. The same for the web and the marketplace. The three
// channel facts are sources of `sales` only, and no word reaches them; the channel-qualified revenue phrases
// («tržby z prodejen», "marketplace revenue") went with them — the revenue word and the channel word now bind
// separately, so «Tržby z prodejen» is a revenue restricted by the bare store word, and asks.
//
// Why the archive and not the sources: what the matcher serves IS this file, and
// `just check-lexicon` (CI) proves it is what the sources compile to.
//   - «Tržby podle prodejen v roce 2025» (measured 2026-10-14, resolver 0.11.21): `prodejen` bound only a TOKENS
//     hit on «obrat z prodejen»; the bare word's EXACT readings were reached only through the lemma, out of the tie
//     band. Declared as written, every case form meets both readings in the EXACT class.
//   - «Tržby z prodejen za 2025»: the whole phrase once bound the ENTITY `store_sales` through its label (METADATA
//     EXACT 1.168), which no declared phrase can beat — a channel fact carries no label now.
//   - «Vratky z prodejen»: «Vratky» bound nothing (G1), and the question ended in a parameter ask.
//
// Run: node --test lexicon/tests/store-family.test.mjs   (or `just verify-model`)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { isCs, isEn, lexicon, repoRoot } from './archive.mjs';

const rowsOf = (term, lang) => lexicon.entries.filter((e) => e.termNormalized === term && lang(e));

const STORE = 'er.entity.store';
const CHANNEL = (value) => `er.entity.sales.channel.${value}`;

test('control — the archive decodes, and a row every build carries is in it', () => {
  // A probe that cannot find its control is broken, not informative (lexicon-archive-staleness).
  assert.ok(lexicon.entries.length > 400, `only ${lexicon.entries.length} entries`);
  const tržby = rowsOf('tržby', isCs).map((e) => e.targetRef);
  assert.deepEqual(tržby, ['er.entity.sales.ext_sales_price']);
});

// Every case of „prodejna“, singular and plural (the vocative left out). The corpus asks
// «prodejen» (2.4, E1, E3, E6) and «prodejny» (E4, E5); the rest is the same word.
const PRODEJNA_FORMS = ['prodejna', 'prodejny', 'prodejně', 'prodejnu', 'prodejnou', 'prodejen', 'prodejnám', 'prodejnách', 'prodejnami'];
const STORE_READINGS = [STORE, CHANNEL('store')];

test('#62 — every case form of «prodejna» is an EXACT declared term of BOTH the store dimension and the store channel', () => {
  const problems = [];
  for (const form of PRODEJNA_FORMS) {
    const rows = rowsOf(form, isCs);
    for (const ref of STORE_READINGS) {
      const row = rows.find((e) => e.targetRef === ref && e.sourceTag === 'DECLARED');
      if (!row) problems.push(`«${form}» does not reach ${ref} (declared)`);
      else if (row.method !== 'EXACT') problems.push(`«${form}» → ${ref} is ${row.method}, not EXACT`);
    }
    const stray = rows.filter((e) => !STORE_READINGS.includes(e.targetRef)).map((e) => e.targetRef);
    if (stray.length) problems.push(`«${form}» also reaches ${stray.join(', ')}`);
  }
  assert.deepEqual(problems, [], problems.join('; '));
});

test('#62 — en «store» and «stores» keep both readings (the dimension label and the channel term)', () => {
  // Live before HP-H, "Revenue by stores in 2025" bound the dimension (GROUPING) and the bare "Stores" asked (G2).
  // "store revenue" was a phrase on the store fact's measure; the singular now carries the channel reading itself,
  // as the cs word does. A guard, so neither reading goes missing.
  for (const term of ['store', 'stores']) {
    const refs = new Set(rowsOf(term, isEn).map((e) => e.targetRef));
    for (const ref of STORE_READINGS) assert.ok(refs.has(ref), `"${term}" does not reach ${ref}`);
  }
});

// md/hop HP-H — a channel word is a term of its OWN, on its channel's value. Until HP-H an inflected channel word
// («webu», «tržišti», «prodejen») reached its channel's revenue only as ONE word of a TOKENS phrase («tržby z webu»),
// which worked while every TOKENS phrase holding it targeted one ref. Those phrases are gone; the forms are declared.
const CHANNEL_WORDS = {
  tržiště: 'marketplace', tržišti: 'marketplace', tržištěm: 'marketplace',
  web: 'web', webu: 'web', webem: 'web', 'e-shopu': 'web',
};

test('HP-H — every channel word is an EXACT declared term of its channel, and no TOKENS phrase holds it', () => {
  const problems = [];
  for (const [word, value] of Object.entries(CHANNEL_WORDS)) {
    const refs = [...new Set(rowsOf(word, isCs).map((e) => e.targetRef))];
    if (refs.length !== 1 || refs[0] !== CHANNEL(value)) problems.push(`«${word}» → ${refs.join(', ') || 'nothing'}`);
    for (const e of rowsOf(word, isCs)) if (e.method !== 'EXACT') problems.push(`«${word}» is ${e.method}, not EXACT`);
    const holding = lexicon.entries.filter((e) => e.method === 'TOKENS' && isCs(e) && ` ${e.termNormalized} `.includes(` ${word} `));
    if (holding.length) problems.push(`«${word}» is a word of the TOKENS phrase(s) ${holding.map((e) => `«${e.termNormalized}»`).join(', ')}`);
  }
  for (const [lang, isLang, word, value] of [['en', isEn, 'marketplace', 'marketplace'], ['en', isEn, 'web', 'web'], ['en', isEn, 'online', 'web']]) {
    if (!rowsOf(word, isLang).some((e) => e.targetRef === CHANNEL(value))) problems.push(`${lang} "${word}" does not reach ${CHANNEL(value)}`);
  }
  // The value labels themselves are METADATA members of the same values.
  for (const [label, value] of [['tržiště', 'marketplace'], ['kanál prodejen', 'store'], ['store channel', 'store'], ['marketplace', 'marketplace']]) {
    if (!lexicon.entries.some((e) => e.termNormalized === label && e.targetRef === CHANNEL(value) && e.targetClass === 'MEMBER')) {
      problems.push(`«${label}» is no MEMBER row of ${CHANNEL(value)}`);
    }
  }
  assert.deepEqual(problems, [], problems.join('; '));
});

test('⚑H-7 — no word reaches a channel fact, or the folded channel_sales; the channel-qualified revenue phrases are gone', () => {
  const FACTS = /^er\.entity\.(store_sales|web_sales|catalog_sales|channel_sales)(\.|$)/;
  const stale = lexicon.entries.filter((e) => FACTS.test(e.targetRef)).map((e) => `«${e.termNormalized}» → ${e.targetRef}`);
  assert.deepEqual(stale, [], stale.join('; '));
  const PHRASES = ['tržby z tržiště', 'tržba z tržiště', 'obrat z tržiště', 'tržby z webu', 'tržby z prodejen', 'tržba z prodejen', 'obrat z prodejen'];
  const left = PHRASES.filter((t) => rowsOf(t, isCs).length).concat(['marketplace revenue', 'store revenue', 'web revenue'].filter((t) => rowsOf(t, isEn).length));
  assert.deepEqual(left, [], `channel-qualified revenue phrases still declared: ${left.join(', ')}`);
});

// „vratka / vratky“ — the returns MEASURE of each channel. Only the store phrase is attested («Vratky
// z prodejen», MH E6); the web and marketplace twins keep the three channels symmetric. They match as
// WHOLE phrases (the file's default profile, not TOKENS), for the reason the test above states: a
// TOKENS returns phrase is reached by its channel word, and by «vratky» alone. «vratek» (genitive
// plural) is declared as written: MorphoDiTa lemmatises it to «vratek», not «vratka».
const RETURNS = {
  prodejen: 'er.entity.store_returns.return_amt',
  webu: 'er.entity.web_returns.return_amt',
  tržiště: 'er.entity.catalog_returns.return_amt',
};

test('#62 — «vratka / vratky / vratek z <kanálu>» is that channel\'s returns measure, as a whole phrase; the bare word is not a term', () => {
  const problems = [];
  for (const [channel, ref] of Object.entries(RETURNS)) {
    for (const head of ['vratky', 'vratka', 'vratek']) {
      const term = `${head} z ${channel}`;
      const rows = rowsOf(term, isCs);
      const refs = [...new Set(rows.map((e) => e.targetRef))];
      if (refs.length !== 1 || refs[0] !== ref) problems.push(`«${term}» → ${refs.join(', ') || 'nothing'}`);
      for (const e of rows) if (e.method === 'TOKENS') problems.push(`«${term}» is TOKENS: «${channel}» and «${head}» alone would reach it`);
    }
    if (lexicon.targets[ref]?.objectKind !== 'measure') problems.push(`${ref} is ${lexicon.targets[ref]?.objectKind ?? 'not a target'}, not a measure`);
  }
  for (const bare of ['vratka', 'vratky', 'vratek']) {
    const refs = rowsOf(bare, isCs).map((e) => e.targetRef);
    if (refs.length) problems.push(`bare «${bare}» → ${refs.join(', ')} (three channels; it must not pick one)`);
  }
  assert.deepEqual(problems, [], problems.join('; '));
});

// The saved queries' own Czech wording — description, patterns, examples — names the store channel as «tržby z
// prodejen», never as a bare «prodejen» restricting revenue («tržby prodejen»). ⚑ md/hop HP-H: «tržby z prodejen» was a
// DECLARED phrase on the store fact's measure and answered; it is now the revenue word beside the store word, which in
// a restriction asks (the ruling below). The example still reads best this way; whether its chip asks is measured in the
// HP-H T6 walk, and the wording moves then if it does.
// Under the ruling that bare word is a FILTER, and a FILTER asks between the store dimension and the store
// channel; a query's example is what golem offers as a follow-up chip and what its corpus case asks
// (`p-store-sales-by-month`), so an example that asks is a query nobody reaches. Line-oriented over the
// strings of model/queries/q_hartland.ttrm, folded (diacritics off, lower case), as the patterns are written.
const queriesFile = path.join(repoRoot, 'model', 'queries', 'q_hartland.ttrm');
const fold = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
const BARE_STORE_AFTER_REVENUE = /\b(trzb[a-z]*|obrat[a-z]*) (prodejen|prodejny|prodejnam|prodejnach|prodejnami|prodejne|prodejnu|prodejnou|prodejna)\b/;

test('#62 — no saved query words the store channel as a bare «prodejen» restricting revenue; store_sales_by_month uses «tržby z prodejen»', () => {
  const text = readFileSync(queriesFile, 'utf-8');
  const offenders = [];
  for (const [i, line] of text.split('\n').entries()) {
    for (const m of line.matchAll(/"([^"]*)"/g)) {
      if (BARE_STORE_AFTER_REVENUE.test(fold(m[1]))) offenders.push(`q_hartland.ttrm:${i + 1}: «${m[1]}»`);
    }
  }
  assert.deepEqual(offenders, [], offenders.join('; '));

  const block = text.slice(text.indexOf('def query store_sales_by_month'), text.indexOf('def query customer_running_total'));
  const examples = [...block.slice(block.indexOf('examples:')).matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  const cs = examples.filter((e) => /[ěščřžýáíéůú]/i.test(e));
  assert.ok(cs.length > 0, `store_sales_by_month has no Czech example: ${examples.join(' | ')}`);
  for (const e of cs) assert.ok(fold(e).includes('trzby z prodejen'), `the Czech example «${e}» does not name the store channel by «tržby z prodejen»`);
});
