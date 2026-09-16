// Stage 2.6 T6.3/T6.4 — both Shems assemble (parse, prompts mounted, register against
// area hartland), visibility contrast (CFO-only finance Shem, disjoint from the main
// Shem's role). Mocked/unit: no live Keycloak/kantheon assembly — checks the YAML
// contract this repo owns. Uses js-yaml borrowed from the sibling tatrman checkout's
// node_modules (a transitive dependency there, not a declared one — documented fragility,
// same spirit as borrowing @tatrman/parser elsewhere in these suites).
// Run: node --test agents/tests/shems.test.mjs (from the hartland repo root).

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const hartlandRoot = path.resolve(here, '../..');
const yamlModulePath = path.resolve(
  hartlandRoot,
  '../tatrman/node_modules/.pnpm/js-yaml@4.1.1/node_modules/js-yaml/dist/js-yaml.mjs',
);
const yaml = await import(yamlModulePath);

async function loadYaml(relPath) {
  const content = await readFile(path.join(hartlandRoot, relPath), 'utf-8');
  return yaml.load(content);
}

async function dirNonEmpty(relPath) {
  try {
    const entries = await readdir(path.join(hartlandRoot, relPath));
    return entries.filter((e) => !e.startsWith('.')).length > 0;
  } catch {
    return false;
  }
}

const agentDef = await loadYaml('agents/hartland.yaml');
const mainShem = await loadYaml('agents/golem/shems/golem-hartland/shem.yaml');
const financeShem = await loadYaml('agents/golem/shems/golem-hartland-finance/shem.yaml');

// IE-P4·S4.2 — the investment estate's Shem, deployed from this repo (D1, ruled 2026-09-16).
const investmentDef = await loadYaml('agents/investment.yaml');
const investmentShem = await loadYaml('agents/golem/shems/golem-investment/shem.yaml');

test('T6.a — agents/hartland.yaml parses and matches the ai-models agent-def shape', () => {
  assert.equal(agentDef.kind, 'golem');
  assert.equal(agentDef.id, 'hartland');
  assert.ok(agentDef.label?.length > 0 && agentDef.label.length <= 40, 'label must be 1-40 chars');
  assert.ok(!agentDef.label.includes("'"), "label must not contain a single quote (env.js passthrough)");
  assert.deepEqual(agentDef.shem.areas, ['hartland']);
});

test('T6.b — both Shem overlays parse and reference the hartland agent def', () => {
  for (const shem of [mainShem, financeShem]) {
    assert.equal(shem.kind, 'golem-shem');
    assert.equal(shem.source.repo, 'hartland');
    assert.equal(shem.source.agentDef, 'agents/hartland.yaml');
    assert.deepEqual(shem.source.areas, ['hartland']);
  }
  assert.equal(mainShem.source.label, 'Hartland Analytics');
  assert.equal(financeShem.source.label, 'Hartland Finance');
});

test('T6.c — both Shems mount prompts/{en,cs}, non-empty', async () => {
  for (const shemDir of ['golem-hartland', 'golem-hartland-finance']) {
    for (const locale of ['en', 'cs']) {
      const has = await dirNonEmpty(`agents/golem/shems/${shemDir}/prompts/${locale}`);
      assert.ok(has, `agents/golem/shems/${shemDir}/prompts/${locale} is empty or missing`);
    }
  }
});

test('T6.d — visibility contrast: the two Shems have disjoint visibility_roles (F-1 governance cameo)', () => {
  const mainRoles = new Set(mainShem.overlay.visibility_roles);
  const financeRoles = new Set(financeShem.overlay.visibility_roles);
  assert.deepEqual([...mainRoles], ['kantheon-area-hartland']);
  assert.deepEqual([...financeRoles], ['kantheon-role-finance']);
  const overlap = [...mainRoles].filter((r) => financeRoles.has(r));
  assert.deepEqual(overlap, [], `visibility_roles overlap: ${overlap.join(', ')} — finance Shem must be unroutable for the main role`);
});

