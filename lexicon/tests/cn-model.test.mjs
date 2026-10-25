// CN-P6 S6.2 — generated/model.tar.zst, the model the resolver's cn doors serve (scripts/cn-model-snapshot.mjs).
//
// The doors serve a model only when its content id is the lexicon archive's `modelSnapshotHash`; on a mismatch every
// `statement.*` / `definition.render` call answers unavailable. So the archive must hold model/ exactly, and the two
// archives must name the same model — `just build-lexicon` writes both, `just check-lexicon` re-checks both, and this
// suite holds the committed pair to it.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { contentId, differences, lexiconPin, modelFiles, readSnapshot, repoRoot } from '../../scripts/cn-model-snapshot.mjs';

const files = modelFiles();
const snap = readSnapshot();

test('the committed archive holds model/ exactly — every .ttr / .ttrm, by its model/-relative path', () => {
  assert.ok(files.size > 0);
  assert.deepEqual(differences(snap, files), [], 'stale: just build-lexicon');
  assert.ok([...snap.docs.keys()].every((rel) => !rel.startsWith('model/')), 'docs/ IS the model tree, not its parent');
});

test('its content id is the one the lexicon was compiled from — the pin the doors check', () => {
  const id = contentId(files);
  assert.equal(lexiconPin(), id);
  assert.equal(JSON.parse(snap.manifest).resolvedFrom.modelContentId, id);
});

test('snapshot.json is a ttr-snapshot manifest: its keys only (the reader takes no other), kind models', () => {
  const m = JSON.parse(snap.manifest);
  assert.deepEqual(Object.keys(m), ['formatVersion', 'kind', 'qnames', 'producedBy', 'resolvedFrom']);
  assert.equal(m.formatVersion, 1);
  assert.equal(m.kind, 'models');
});

test('it rides the hartland-lexicon ConfigMap beside the lexicon — one update swaps both', () => {
  const kustomization = readFileSync(path.join(repoRoot, 'generated/kustomization.yaml'), 'utf-8');
  assert.match(kustomization, /- name: hartland-lexicon\n\s+files:\n\s+- lexicon\.tar\.zst\n\s+- model\.tar\.zst\n/);
});

test('one recipe builds both archives and one checks both', () => {
  const justfile = readFileSync(path.join(repoRoot, 'justfile'), 'utf-8');
  const recipe = (name) => justfile.slice(justfile.indexOf(`\n${name} `), justfile.indexOf('\n\n', justfile.indexOf(`\n${name} `)));
  assert.match(recipe('build-lexicon'), /node scripts\/cn-model-snapshot\.mjs\n?$/);
  assert.match(recipe('check-lexicon'), /node scripts\/cn-model-snapshot\.mjs --check/);
});
