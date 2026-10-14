// ttr-demo#62 — the store family („prodejna“ / store), checked in the COMMITTED ARCHIVE.
//
// Bora's ruling (2026-10-12): a bare store word reads by its ROLE, so the lexicon must give it
// BOTH readings and let the resolver's slot decide:
//   - GROUPING („podle prodejen“, "by store") → the store dimension, no ask;
//   - FILTER → ask, offering the dimension and the store channel;
//   - the declared phrases („tržba / tržby z prodejen“, "store revenue") → the store-channel
//     measure, answered directly.
// Plus „vratka / vratky“ → the returns measure.
//
// Why the archive and not the sources: what the matcher serves IS this file, and
// `just check-lexicon` (CI) proves it is what the sources compile to. Each assertion below is a
// fact the resolver reads at runtime, measured live on 2026-10-14 (resolver 0.11.21):
//   - «Tržby podle prodejen v roce 2025»: `prodejen` bound ONLY `store_sales.ext_sales_price`,
//     through a TOKENS hit on the declared phrase «obrat z prodejen» (DECLARED_ALIAS, 1.003).
//     The bare word's two EXACT readings («prodejna» → store, → store_sales) were reached only
//     through the lemma (`LemmaLookup`, score − 0.1), out of the tie band, so the slot rule that
//     prefers the dimension in a GROUPING never saw them. Declared as written, every case form
//     meets both readings in the EXACT class, which outranks the TOKENS hit.
//   - «Tržby z prodejen za 2025»: the whole phrase bound the ENTITY `store_sales` (METADATA
//     EXACT 1.168, its `displayLabel.cs` «Tržby z prodejen»), not the measure, so the door could
//     not answer and the composer ran a 3-channel monthly query. A declared phrase (profiled,
//     1.000 or DECLARED_ALIAS) can never beat that label, so the label had to stop saying it.
//   - «Vratky z prodejen»: «Vratky» bound nothing (G1), and the question ended in a parameter ask.
//
// Run: node --test lexicon/tests/store-family.test.mjs   (or `just verify-model`)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { zstdDecompressSync } from 'node:zlib';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const archivePath = path.join(repoRoot, 'generated', 'lexicon.tar.zst');

/** The members of a plain ustar archive (what the lexicon packer writes), by name. */
function untar(buf) {
  const files = new Map();
  for (let off = 0; off + 512 <= buf.length; ) {
    const header = buf.subarray(off, off + 512);
    if (header.every((b) => b === 0)) break;
    const field = (start, len) => header.subarray(start, start + len).toString('utf-8').replace(/\0.*$/s, '');
    const name = [field(345, 155), field(0, 100)].filter(Boolean).join('/');
    const size = parseInt(field(124, 12).trim() || '0', 8);
    const type = field(156, 1);
    off += 512;
    if (type === '0' || type === '') files.set(name, buf.subarray(off, off + size));
    off += Math.ceil(size / 512) * 512;
  }
  return files;
}

const lexicon = JSON.parse(untar(zstdDecompressSync(readFileSync(archivePath))).get('docs/lexicon.json').toString('utf-8'));
const isCs = (e) => e.lang.split('|').includes('cs');
const isEn = (e) => e.lang.split('|').includes('en');
const rowsOf = (term, lang) => lexicon.entries.filter((e) => e.termNormalized === term && lang(e));

test('control — the archive decodes, and a row every build carries is in it', () => {
  // A probe that cannot find its control is broken, not informative (lexicon-archive-staleness).
  assert.ok(lexicon.entries.length > 400, `only ${lexicon.entries.length} entries`);
  const tržby = rowsOf('tržby', isCs).map((e) => e.targetRef);
  assert.deepEqual(tržby, ['er.entity.channel_sales.ext_sales_price']);
});

// Every case of „prodejna“, singular and plural (the vocative left out). The corpus asks
// «prodejen» (2.4, E1, E3, E6) and «prodejny» (E4, E5); the rest is the same word.
//
// The two readings the ruling names: the store DIMENSION, and the store channel as "store revenue" —
// its MEASURE, which is what the bare word bound live in every role (through a TOKENS hit). Keeping the
// measure as the second reading leaves every non-GROUPING, non-COUNT position as it reads live today;
// only the slots the ruling decides move. The citation form also keeps master's channel ENTITY term
// (`store_channel_cs`), which the resolver folds into its own measure (declared containment).
const PRODEJNA_FORMS = ['prodejna', 'prodejny', 'prodejně', 'prodejnu', 'prodejnou', 'prodejen', 'prodejnám', 'prodejnách', 'prodejnami'];
const STORE_READINGS = ['er.entity.store', 'er.entity.store_sales.ext_sales_price'];