test('T6.e — every example_question and counter_example is present in BOTH en and cs, non-empty', () => {
  for (const shem of [mainShem, financeShem]) {
    for (const field of ['example_questions', 'counter_examples']) {
      const value = shem.overlay[field];
      assert.ok(value?.en?.length > 0, `${shem.source.label}.overlay.${field}.en is empty`);
      assert.ok(value?.cs?.length > 0, `${shem.source.label}.overlay.${field}.cs is empty`);
    }
  }
});

test('T6.f — finance Shem preferred_query_subset is a subset of the 15 q.hartland.* names', async () => {
  const { loadHartlandProject } = await import('../../model/tests/project-harness.mjs');
  const project = await loadHartlandProject();
  const queryNames = new Set();
  for (const [, ast] of project.asts) {
    for (const def of ast.definitions ?? []) if (def.kind === 'query') queryNames.add(def.name);
  }
  for (const name of financeShem.overlay.preferred_query_subset) {
    assert.ok(queryNames.has(name), `finance Shem references unknown query '${name}'`);
  }
});

// ── IE-P4·S4.2 — the investment Shem ────────────────────────────────────────────────────────────

test('IE — agents/investment.yaml parses and matches the agent-def shape', () => {
  assert.equal(investmentDef.kind, 'golem');
  assert.equal(investmentDef.id, 'investment');
  assert.ok(investmentDef.label?.length > 0 && investmentDef.label.length <= 40, 'label must be 1-40 chars');
  assert.ok(!investmentDef.label.includes("'"), "label must not contain a single quote (env.js passthrough)");
  assert.deepEqual(investmentDef.shem.areas, ['investment']);
});

test('IE — the investment overlay is self-contained in THIS repo (BM-9), on area investment', () => {
  assert.equal(investmentShem.kind, 'golem-shem');
  assert.equal(investmentShem.source.repo, 'hartland');
  assert.equal(investmentShem.source.agentDef, 'agents/investment.yaml');
  assert.equal(investmentShem.source.id, 'investment');
  assert.equal(investmentShem.source.label, 'Investment Q&A');
  assert.deepEqual(investmentShem.source.areas, ['investment']);
  assert.deepEqual(investmentShem.overlay.visibility_roles, ['kantheon-area-investment']);
});

test('IE — ⚑IE-9: the overlay declares NO capability refs, and names no midas tool', () => {
  // Midas-core is not deployable on this estate, and a ref here rides the REGISTERED manifest —
  // so declaring one advertises a capability that fails when used.
  assert.deepEqual(investmentShem.overlay.capability_refs, []);
  assert.ok(
    !JSON.stringify(investmentShem).toLowerCase().includes('midas'),
    'no "midas" may appear anywhere in the investment overlay (⚑IE-9)',
  );
});

test('IE — the router text and examples describe THIS book, in both locales', () => {
  const router = investmentShem.overlay.description_for_router;
  assert.ok(router.includes('query door'), 'the router text must say how it reads the book');
  for (const field of ['example_questions', 'counter_examples']) {
    const value = investmentShem.overlay[field];
    assert.ok(value?.en?.length > 0, `overlay.${field}.en is empty`);
    assert.ok(value?.cs?.length > 0, `overlay.${field}.cs is empty`);
  }
  // Every example is answerable, so each must carry an id shape the curated queries take.
  for (const q of investmentShem.overlay.example_questions.en) {
    assert.ok(q.includes('conseq:'), `example question names no conseq: id — "${q}"`);
  }
  // Returns/fees are unanswerable here, so they may be NAMED as counter-examples and must never be
  // ADVERTISED as example questions. The scan is the example lists only, deliberately: the router
  // text says "the book records no dividend or fee movement", which is the honest sentence for it
  // to carry — a whole-overlay scan would forbid the Golem from describing its own limits.
  const advertised = JSON.stringify(investmentShem.overlay.example_questions).toLowerCase();
  for (const token of ['ytd', 'dividend', 'fee', 'aapl', 'return']) {
    assert.ok(!advertised.includes(token), `'${token}' is advertised as an example question`);
  }
});

