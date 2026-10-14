// ttr-server#237 — the Czech grain ADJECTIVES („měsíční“, „roční“, „čtvrtletní“, „týdenní“), checked in
// the COMMITTED ARCHIVE.
//
// „Měsíční tržby z tržiště v roce 2025“ asks for months. The estate declared the adverb (`měsíčně`) and
// the phrase (`po měsících`) for the month attribute, never the adjective, so live on 2026-10-14
// (resolver 0.11.21) „Měsíční“ bound nothing: in front of the declared phrase it vanished — no mention,
// no gap — and the question was answered as one total; before a bare noun („Měsíční tržby“) the phrase
// was a G1. English "Monthly" binds because `monthly` is declared, and the resolver reads a calendar
// adjective bound to an attribute as the GROUPING (R6"). These terms give Czech the same anchor.
//
// Why the archive and not the sources: what the matcher serves IS this file, and
// `just check-lexicon` (CI) proves it is what the sources compile to.
//
// Run: node --test lexicon/tests/grain-adjectives.test.mjs   (or `just verify-model`)

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
const rowsOf = (term) => lexicon.entries.filter((e) => e.termNormalized === term && isCs(e));

/** The six case forms of a soft adjective (jarní type), singular and plural share them. */
const forms = (stem) => ['í', 'ího', 'ímu', 'ím', 'ích', 'ími'].map((ending) => stem + ending);

const GRAINS = {
  'er.entity.date_dim.month': forms('měsíčn'),
  'er.entity.date_dim.year': forms('ročn'),
  'er.entity.date_dim.quarter': forms('čtvrtletn'),
  'er.entity.date_dim.week_seq': forms('týdenn'),
};

test('control — the archive decodes, and the adverb each grain already had is still there', () => {
  assert.ok(lexicon.entries.length > 400, `only ${lexicon.entries.length} entries`);
  for (const [adverb, target] of [
    ['měsíčně', 'er.entity.date_dim.month'],
    ['ročně', 'er.entity.date_dim.year'],
    ['čtvrtletně', 'er.entity.date_dim.quarter'],
    ['týdně', 'er.entity.date_dim.week_seq'],
  ]) {
    assert.deepEqual(rowsOf(adverb).map((e) => e.targetRef), [target], adverb);
  }
});

test('#237 — every case form of the four grain adjectives is a DECLARED model-object row of its grain, and only of it', () => {
  const problems = [];
  for (const [target, words] of Object.entries(GRAINS)) {
    for (const word of words) {
      const rows = rowsOf(word);
      const refs = rows.map((e) => e.targetRef);
      if (refs.length !== 1 || refs[0] !== target) problems.push(`${word}: ${JSON.stringify(refs)} (want ${target})`);
      for (const e of rows) {
        if (e.sourceTag !== 'DECLARED' || e.targetClass !== 'MODEL_OBJECT') {
          problems.push(`${word}: ${e.sourceTag} ${e.targetClass}`);
        }
      }
    }
  }
  assert.deepEqual(problems, []);
});

test('#237 — no grain adjective is a grounding trigger: it is the breakdown, never a period of its own', () => {
  const triggers = Object.values(GRAINS)
    .flat()
    .flatMap((word) => rowsOf(word))
    .filter((e) => e.targetClass === 'GROUNDING_TRIGGER');
  assert.deepEqual(triggers, []);
});

test('#237 — no day or half-year adjective: the estate declares no such grain, so the word stays a G1 the user is asked about', () => {
  for (const word of [...forms('denn'), ...forms('pololetn')]) {
    assert.deepEqual(rowsOf(word).filter((e) => e.targetRef.startsWith('er.')), [], word);
  }
});

// The words one edit from a grain adjective — the period nouns the time kernel owns (`čtvrtletí`, in
// every case the adjective shares an ending with), and ordinary words that are no grain at all
// (`ročník` a vintage, `ruční` manual, `měsíčník` a monthly magazine). Under the file's default profile
// (`typos: { distance: 1 }`) each new row reached its neighbour: lex-matcher 0.11.3 answered
// «čtvrtletí» with `čtvrtletní` → the quarter attribute at 0.95 beside chrono's own trigger, and
// «čtvrtletím» with `čtvrtletním` → the quarter in a tie with that trigger; «ročník» reached the year.
const NEIGHBOURS = [
  'čtvrtletí', 'čtvrtletím', 'čtvrtletích', 'čtvrtletími',
  'ročník', 'ročníku', 'ruční', 'ručním', 'ručních', 'měsíčník', 'měsíčníku',
];

const canonical = (s) => s.normalize('NFC').toLowerCase();
const folded = (s) => s.normalize('NFD').replace(/\p{M}+/gu, '').toLowerCase();

function editDistance(a, b) {
  const row = [...Array(b.length + 1).keys()];
  for (let i = 1; i <= a.length; i++) {
    let diagonal = row[0];
    row[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const above = row[j];
      row[j] = Math.min(row[j] + 1, row[j - 1] + 1, diagonal + (a[i - 1] === b[j - 1] ? 0 : 1));
      diagonal = above;
    }
  }
  return row[b.length];
}

/** Whether a row's declared profile admits [query] — the rules RV-44 profiles state, read literally. */
function reaches(row, query) {
  return row.matchProfile.rules.some((rule) => {
    const norm = rule.norm === 'folded' ? folded : canonical;
    const [term, asked] = [norm(row.termNormalized), norm(query)];
    if (rule.exact != null && term === asked) return true;
    return rule.typos != null && editDistance(term, asked) <= rule.typos.distance;
  });
}

const grainRows = () => Object.values(GRAINS).flat().flatMap((word) => rowsOf(word));

test('#237 — no grain adjective reaches a word one edit away: the period noun stays the time kernel\'s', () => {
  const reached = [];
  for (const row of grainRows()) {
    for (const word of NEIGHBOURS) {
      if (reaches(row, word)) reached.push(`${word} → ${row.termNormalized} (${row.targetRef})`);
    }
  }
  assert.deepEqual(reached, []);
});

test('#237 — every grain adjective is still read as written and without diacritics', () => {
  const problems = [];
  for (const row of grainRows()) {
    if (!reaches(row, row.termNormalized)) problems.push(`${row.termNormalized}: not as written`);
    if (!reaches(row, folded(row.termNormalized))) problems.push(`${row.termNormalized}: not without diacritics`);
  }
  assert.deepEqual(problems, []);
});
