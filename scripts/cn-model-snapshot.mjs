// CN-P6 S6.2 — generated/model.tar.zst: the model the resolver's cn doors serve (`statement.*`, `assertion.*`,
// `definition.render`; cn contracts §4, A-CN-76).
//
// The doors read ONE path, `RESOLVER_CONCEPT_MODEL_PATH`: the estate's model tree, or a snapshot archive of it
// (ttr-snapshot's format — `snapshot.json` + `docs/<path>`, USTAR in zstd). They serve it only when its content id is
// the `modelSnapshotHash` the lexicon archive was compiled from: sha256 over every `.ttr` / `.ttrm` under model/, in
// bytewise path order, each as `<relative path> NUL <bytes> NUL` (ttr-lexicon-cli's `ModelContentId`, the resolver's
// `ConceptModelSource.contentId`). So this archive packs exactly those files, under their model/-relative paths, and
// rides the `hartland-lexicon` ConfigMap beside lexicon.tar.zst (generated/kustomization.yaml): one ConfigMap update
// swaps both files at once, and the pin never sees one without the other.
//
// No toolchain CLI writes a model snapshot (the lexicon build hashes model/ but packs only the lexicon), hence this
// script. The reader asks for a parseable `snapshot.json` and a `docs/` tree — nothing about the bytes — so freshness is
// judged on CONTENT: a write leaves an archive that already holds this content untouched, whatever zstd build packed
// it, and the regenerate job's `git status` reads it as current.
//
//     node scripts/cn-model-snapshot.mjs           # write generated/model.tar.zst (untouched when already current)
//     node scripts/cn-model-snapshot.mjs --check   # exit 3 when stale or absent, or when the lexicon pins another model

import { createHash } from 'node:crypto';
import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { constants, zstdCompressSync, zstdDecompressSync } from 'node:zlib';

export const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const modelRoot = path.join(repoRoot, 'model');
export const snapshotPath = path.join(repoRoot, 'generated', 'model.tar.zst');
const lexiconPath = path.join(repoRoot, 'generated', 'lexicon.tar.zst');

const PRODUCED_BY = 'ttr-demo scripts/cn-model-snapshot.mjs';
const bytewise = (a, b) => Buffer.compare(Buffer.from(a, 'utf-8'), Buffer.from(b, 'utf-8'));

/** Every `.ttr` / `.ttrm` under model/ → its bytes, keyed by the model/-relative path, in bytewise order. */
export function modelFiles(root = modelRoot) {
  const rels = readdirSync(root, { recursive: true, withFileTypes: true })
    .filter((d) => d.isFile() && /\.ttrm?$/.test(d.name))
    .map((d) => path.relative(root, path.join(d.parentPath, d.name)).split(path.sep).join('/'))
    .sort(bytewise);
  return new Map(rels.map((rel) => [rel, readFileSync(path.join(root, rel))]));
}

/** The lexicon build's `modelSnapshotHash` over [files]. */
export function contentId(files) {
  const hash = createHash('sha256');
  for (const [rel, bytes] of files) hash.update(Buffer.from(rel, 'utf-8')).update('\0').update(bytes).update('\0');
  return `sha256:${hash.digest('hex')}`;
}

/** `snapshot.json` — ttr-snapshot's `SnapshotManifest`, which takes no other key. */
export function manifest(id) {
  return JSON.stringify(
    { formatVersion: 1, kind: 'models', qnames: [], producedBy: PRODUCED_BY, resolvedFrom: { modelContentId: id } },
    null,
    2,
  );
}

// ── USTAR, as ttr-snapshot's SnapshotWriter lays it out: bytewise path order, mode 0644, uid = gid = 0, mtime 0 ──────
function header(name, size) {
  const h = Buffer.alloc(512);
  const put = (text, off, len) => h.write(text, off, len, 'utf-8');
  const octal = (n, len) => n.toString(8).padStart(len - 1, '0') + '\0';
  if (Buffer.byteLength(name) > 100) throw new Error(`tar: name over 100 bytes: ${name}`);
  put(name, 0, 100);
  put(octal(0o644, 8), 100, 8);
  put(octal(0, 8), 108, 8);
  put(octal(0, 8), 116, 8);
  put(octal(size, 12), 124, 12);
  put(octal(0, 12), 136, 12);
  put('        ', 148, 8);
  put('0', 156, 1);
  put('ustar\0', 257, 6);
  put('00', 263, 2);
  const sum = h.reduce((a, b) => a + b, 0);
  put(sum.toString(8).padStart(6, '0') + '\0 ', 148, 8);
  return h;
}

