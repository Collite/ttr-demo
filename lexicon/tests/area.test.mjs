// RV-P3.2 T3 — structural guards over the root `lexicon/` data area.
//
// Cheap and fast, and deliberately shallow: the Kotlin validator (`ttr-lexicon`, the
// RG-LEX-* catalogue) is the authority on this schema, and `just build-lexicon` runs it.
// These run in a second with no dependencies and catch the mistakes that would otherwise
// cost a JVM round trip — a missing `schema:` line, a `target:` that is neither a
// `ground:` kind nor a dotted model ref, a skill file whose `op` lost its prefix.
//
// No YAML parser: this repo is content-only (BM-9) and pulls in no dependencies. The
// checks are therefore line-oriented over files we author in a known style. That is a real
// limit — a structurally valid file could still be semantically wrong — and it is why
// these are guards rather than validation.
//
// Run: node --test lexicon/tests/area.test.mjs   (or `just verify-model`, which finds it)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, existsSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

const areaRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = path.resolve(areaRoot, '..');

/** Every file under `lexicon/` with the given extension, recursively, repo-relative. */
function filesUnder(dir, ext) {
  const out = [];
  if (!existsSync(dir)) return out;
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) out.push(...filesUnder(full, ext));
    else if (name.endsWith(ext)) out.push(full);
  }
  return out;
}

const lexFiles = filesUnder(areaRoot, '.lex.yaml');
const skillFiles = filesUnder(path.join(areaRoot, 'skills'), '.md');

// The closed `ground:` set (RV-42). A fourth kind is a kernel change, not an authoring one,
// so a typo here should fail rather than compile into a row nothing will ever look up.
const GROUND_KINDS = new Set(['ground:chrono', 'ground:money', 'ground:geo']);

test('T3.1 — the area has at least one data file (the area exists at all)', () => {
  assert.ok(lexFiles.length > 0, `no *.lex.yaml under ${areaRoot}`);
});

test('T3.2 — every .lex.yaml declares schema: ttr-lexicon/v1', () => {
  const offenders = [];
  for (const file of lexFiles) {
    const text = readFileSync(file, 'utf-8');
    if (!/^schema:\s*ttr-lexicon\/v1\s*$/m.test(text)) offenders.push(path.relative(repoRoot, file));
  }
  assert.deepEqual(offenders, [], `missing or wrong schema line: ${offenders.join(', ')}`);
});

test('T3.3 — every target: is a ground: kind from the closed set, or a dotted model ref', () => {
  const offenders = [];
  for (const file of lexFiles) {
    const rel = path.relative(repoRoot, file);
    for (const [i, line] of readFileSync(file, 'utf-8').split('\n').entries()) {
      const m = /^\s*(?:-\s*)?target:\s*(\S+)\s*$/.exec(line);
      if (!m) continue;
      const target = m[1];
      if (target.startsWith('ground:')) {
        if (!GROUND_KINDS.has(target)) offenders.push(`${rel}:${i + 1}: unknown ground kind ${target}`);
      } else if (!/^[a-z][a-zA-Z0-9_]*(\.[a-zA-Z0-9_]+)+$/.test(target)) {
        offenders.push(`${rel}:${i + 1}: ${target} is neither a ground: kind nor a dotted model ref`);
      }
    }
  }
  assert.deepEqual(offenders, [], offenders.join('; '));
});

test('T3.4 — every skill .md has frontmatter with an op:-prefixed op', () => {
  const offenders = [];
  for (const file of skillFiles) {
    const rel = path.relative(repoRoot, file);
    const text = readFileSync(file, 'utf-8');
    if (!text.startsWith('---\n')) {
      offenders.push(`${rel}: no frontmatter`);
      continue;
    }
    const front = text.slice(4, text.indexOf('\n---', 4));
    const op = /^op:\s*(\S+)\s*$/m.exec(front);
    if (!op) offenders.push(`${rel}: frontmatter has no op:`);
    else if (!op[1].startsWith('op:')) offenders.push(`${rel}: op ${op[1]} is missing the op: prefix`);
    if (!/^schema:\s*ttr-skill\/v1\s*$/m.test(front)) offenders.push(`${rel}: not schema: ttr-skill/v1`);
  }
  assert.deepEqual(offenders, [], offenders.join('; '));
});

test('T3.5 — no place names in ground:geo (RV-42: the gazetteer is parked, geo-side)', () => {
  // This estate's corpus is full of them — Brno, Praha, Memphis, Nashville — and a term in
  // the geo class says "this span is about geography", never "which place". The compiler's
  // own GroundingStdlibSpec holds the stdlib to this line; the estate is held to it here.
  const PLACES = ['brno', 'praha', 'prague', 'memphis', 'nashville', 'tennessee', 'ostrava', 'plzeň'];
  const offenders = [];
  for (const file of lexFiles) {
    const rel = path.relative(repoRoot, file);
    const text = readFileSync(file, 'utf-8');
    // Only the entry that targets ground:geo — a place name in a comment is prose.
    for (const block of text.split(/^\s*-\s+terms:/m).slice(1)) {
      if (!/target:\s*ground:geo/.test(block)) continue;
      for (const m of block.matchAll(/text:\s*"([^"]+)"/g)) {
        if (PLACES.includes(m[1].toLowerCase())) offenders.push(`${rel}: place name "${m[1]}" in ground:geo`);
      }
    }
  }
  assert.deepEqual(offenders, [], offenders.join('; '));
});

