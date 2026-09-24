// Shared project-load harness for the Stage 2.x mocked unit-test suites (no live DB).
// Parses every model/*.ttrm under the hartland repo root as ONE project, loads the
// cnc-roles stock vocab, and runs the full semantics + lint pipeline — the same
// machinery tatrman's own `tests/integration/src/integration.test.ts` uses
// (`collectFixtureCodes`), adapted to point at this repo instead of tatrman's samples/.
//
// Borrows the sibling tatrman checkout's built dist (BM-9: hartland stays content-only,
// no node_modules of its own).

import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
export const hartlandRoot = path.resolve(here, '../..');

/**
 * True for a file this repo AUTHORS, false for one synced in from another repository.
 *
 * ⛔ IE-P2·S2.3. Until the investment package landed under `model/investment/` this distinction did
 * not exist, and the suites below were written in a world where "every definition in the project"
 * and "every definition hartland declares" were the same sentence. They are not any more: veles
 * serves this tree, so a second package lives in it, and four assertions that read as rosters —
 * *the 19 D-5 entities*, *ListQueries = 15* — silently became project-wide counts that a sync
 * could move. A roster must count what it names.
 *
 * Scoped by PATH rather than by `package` declaration on purpose: the synced tree is identified by
 * where the sync puts it, and a file that arrived here by mistake declaring `package hartland`
 * should still be excluded from hartland's own roster and caught by the sync's suite instead.
 */
export const isOwnModelFile = (uri) => !uri.includes('model/investment/');

/** The synced package's own files — the other half of [isOwnModelFile], so both sides are checked. */
export const isSyncedModelFile = (uri) => uri.includes('model/investment/');

// Diagnostics every stage's project-wide sweep should treat as expected, not a failure —
// centralized here so a later stage adding a new accepted residual doesn't silently break
// an earlier stage's test (each entry says which stage introduced it and why).
export const ACCEPTED_RESIDUAL_CODES = new Set([
  // Stage 2.2: the BM-9 kind-directory tree + one flat `package hartland` (no imports
  // needed anywhere) — see modeler.toml's [packages] comment. Non-suppressible by design,
  // doesn't block resolution (verified: zero ttr/unresolved-reference project-wide).
  'ttr/package-prefix-divergence',
  // Stage 2.2: def area hartland's explicit `entities:` is redundant with its recursive
  // `packages:` closure — intentional, for readability (info-level).
  'ttr/area-redundant-member',
  // Stage 2.3/2.4: `md/table-map-no-binding` is `scope: 'document'` (packages/lint/src/
  // rules/md.ts) — it only looks for an `md2db_map` in the SAME file as the `def map`.
  // Stage 2.4 DOES bind all 4 Product table-maps (model/binding/md2db.ttrm), just in a
  // different file than model/md/product.ttrm — a known cross-file linter limitation
  // (the rule's own docstring: "Phase 3 refines cross-file"), not an actual binding gap.
  // Real completeness is checked directly in md.test.mjs T6.1 against the AST, not via
  // this diagnostic.
  // Stage 2.3: Product's 4 table-backed maps have no md2db_map yet — that's Stage 2.4.
  'md/table-map-no-binding',
  // MS (mention semantics, vocabulary v3): TTR-SEM-218 `SemLegacyMentionDeprecated` — the
  // model declares `nameAttribute:`/`codeAttribute:`, whose replacement is the entity
  // `semantics { name:, code: }` mention facet. Warning-level by ruling (MS-D2): a
  // deprecation is advice about style, not a defect. It fires on five files here and is
  // ACCEPTED rather than fixed, deliberately — READERS BEFORE PRODUCERS. Veles reads the
  // semantics mention keys only from MS-P2 on; dropping the legacy properties while the
  // serving estate still runs an older veles would blank EntityDetail.name_attribute for
  // every dimension at once, silently. Seven heads now declare BOTH — `store` (MS) and the
  // six LP-P3·T1 added: `item`, `promotion`, `call_center`, `warehouse`, `customer_address`,
  // `reason` (plus `customer`, code only, which has no name attribute to point at). That is
  // the intended migration step; declaring the facet does not ADD a 218, only dropping the
  // legacy property beside it would clear one.
  // Remove this entry — and the legacy properties — once hartland's veles is on an MS-P2
  // image and the chain has been seen serving name/code from the semantics block.
  'TTR-SEM-218',
  // IE-P2·S2.3 (kantheon's S2.2 found the same pair, and accepted it for the same reason):
  // RS-32 moved pattern discovery onto lexicon `term` entries, so `search { patterns: …,
  // examples: … }` on a `def query` now raises `ttr/lexicon-legacy-patterns` /
  // `-legacy-examples`. Both fire on `model/queries/q_hartland.ttrm` — which is why this
  // repo's model gate has been RED on master since the toolchain bump, 8 assertions across
  // 4 files — and on the synced `model/investment/queries/q_investment.ttrm` beside it.
  //
  // ACCEPTED, not fixed, and READERS BEFORE PRODUCERS is again the reason: the running
  // veles and golem on hartland discover a pattern query through `search`, and moving the
  // patterns to lexicon terms would take every q.hartland.* out of discovery at once, on an
  // estate that is the live demo. The migration is a stage of its own, with the image bump
  // in it. Remove this entry when the patterns move.
  'ttr/lexicon-legacy-patterns',
  'ttr/lexicon-legacy-examples',
]);
// The sibling checkout by default. `TATRMAN_PACKAGES` overrides it so this suite can be
// run against a tatrman WORKTREE — needed whenever the model uses grammar the sibling's
// built dist does not have yet (NLS-P10: the localised `description:` form is 0.13).
const tatrmanPackages = process.env.TATRMAN_PACKAGES ?? path.resolve(hartlandRoot, '../tatrman/packages');