function tar(entries) {
  const blocks = [];
  for (const [name, bytes] of [...entries].sort(([a], [b]) => bytewise(a, b))) {
    blocks.push(header(name, bytes.length), bytes, Buffer.alloc((512 - (bytes.length % 512)) % 512));
  }
  blocks.push(Buffer.alloc(1024));
  return Buffer.concat(blocks);
}

/** The members of a plain USTAR archive, by name (regular files only). */
export function untar(buf) {
  const files = new Map();
  for (let off = 0; off + 512 <= buf.length; ) {
    const h = buf.subarray(off, off + 512);
    if (h.every((b) => b === 0)) break;
    const field = (start, len) => h.subarray(start, start + len).toString('utf-8').replace(/\0.*$/s, '');
    const name = [field(345, 155), field(0, 100)].filter(Boolean).join('/');
    const size = parseInt(field(124, 12).trim() || '0', 8);
    const type = field(156, 1);
    off += 512;
    if (type === '0' || type === '') files.set(name, buf.subarray(off, off + size));
    off += Math.ceil(size / 512) * 512;
  }
  return files;
}

/** An archive's `snapshot.json` text and its `docs/` tree; null when there is none, `{ unreadable }` when it is not one. */
export function readSnapshot(file = snapshotPath) {
  if (!existsSync(file)) return null;
  let members;
  try {
    members = untar(zstdDecompressSync(readFileSync(file)));
  } catch (e) {
    return { unreadable: e.message };
  }
  const docs = new Map(
    [...members].filter(([k]) => k.startsWith('docs/')).map(([k, v]) => [k.slice('docs/'.length), v]),
  );
  return { manifest: members.get('snapshot.json')?.toString('utf-8') ?? null, docs };
}

/** The `modelSnapshotHash` the committed lexicon archive was compiled against. */
export function lexiconPin(file = lexiconPath) {
  const lexicon = JSON.parse(untar(zstdDecompressSync(readFileSync(file))).get('docs/lexicon.json').toString('utf-8'));
  return lexicon.header.modelSnapshotHash;
}

/** Why [snap] does not hold [files] (empty when it does). */
export function differences(snap, files) {
  if (!snap) return ['generated/model.tar.zst is absent'];
  if (snap.unreadable) return [`generated/model.tar.zst is not a zstd archive (${snap.unreadable})`];
  const why = [];
  if (snap.manifest !== manifest(contentId(files))) why.push('snapshot.json differs (another model content id)');
  for (const [rel, bytes] of files) {
    if (!snap.docs.has(rel)) why.push(`missing ${rel}`);
    else if (!snap.docs.get(rel).equals(bytes)) why.push(`changed ${rel}`);
  }
  for (const rel of snap.docs.keys()) if (!files.has(rel)) why.push(`not in model/: ${rel}`);
  return why;
}

function main(args) {
  const files = modelFiles();
  const id = contentId(files);
  let pin = null;
  try {
    if (existsSync(lexiconPath)) pin = lexiconPin();
  } catch (e) {
    pin = `unreadable (${e.message})`;
  }
  const stale = differences(readSnapshot(), files);
  if (args.includes('--check')) {
    const problems = [...stale];
    if (pin !== id) problems.push(`generated/lexicon.tar.zst pins ${pin}, model/ is ${id} — just build-lexicon`);
    if (problems.length > 0) {
      console.error(`cn-model-snapshot: stale —\n  ${problems.join('\n  ')}\n(just build-lexicon writes both archives)`);
      process.exit(3);
    }
    console.log(`cn-model-snapshot: current — ${files.size} files, ${id}`);
    return;
  }
  if (stale.length === 0) {
    console.log(`cn-model-snapshot: current — ${files.size} files, ${id}`);
  } else {
    const entries = new Map([['snapshot.json', Buffer.from(manifest(id), 'utf-8')]]);
    for (const [rel, bytes] of files) entries.set(`docs/${rel}`, bytes);
    const packed = zstdCompressSync(tar(entries), {
      params: { [constants.ZSTD_c_compressionLevel]: 19, [constants.ZSTD_c_checksumFlag]: 0 },
    });
    writeFileSync(snapshotPath, packed);
    console.log(`cn-model-snapshot: wrote generated/model.tar.zst — ${files.size} files, ${packed.length} bytes, ${id}`);
  }
  if (pin !== null && pin !== id) console.warn(`cn-model-snapshot: ⚠ generated/lexicon.tar.zst pins ${pin} — rebuild it`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main(process.argv.slice(2));
