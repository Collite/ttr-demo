// scripts/demo-compare.sh (SO-demo P2·S2.1, contracts §5, SD-D4) — the live change against demo/returns-review.
// Two fixture trees on a local bare `origin`: the reference branch, and a live branch made from it with one change
// per test. The archives are real tar + zstd, built here, so the normalisation runs over what the script unpacks in
// the show. Needs git, tar and zstd. Run: node --test model/tests/demo-compare.test.mjs.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const script = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../scripts/demo-compare.sh');
const REF = 'demo/returns-review';
const LIVE = 'model/u/1';
const ID = ['-c', 'user.name=t', '-c', 'user.email=t@t'];

const LAYOUT = (positions) => `graph returns_review {
  model: er,
  objects: [
    hartland.er.entity.return_request,
    hartland.er.entity.returns_review
  ],
  layout: {
    nodes: {
      hartland.er.entity.return_request: { x: ${positions[0]}, y: 0 },
      hartland.er.entity.returns_review: { x: ${positions[1]}, y: 0 }
    }
  }
}
`;
const SNAPSHOT = (id) => `${JSON.stringify({ formatVersion: 1, kind: 'lexicon', qnames: [], producedBy: 'ttr-lexicon-cli',
  resolvedFrom: { modelSnapshotId: id } }, null, 2)}\n`;

// The reference tree, as files: path → content. An archive is { members, level } — built by `pack`.
const base = () => ({
  'modeler.toml': '[project]\nname = "hartland"\n',
  'model/er/returns-review.ttrm': 'package hartland\n\nmodel er\n\ndef entity returns_review { attributes: [ request_id int ] }\n',
  'model/er/tests/er.test.mjs': "const EXPECTED = [\n  'returns_review',\n];\n",
  'model/layouts/returns_review.ttrg': LAYOUT([520, 0]),
  'model/layouts/agent/agent_hartland.ttrg': 'graph agent_hartland {\n  model: er,\n  objects: [ hartland.er.entity.returns_review ]\n}\n',
  'generated/resolved-packages.json': '{ "formatVersion": 1, "generatedFrom": "hartland" }\n',
  'generated/lexicon.tar.zst': { level: 19, members: {
    'snapshot.json': SNAPSHOT('sha256:aaaa'),
    'docs/lexicon.json': '{ "rows": [ { "text": "returns review", "target": "er.entity.returns_review" } ] }\n',
  } },
  'README.md': 'hartland\n',
});

async function pack(file, { members, level }) {
  const dir = await mkdtemp(path.join(tmpdir(), 'demo-compare-pack-'));
  for (const [name, text] of Object.entries(members)) {
    await mkdir(path.dirname(path.join(dir, name)), { recursive: true });
    await writeFile(path.join(dir, name), text);
  }
  const tarball = execFileSync('tar', ['-c', '-f', '-', '-C', dir, ...Object.keys(members).sort()]);
  execFileSync('zstd', ['-q', `-${level}`, '-f', '-o', file], { input: tarball });
  await rm(dir, { recursive: true, force: true });
}

async function writeTree(dir, tree) {
  for (const [rel, content] of Object.entries(tree)) {
    const file = path.join(dir, rel);
    await mkdir(path.dirname(file), { recursive: true });
    if (content === null) await rm(file, { force: true });
    else if (typeof content === 'string') await writeFile(file, content);
    else await pack(file, content);
  }
}

// origin with REF = base() and LIVE = base() + `change`; the script runs in a clone of origin, as in the show.
async function compare(change, args = [LIVE]) {
  const work = await mkdtemp(path.join(tmpdir(), 'demo-compare-'));
  try {
    const git = (dir, ...a) => execFileSync('git', ['-C', dir, ...ID, ...a], { encoding: 'utf-8' });
    const origin = path.join(work, 'origin.git');
    const seed = path.join(work, 'seed');
    execFileSync('git', ['init', '-q', '--bare', origin]);
    execFileSync('git', ['init', '-q', seed]);
    await writeTree(seed, base());
    git(seed, 'add', '-A');
    git(seed, 'commit', '-q', '-m', 'the pre-authored branch');
    git(seed, 'push', '-q', origin, `HEAD:refs/heads/${REF}`);
    await writeTree(seed, change);
    git(seed, 'add', '-A');
    git(seed, 'commit', '-q', '--allow-empty', '-m', 'the live change');
    git(seed, 'push', '-q', origin, `HEAD:refs/heads/${LIVE}`);
    const show = path.join(work, 'show');
    execFileSync('git', ['clone', '-q', '-b', REF, `file://${origin}`, show]);
    return spawnSync('bash', [script, ...args], { cwd: show, encoding: 'utf-8' });
  } finally {
    await rm(work, { recursive: true, force: true });
  }
}