// ── T4's "author once" guard ───────────────────────────────────────────────────────────
// P1.2 T7's naming decision: `lexicon/` and `model/lexicon/{cs,en}/*.ttrm` are two surfaces
// of ONE declared layer. A term written on both is that layer saying the same thing twice,
// and the compiler only catches it (`RG-LEXC-002`) when the target matches too — which is
// the case this repo is LEAST likely to hit, because the sugar surface and the data area
// were authored months apart by different stages. So it is caught here instead.
//
// Deliberately compares text only, not text+target: the failure worth stopping is "this
// word is already declared somewhere", and the author needs to see it either way.
test('T4 — no term is declared on both the data area and the .ttrm sugar surface', () => {
  const sugar = new Map(); // normalized form -> the file that declares it
  for (const locale of ['cs', 'en']) {
    const dir = path.join(repoRoot, 'model', 'lexicon', locale);
    if (!existsSync(dir)) continue;
    for (const file of readdirSync(dir).filter((f) => f.endsWith('.ttrm'))) {
      const text = readFileSync(path.join(dir, file), 'utf-8');
      // `forms: ["a", "b", …]` — the only place the sugar surface spells a matchable term.
      for (const list of text.matchAll(/^\s*forms:\s*\[([^\]]*)\]/gm)) {
        for (const m of list[1].matchAll(/"([^"]+)"/g)) {
          sugar.set(m[1].toLowerCase(), `model/lexicon/${locale}/${file}`);
        }
      }
    }
  }
  assert.ok(sugar.size > 0, 'found no forms: in the .ttrm sugar surface — the guard would pass vacuously');

  const offenders = [];
  for (const file of lexFiles) {
    const rel = path.relative(repoRoot, file);
    for (const [i, line] of readFileSync(file, 'utf-8').split('\n').entries()) {
      // Only real term lines: a `text:` inside a flow mapping. Prose in comments is prose.
      const m = /^\s*-?\s*\{\s*text:\s*"([^"]+)"/.exec(line);
      if (!m) continue;
      const hit = sugar.get(m[1].toLowerCase());
      if (hit) offenders.push(`${rel}:${i + 1}: "${m[1]}" is already declared in ${hit}`);
    }
  }
  assert.deepEqual(offenders, [], offenders.join('; '));
});

// ── T5's layering assertion ────────────────────────────────────────────────────────────
// Needs the Kotlin CLI, which lives in the sibling tatrman checkout the same way
// model/lexicon/tests/lexicon.test.mjs needs @tatrman/semantics' dist. Skipped with a
// reason rather than failed when it is not built, so `just verify-model` stays runnable on
// a machine that has not built the toolchain.
// `TTR_LEXICON_CLI` overrides the sibling-checkout default, the same escape hatch the
// justfile's `cli=` parameter gives every other toolchain recipe here.
const CLI =
  process.env.TTR_LEXICON_CLI ??
  path.resolve(repoRoot, '../tatrman/packages/kotlin/ttr-lexicon-cli/build/install/ttr-lexicon/bin/ttr-lexicon');
const cliMissing = !existsSync(CLI) && 'ttr-lexicon not built — run `just build-lexicon` from a tatrman checkout first';

function groundingCount(args) {
  const out = execFileSync(CLI, ['build', repoRoot, '--out', path.join(process.env.TMPDIR ?? '/tmp', 'layering.tar.zst'), ...args], {
    encoding: 'utf-8',
    stdio: ['ignore', 'pipe', 'ignore'],
  });
  const m = /GROUNDING_TRIGGER:\s*(\d+)/.exec(out);
  assert.ok(m, `no GROUNDING_TRIGGER count in CLI output:\n${out}`);
  return Number(m[1]);
}

test('T5 — the artifact carries BOTH stdlib and estate grounding terms for the same kind', { skip: cliMissing }, () => {
  const estateOnly = groundingCount(['--no-stdlib']);
  const layered = groundingCount([]);

  // Both halves are real: the estate contributes rows, and the stdlib contributes strictly
  // more on top. Equality either way would mean one layer is silently not reaching the
  // artifact — which is the failure this asserts against, not the row counts themselves.
  assert.ok(estateOnly > 0, 'the estate contributes no grounding terms of its own');
  assert.ok(layered > estateOnly, `layering added nothing: ${layered} with stdlib vs ${estateOnly} without`);
});

// LR (2026-10-11) — the resolver's anchors match a term by the token as written or by its
// lemma, never by a declension. The stock measure's words are inflected in every question
// that names them («výpadky zásob», «v zásobách»), and all of those lemmatise to `zásoba`:
// without that citation form no anchor said "stock", and a place word took the store
// instead of the DC the stock fact reaches.
test('T6 — the stock measure declares its citation form, the one an anchor reads', () => {
  const file = path.join(areaRoot, 'aliases', 'hartland.lex.yaml');
  const blocks = readFileSync(file, 'utf-8').split(/^\s*- terms:\s*$/m);
  const stock = blocks.find((b) => /^\s*target:\s*er\.entity\.inventory\.quantity_on_hand\s*$/m.test(b));
  assert.ok(stock, 'no term block targets er.entity.inventory.quantity_on_hand');
  const terms = [...stock.matchAll(/\{\s*text:\s*"([^"]+)"/g)].map((m) => m[1]);
  assert.ok(terms.includes('zásoba'), `the stock terms are ${terms.join(', ')} — «zásoba» is missing`);
});
