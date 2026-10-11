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
