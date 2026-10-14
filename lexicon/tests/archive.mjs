// The COMMITTED lexicon archive, decoded — what the lexicon suites (`store-family`, `grain-adjectives`)
// read. Not a suite itself: `just verify-model` runs `*.test.mjs` only.
//
// Why the archive and not the sources: what the matcher serves IS this file, and
// `just check-lexicon` (CI) proves it is what the sources compile to.

import { readFileSync } from 'node:fs';
import { zstdDecompressSync } from 'node:zlib';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
export const archivePath = path.join(repoRoot, 'generated', 'lexicon.tar.zst');

/** The members of a plain ustar archive (what the lexicon packer writes), by name. */
export function untar(buf) {
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

/** `docs/lexicon.json` from the committed archive: `{ header, entries, targets }`. */
export const lexicon = JSON.parse(untar(zstdDecompressSync(readFileSync(archivePath))).get('docs/lexicon.json').toString('utf-8'));

export const isCs = (e) => e.lang.split('|').includes('cs');
export const isEn = (e) => e.lang.split('|').includes('en');