const differing = (r) => r.stdout.split('\n').slice(r.stdout.split('\n').findIndex((l) => /path\(s\) differ:$/.test(l)) + 1)
  .filter(Boolean);

test('C1 — the same change: exit 0, clean', async () => {
  const r = await compare({});
  assert.equal(r.status, 0, r.stderr + r.stdout);
  assert.match(r.stdout, /demo-compare: clean/);
});

test('C2 — the lexicon archive repacked with another model id and zstd level: normalised, exit 0', async () => {
  const lexicon = base()['generated/lexicon.tar.zst'];
  const r = await compare({ 'generated/lexicon.tar.zst': { level: 3,
    members: { ...lexicon.members, 'snapshot.json': SNAPSHOT('sha256:bbbb') } } });
  assert.equal(r.status, 0, r.stderr + r.stdout);
  assert.match(r.stdout, /normalised — generated\/lexicon\.tar\.zst \(resolvedFrom ids only\)/);
  assert.match(r.stdout, /demo-compare: clean/);
});

test('C3 — a lexicon row the live archive lacks: exit 1, the archive listed', async () => {
  const r = await compare({ 'generated/lexicon.tar.zst': { level: 19, members: {
    'snapshot.json': SNAPSHOT('sha256:aaaa'), 'docs/lexicon.json': '{ "rows": [] }\n' } } });
  assert.equal(r.status, 1, r.stderr + r.stdout);
  assert.deepEqual(differing(r), ['generated/lexicon.tar.zst']);
});

test('C4 — anything else in snapshot.json still counts: exit 1', async () => {
  const lexicon = base()['generated/lexicon.tar.zst'];
  const r = await compare({ 'generated/lexicon.tar.zst': { level: 19,
    members: { ...lexicon.members, 'snapshot.json': SNAPSHOT('sha256:aaaa').replace('ttr-lexicon-cli', 'another') } } });
  assert.equal(r.status, 1, r.stderr + r.stdout);
  assert.deepEqual(differing(r), ['generated/lexicon.tar.zst']);
});

test('C5 — the saved layout with the cards placed elsewhere: normalised, exit 0', async () => {
  const r = await compare({ 'model/layouts/returns_review.ttrg': LAYOUT([480.5, -40]) });
  assert.equal(r.status, 0, r.stderr + r.stdout);
  assert.match(r.stdout, /normalised — model\/layouts\/returns_review\.ttrg \(positions only\)/);
});

test('C6 — the saved layout without a layout block at all: normalised, exit 0', async () => {
  const r = await compare({ 'model/layouts/returns_review.ttrg': LAYOUT([520, 0]).replace(/,\n {2}layout: \{[^]*\n {2}\}\n/, '\n') });
  assert.equal(r.status, 0, r.stderr + r.stdout);
  assert.match(r.stdout, /positions only/);
});

test('C7 — the saved layout with another object, and the bot\'s layout moved: exit 1, both listed', async () => {
  const r = await compare({
    'model/layouts/returns_review.ttrg': LAYOUT([520, 0]).replace('    hartland.er.entity.return_request,\n', ''),
    'model/layouts/agent/agent_hartland.ttrg': base()['model/layouts/agent/agent_hartland.ttrg'].replace('model: er', 'model: db'),
  });
  assert.equal(r.status, 1, r.stderr + r.stdout);
  assert.deepEqual(differing(r), ['model/layouts/agent/agent_hartland.ttrg', 'model/layouts/returns_review.ttrg']);
});

test('C8 — authored text differs, a file is missing: exit 1, each listed; outside the scope is ignored', async () => {
  const r = await compare({
    'model/er/tests/er.test.mjs': "const EXPECTED = [\n  'returns_review', // Propose\n];\n",
    'generated/resolved-packages.json': null,
    'README.md': 'hartland, edited\n',
  });
  assert.equal(r.status, 1, r.stderr + r.stdout);
  assert.deepEqual(differing(r), ['generated/resolved-packages.json', 'model/er/tests/er.test.mjs']);
});

test('C9 — a live branch origin does not have: exit 2', async () => {
  const r = await compare({}, ['model/u/none']);
  assert.equal(r.status, 2, r.stderr + r.stdout);
  assert.match(r.stderr, /cannot fetch/);
});