test('IE — prompts/{en,cs}/intent.yaml are mounted, and free-sql/chip-topup are NOT packed', async () => {
  for (const locale of ['en', 'cs']) {
    const has = await dirNonEmpty(`agents/golem/shems/golem-investment/prompts/${locale}`);
    assert.ok(has, `prompts/${locale} is empty or missing`);
    const intent = await readFile(
      path.join(hartlandRoot, `agents/golem/shems/golem-investment/prompts/${locale}/intent.yaml`),
      'utf-8',
    );
    // The estate's id shapes and its only currency live in the prompt or nowhere.
    for (const token of ['conseq:', 'ISIN', 'CZK']) {
      assert.ok(intent.includes(token), `prompts/${locale}/intent.yaml does not state ${token}`);
    }
  }
  // The GENERATED KEYS, not the file text: the kustomization's own comment explains why free-sql and
  // chip-topup are absent, and a naive substring scan reads that explanation as a violation.
  const kustomization = yaml.load(
    await readFile(
      path.join(hartlandRoot, 'agents/golem/shems/golem-investment/kustomization.yaml'),
      'utf-8',
    ),
  );
  const packed = kustomization.configMapGenerator.flatMap((g) => g.files ?? []);
  assert.deepEqual(
    packed,
    ['shem.yaml', 'prompts-en-intent.yaml=prompts/en/intent.yaml', 'prompts-cs-intent.yaml=prompts/cs/intent.yaml'],
    'the bundle packs shem.yaml + both intent prompts and nothing else — free-sql/chip-topup have no ' +
      'live consumer, and an unmounted key is a file in the ConfigMap and absent from the pod',
  );
});

// ⛔ THE DRIFT GUARD. This bundle is DEPLOYED from here and AUTHORED in kantheon, where the Kotest
// specs assert it against the real parser and assembler. Two copies with no compiler between them is
// how S1.5·D14 happened — an olymp commit restored the pre-review body of two files and nothing
// noticed. So: change one side and copy it in the same commit. Two differences are sanctioned and
// listed below; anything else is drift and fails here.
test('IE — the deployed overlay matches kantheon\'s authoring copy, bar the two sanctioned differences', async (t) => {
  const kantheonShem = path.resolve(
    hartlandRoot,
    '../kantheon/agents/golem/shems/golem-investment/shem.yaml',
  );
  let authored;
  try {
    authored = yaml.load(await readFile(kantheonShem, 'utf-8'));
  } catch {
    // Loud skip, the render-app convention: no sibling checkout must never read as a pass.
    t.skip(`no kantheon sibling at ${kantheonShem} — THE DRIFT CHECK DID NOT RUN.`);
    return;
  }

  // (1) BM-9 self-containment: kantheon names ai-models, this repo names itself.
  assert.equal(authored.source.repo, 'ai-models', 'kantheon copy changed its source.repo — re-read this guard');
  // (2) BM-6 per-locale lists here; kantheon authors them flat.
  assert.ok(Array.isArray(authored.overlay.example_questions), 'kantheon copy is no longer flat');

  const normalise = (shem) => ({
    ...shem,
    source: { ...shem.source, repo: undefined, agentDef: undefined },
    overlay: { ...shem.overlay, example_questions: undefined, counter_examples: undefined },
  });
  assert.deepEqual(
    normalise(investmentShem),
    normalise(authored),
    'the deployed overlay and kantheon\'s authoring copy have drifted — copy the change across in ' +
      'the same commit (only source.repo/agentDef and the example/counter lists may differ)',
  );

  // The English example questions must be the same set, whatever their shape.
  assert.deepEqual(
    investmentShem.overlay.example_questions.en,
    authored.overlay.example_questions,
    'the en example questions differ between the deployed and authored copies',
  );
});

test('T6.g — no profit/margin anywhere in either Shem overlay (D-6a)', () => {
  const BANNED = ['profit', 'margin'];
  for (const shem of [mainShem, financeShem]) {
    const text = JSON.stringify(shem).toLowerCase();
    for (const token of BANNED) {
      // "profit margin isn't modeled" counter_examples are ALLOWED to mention the
      // words (they're the deliberate gap-ammo) — only fail if the token appears
      // OUTSIDE the counter_examples block.
      const withoutCounters = JSON.stringify({ ...shem, overlay: { ...shem.overlay, counter_examples: undefined } }).toLowerCase();
      assert.ok(!withoutCounters.includes(token), `'${token}' found outside counter_examples in ${shem.source.label}`);
    }
  }
});