test('#62 — every case form of «prodejna» is an EXACT declared term of BOTH the store dimension and the store-channel measure', () => {
  const problems = [];
  for (const form of PRODEJNA_FORMS) {
    const rows = rowsOf(form, isCs);
    for (const ref of STORE_READINGS) {
      const row = rows.find((e) => e.targetRef === ref && e.sourceTag === 'DECLARED');
      if (!row) problems.push(`«${form}» does not reach ${ref} (declared)`);
      else if (row.method !== 'EXACT') problems.push(`«${form}» → ${ref} is ${row.method}, not EXACT`);
    }
    const allowed = form === 'prodejna' ? [...STORE_READINGS, 'er.entity.store_sales'] : STORE_READINGS;
    const stray = rows.filter((e) => !allowed.includes(e.targetRef)).map((e) => e.targetRef);
    if (stray.length) problems.push(`«${form}» also reaches ${stray.join(', ')}`);
  }
  assert.deepEqual(problems, [], problems.join('; '));
});

test('#62 — en «stores» keeps both readings (the dimension label and the channel term)', () => {
  // The en half already had the shape the cs half gains: live, "Revenue by stores in 2025" binds the
  // dimension (GROUPING) and the bare "Stores" asks (G2). A guard, so neither reading goes missing.
  const refs = new Set(rowsOf('stores', isEn).map((e) => e.targetRef));
  for (const ref of ['er.entity.store', 'er.entity.store_sales']) assert.ok(refs.has(ref), `"stores" does not reach ${ref}`);
});

test('#62 — the plural «tržby z prodejen» is the store-channel MEASURE, and no label claims it for the entity', () => {
  for (const term of ['tržba z prodejen', 'tržby z prodejen', 'tržeb z prodejen']) {
    const refs = [...new Set(rowsOf(term, isCs).map((e) => e.targetRef))];
    assert.deepEqual(refs, ['er.entity.store_sales.ext_sales_price'], `«${term}» → ${refs.join(', ') || 'nothing'}`);
  }
  // The measure's kind is what wakes FrameRoles R2 (MEASURE), and so the door's SUM.
  assert.equal(lexicon.targets['er.entity.store_sales.ext_sales_price']?.objectKind, 'measure');
});

// A TOKENS term is reached by ONE of its words, not only as the whole phrase. That is how an inflected
// channel word binds live: «webu», «tržišti», «prodejen» are not terms, and each reaches its channel's
// revenue through the TOKENS phrases it appears in («tržby z webu», «obrat z tržiště», …). It works
// only while every TOKENS phrase holding the word targets ONE ref; a second target makes the word
// non-discriminative (auto_bindable=false), and it binds nothing (G1). The first build of #62 broke
// exactly this: its TOKENS returns phrases («vratky z webu») tied «webu» and «tržišti» with the returns
// measures, and «A na webu?», «… na tržišti …» went G1.
const CHANNEL_WORDS = {
  webu: 'er.entity.web_sales.ext_sales_price',
  tržiště: 'er.entity.catalog_sales.ext_sales_price',
  prodejen: 'er.entity.store_sales.ext_sales_price',
};

test('#62 — a channel word reaches ONE target through the TOKENS phrases holding it («webu», «z webu», «tržiště», «z tržiště», …)', () => {
  const problems = [];
  const tokensRows = lexicon.entries.filter((e) => e.method === 'TOKENS' && isCs(e));
  for (const [word, ref] of Object.entries(CHANNEL_WORDS)) {
    for (const probe of [word, `z ${word}`]) {
      const holding = tokensRows.filter((e) => ` ${e.termNormalized} `.includes(` ${probe} `));
      const refs = [...new Set(holding.map((e) => e.targetRef))];
      if (!holding.length) problems.push(`no TOKENS phrase holds «${probe}» (the control is gone)`);
      else if (refs.length !== 1 || refs[0] !== ref) problems.push(`«${probe}» reaches ${refs.join(', ')} through ${holding.map((e) => `«${e.termNormalized}»`).join(', ')}`);
    }
  }
  assert.deepEqual(problems, [], problems.join('; '));
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
