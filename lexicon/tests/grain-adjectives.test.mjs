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