const { parseString } = await import(path.join(tatrmanPackages, 'parser/dist/index.js'));
const semantics = await import(path.join(tatrmanPackages, 'semantics/dist/index.js'));
const semanticsNodeOnly = await import(path.join(tatrmanPackages, 'semantics/dist/node-only.js'));
const lintMod = await import(path.join(tatrmanPackages, 'lint/dist/index.js'));

const {
  resolveManifest, parseManifest, ProjectSymbolTable, Resolver,
  PackageGraphBuilder, synthesizeMappings, effectivePackage,
  AreaTableBuilder,
} = semantics;
const { loadStockVocabularies } = semanticsNodeOnly;
const { lintDocument, lintProject, recommendedConfig } = lintMod;

async function walkTtrm(dir, excludeDirs = ['.schema-ref', 'node_modules', '.git']) {
  const out = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (excludeDirs.includes(entry.name)) continue;
      out.push(...await walkTtrm(path.join(dir, entry.name), excludeDirs));
    } else if (entry.isFile() && entry.name.endsWith('.ttrm')) {
      out.push(path.join(dir, entry.name));
    }
  }
  return out;
}

/**
 * Parse + resolve the whole hartland model/ tree as one project. Returns everything a
 * stage's T6 suite needs: per-file ASTs, per-file diagnostic codes, the symbol table,
 * resolver, package graph, area table, and manifest.
 */
export async function loadHartlandProject() {
  const root = hartlandRoot.endsWith('/') ? hartlandRoot : hartlandRoot + '/';
  const files = (await walkTtrm(path.join(hartlandRoot, 'model')));

  const manifestToml = await readFile(path.join(hartlandRoot, 'modeler.toml'), 'utf-8');
  const manifest = resolveManifest(parseManifest(manifestToml), root);

  const symbols = new ProjectSymbolTable();
  const asts = new Map(); // uri -> ast
  const areaEntries = [];

  // Stock vocab (fact/dimension/structural/master/transaction/bridge) — `roles: [...]`
  // on every er entity references this.
  const stockVocabs = await loadStockVocabularies(manifest.stockVocabularies);
  for (const [name, ast] of stockVocabs) {
    const uri = `stock://${name}.ttrm`;
    asts.set(uri, ast);
    symbols.upsertDocument(uri, ast, 'cnc', 'role', '');
  }

  const parseErrorsByFile = new Map(); // relative path -> [{code,message}]
  for (const file of files) {
    const uri = `file://${file}`;
    const result = parseString(await readFile(file, 'utf-8'), uri);
    parseErrorsByFile.set(path.relative(hartlandRoot, file), result.errors);
    if (!result.ast) continue;
    asts.set(uri, result.ast);
    symbols.upsertDocument(
      uri,
      result.ast,
      result.ast.modelDirective?.modelCode ?? 'db',
      result.ast.modelDirective?.schema ?? '',
      effectivePackage(result.ast, file, root, manifest.packages),
    );
    synthesizeMappings(symbols, uri, result.ast);
    for (const def of result.ast.definitions ?? []) {
      if (def.kind === 'area') areaEntries.push({ area: def, documentUri: uri });
    }
  }

  const resolver = new Resolver(symbols);
  const deps = { manifest, symbols, resolver };
  const packageGraph = new PackageGraphBuilder(symbols, asts).build();
  const config = recommendedConfig();
  const projectByUri = lintProject(asts, packageGraph, deps, config);

  const diagnosticsByFile = new Map(); // relative path -> Set(codes)
  for (const file of files) {
    const uri = `file://${file}`;
    const ast = asts.get(uri);
    if (!ast) continue;
    const codes = new Set();
    for (const d of lintDocument(uri, ast, deps, config)) codes.add(d.code);
    for (const d of projectByUri.get(uri) ?? []) codes.add(d.code);
    diagnosticsByFile.set(path.relative(hartlandRoot, file), codes);
  }

  const areaTable = new AreaTableBuilder(symbols, resolver, manifest.packages.root ?? '').build(areaEntries);

  return { root: hartlandRoot, files, asts, symbols, resolver, packageGraph, manifest, diagnosticsByFile, parseErrorsByFile, areaTable };
}
