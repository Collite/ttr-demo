# `lexicon/` — hartland's declared lexicon area (RV-36)

The **root-level data area**: alias/value files, grounding trigger files and skill files that
compile into the estate's lexicon archive. Added at RV-P3.2.

This is **one of two surfaces of one DECLARED layer**, not a second area. The other is
`model/lexicon/{cs,en}/*.ttrm` — the TTR-M `def term` sugar Stage 2.5 authored. They sit at
different levels, never collide as paths, and both compile into the same entry table. Neither
gets renamed.

```
lexicon/
├── aliases/hartland.lex.yaml     the estate's MEASURE vocabulary, er-targeted
├── grounding/hartland.lex.yaml   estate additions to the chrono/money/geo trigger vocabulary
├── tests/area.test.mjs           structural guards (node --test, no dependencies)
└── README.md
```

> ⚑ **`aliases/` and `values/` were REMOVED 2026-08-10 (Bora), and so were the md halves of the
> sugar surface** (`model/lexicon/{cs,en}/measures.ttrm` + `examples.ttrm`; `channels.ttrm` stays,
> its targets are `er.entity.*`). Every one of those rows targeted **`md.`**, and md vocabulary is
> not usable in its current form: the merged Golem's query door renders a bound ref into a
> TransDSL data object, and an `md.` ref names neither an object nor an aggregation — the Veles
> `ModelBundle` carries no md layer to resolve it against, so such a question is refused by name
> rather than answered (kantheon RV-P6.5, ruling B). **md gets its own exercise**; when it lands,
> this vocabulary comes back with a binding behind it. Nothing about the `model/md/` model itself
> changed — only the words pointed at it.
>
> ⛑ **`aliases/` came back 2026-08-13 — er-targeted, not md.** The removal above was right and
> is not undone; what it left behind was an estate with **no measure vocabulary at all**, which
> the hartland demo hit head-on: *"What are the marketplace revenues for 2025 by month?"* answered
> `I don't recognise "the marketplace revenues"`, because `marketplace` and `month` both resolved
> and `revenue` matched nothing in any form. The new file declares the same words against
> **`er.entity.<entity>.<attribute>`** — the shape `TransDslRenderer` can address without a
> metadata lookup, and which it SUMs for a `FRAME_ROLE_MEASURE`. `values/` is **not** restored:
> its rows were md members, and the er-side equivalent is a filter story, not a vocabulary one.
>
> ⚠ **Bare measure words are deliberately absent, and the compiler is why.** On the er layer
> `revenue` is three attributes on three entities. Declaring it three times — the honest shape,
> meant to raise a `G2_AMBIGUOUS` "which channel?" — is rejected: `RG-LEX-006`, *"Two targets for
> one term in one file have no defined winner"*, 38 violations and no archive written. The
> declared layer is single-target-per-term by construction, so bare words stay undeclared rather
> than being pointed at an arbitrary channel. Every corpus question that uses one is cross-channel
> anyway, which the door refuses regardless ("spans more than one object"), so those stay on the
> pattern path in `model/queries/q_hartland.ttrm` exactly as before. Restoring them on the fast
> path is an md exercise or a channel-labelled-view modelling exercise — not a lexicon change.
>
> ✅ **The modelling exercise landed 2026-09-24.** `er.entity.channel_sales` is backed by the view
> `data/views/channel_sales.sql` (UNION ALL of the three facts, channel as a column), so the bare
> words have ONE target: `revenue`/`tržby`/`obrat` → `channel_sales.ext_sales_price`,
> `channel`/`kanál*` → `channel_sales.channel` (`aliases/hartland.lex.yaml`). *"Revenue by channel
> for 2025 by month"* now binds on the fast path; the channel-qualified rows keep their
> single-channel targets, and the curated patterns stay for what the fast path cannot do.

Each data file's own header carries its sourcing — which line of `design/demo-transcript.md`,
which `search { patterns }` block in `model/queries/q_hartland.ttrm`, which
`example_questions` roster a term came from — plus the terms it deliberately does **not**
declare, and why. Read those before adding a word.

Build it with `just build-lexicon`; `just check-lexicon` fails when the committed archive is
stale. Both need the sibling tatrman checkout's Kotlin CLI — see the recipes for the `cli=`
override.

## Why the archive is committed

`generated/lexicon.tar.zst` is compressed binary, which is not the usual thing to put in a repo.
It is committed anyway, for two reasons that outweigh it at this size:

- **`--check` is only a gate if there is something committed to check.** Without the artifact in
  the tree, `just check-lexicon` on a fresh clone has nothing to compare against and the drift
  gate is decoration.
- **`resolved-packages.json` set the precedent**, and the reviewable part of this artifact is not
  its bytes but its **id** and per-class counts, both printed by the build and recorded below.

It measured **9,594 bytes** at the counts below. If it grows past roughly a hundred kilobytes the
trade flips and the archive should move to a CI-built artifact — the drift gate would then be a CI
step rather than a local recipe.

## What is in the artifact today

From `just build-lexicon`, **2026-10-09**: the „obrat z …“ channel phrases. Built with the **pinned**
toolchain `grammar/v0.13.7`:

| | |
|---|---|
| archive id | `sha256:29b01c5337057ac46f46005fa458650b576e66fa3df87d3a27d82316860ee97e` |
| model id | `sha256:5ebf54ceb6517e84e4ea438ac45586aa47cde0d99dc35ddfd9e470f936b58dca` (unchanged) |
| schema | `ttr-lexicon-compiled/v5` |
| toolchain | `Collite/ttr-core` **`grammar/v0.13.7`** (= `efd99dd`) |
| entries | **509** (was 503) |
| — `MODEL_OBJECT` | 178 (94 DECLARED, 84 METADATA) |
| — `MEMBER` | 100 |
| — `OPERATOR` | 35 |
| — `GROUNDING_TRIGGER` | 98 |
| — `STRING_PREDICATE` | 98 |
| build warnings | **4** (1 `RG-LEXC-002`, 3 `RG-LEXC-004`), the same four master's archive builds with |
| targets | 50 |
| size | 10,575 bytes |

Six DECLARED rows, TOKENS, one per channel measure: `obrat z tržiště` / `obratu z tržiště` →
`catalog_sales.ext_sales_price`, and the same for `z webu` (`web_sales`) and `z prodejen`
(`store_sales`). The demo script's synonym question *„Obrat z tržiště po čtvrtletích v roce 2025“* bound
the bare `obrat` (→ all channels, `channel_sales`) and left `tržiště` with no role, so it answered all
three channels as the marketplace's figure. The channel-qualified phrase is the longer span and wins.

⚠ **The archive in master before this change was not recorded.** #49 (`channel_sales.warehouse_sk`)
rebuilt it as `sha256:d3d35f7043c229d47fa52b8fff06907fba5e30901786ff5e70f7473933c20a46`, 503 entries over
the same model id. Rebuilding master's sources with the pinned toolchain reproduces it byte for byte.

### 2026-09-28

From `just build-lexicon`, **2026-09-28**: member vocabularies on four more name attributes. Built
with the **pinned** toolchain `grammar/v0.13.7`, the `ref:` in `.github/workflows/model-gate.yml`:

| | |
|---|---|
| archive id | `sha256:87b447260095ca40506499edc2aca4482a936310523711f4b12562add2d919e0` |
| model id | `sha256:93cdbca3ffa73fe247e32de7b0cbbbc5fbfcbe00ccaf5c4ce84c4f4bba7f0373` |
| schema | `ttr-lexicon-compiled/v5` |
| toolchain | `Collite/ttr-core` **`grammar/v0.13.7`** (= `efd99dd`) |
| entries | **491** (unchanged) |
| — `MODEL_OBJECT` | 160 (87 DECLARED, 73 METADATA) |
| — `MEMBER` | 100 (0 DECLARED, 100 METADATA `valueLabels`) |
| — `OPERATOR` | 35 |
| — `GROUNDING_TRIGGER` | 98 |
| — `STRING_PREDICATE` | 98 |
| build warnings | **2** (both `RG-LEXC-004`, as before) |
| targets | **46** (was 42), 15 with a mention facet |
| targets with a member vocabulary | **8** (was 4) |
| size | 10,335 bytes |

**No entry changed.** A member vocabulary is not an entry: it is the `memberVocabulary` flag on the
attribute's target. The lexicon matcher then loads that attribute's values from the warehouse, and
the resolver registers the attribute as a place a value can be looked up. Four name attributes now
declare `search { searchable method: TOKENS }`, so each becomes a target of its own:

```
er.entity.item.product_name        TOKENS   18 000 rows, 17 952 names (the bilingual catalogue)
er.entity.warehouse.warehouse_name TOKENS   5   (Memphis DC, Columbus DC, …)
er.entity.reason.reason_desc       TOKENS   35  (Found a better price, …)
er.entity.call_center.name         TOKENS   3   (NY Metro, Mid Atlantic, North Midwest)
—— unchanged ——
er.entity.store.store_name         TYPOS(1) 6
er.entity.store.state · warehouse.state · customer_address.state   EXACT
```

TOKENS because a name is several words and a user types one: «Memphis» finds `Memphis DC`, and
products «Voltaic» finds every `Voltaic …`. `store_name` stays TYPOS(1): each store name is a
single city word. Two name heads are deliberately left out:

- **`promotion.promo_name`** still holds the benchmark's generated syllables. Its 10 values over
  300 rows include `able`, `bar` and `ought`, which are ordinary English words and would become
  members.
- **`customer_address.city`** has 695 cities over 50 000 addresses. Several are also store or
  warehouse names (`Franklin`, `Memphis`), and a place-shaped span is claimed as a place before any
  vocabulary sees it
  ([ttr-server#118](https://github.com/Collite/ttr-server/issues/118)).

⚠ **The archive in master before this change was never recorded either.** The toolchain bump to
`grammar/v0.13.7` (#39) rebuilt it as `sha256:2012d23af9176d14067ace86c038acf4c7eba47235437594c7073c9e37642f03`
(reproduced byte-for-byte from a clean export of `62b9e09`) and left the 2026-09-24 table below in
place.

### Previously (2026-09-24, LP-P3·T1 — the mention facet on seven more heads)

From `just build-lexicon`, **2026-09-24** (LP-P3·T1 — the mention facet on seven more heads),
built with the **pinned** toolchain `grammar/v0.13.5`, which is what `.github/workflows/model-gate.yml`
checks out and what the serving images were built against:

| | |
|---|---|
| archive id | `sha256:b5c5290eed8fb8c709dd621162fc82903853cb37575e2fd5870759ac78d3fb43` |
| model id | `sha256:18230c666eb104e54d98854a7cbe44c5ee24a3e2036652c33ad7478169038fc4` |
| schema | `ttr-lexicon-compiled/v4` |
| toolchain | `Collite/ttr-core` **`grammar/v0.13.5`** (= `9bbec48f`) |
| entries | **427** |
| — `MODEL_OBJECT` | 160 (87 DECLARED, 73 METADATA) |
| — `MEMBER` | **100** (0 DECLARED, 100 METADATA `valueLabels`) |
| — `OPERATOR` | 35 (the six stdlib operators' triggers) |
| — `GROUNDING_TRIGGER` | 98 (72 stdlib + 26 from `grounding/hartland.lex.yaml`) |
| — `STRING_PREDICATE` | **34** (the LP-P2a `pred:` stdlib slice — all five refs, cs + en) |
| operators | 6 |
| build warnings | **2** (both `RG-LEXC-004`, MH T1 — see below) |
| md-targeted rows | **100, all `METADATA`** |
| targets with a mention facet | **8 of 38** (was 1) |
| size | 9,594 bytes |

**No entry of LP's changed.** The 9 rows added since the last table are PR #35's
(`"units sold"` → `channel_sales.quantity`, `"category"` → `item.category`); what LP moved is the
**`targets` map**, which since schema v4 carries `nameRef`/`codeRef`/`codeFormat` per target. Seven
more heads now declare `semantics { name: · code: }` and so become somewhere a quoted literal can
attribute to (LP contracts §2.1):

```
er.entity.call_center       name | call_center_id
er.entity.customer          —    | customer_id      (code only: no name column in this cut)
er.entity.customer_address  city | address_id
er.entity.item              product_name | item_id
er.entity.promotion         promo_name   | promo_id
er.entity.reason            reason_desc  | reason_id
er.entity.store             store_name   | store_id  (MS, already there)
er.entity.warehouse         warehouse_name | warehouse_id
```

⚑ **That is every eligible hartland head.** Of the 30 targets still without a facet, 12 are
attributes and measures (a member has no name column — it IS one, `Mention.NONE` by
construction), 8 are facts (`entity_with_measures` — a fact is not a thing you name), 3 declare
neither a name nor a code (`customer_demographics`, `household_demographics`, `income_band`), and
`date_dim`'s name is a date and its code the internal sequence key, so attributing a typed string
to either would be wrong. The remaining **6 are the investment area** (`asset`, `client`,
`portfolio`, `position`, `price`, `transaction`), which is **not authored here** —
`model/investment/` is synced out of kantheon (`just sync-investment-model`), so its facet is a
change in that repo.

⚠ **The previous archive was never recorded.** `7fc8c36` (*"lexicon: rebuild with the current CLI
— 418 entries incl. LP-P2a STRING_PREDICATE"*) shipped archive
`sha256:0b620056587414f3c99f13d5069e409b15f908fe808828dd472de181c71d2325` over model
`sha256:ea15b2b776faa3de411a1c1159b4cee9a10a45c9f944fd4007a5c1b73e0f22f3`, and left the 2026-09-04
table below in place — so between then and now the table described neither the archive in the tree
nor the one on the cluster. The rule in *Adding a word* step 5 is the one that was missed; this
table is a fact about the estate only if it is rewritten with the archive.

⚑ And the id moves on **comments**, not only on vocabulary: every `METADATA` row records the line
it was harvested from, so inserting a four-line note above an entity shifts its provenance and the
archive id with it. `just check-lexicon` is therefore a real gate on any `model/` edit, including
one that changes no words at all.

⛔ **The id also moves on the TOOLCHAIN, and that is the one that has bitten this repo twice.** PRs
#35 and #36 landed within four minutes of each other; #35 rebuilt the archive, #36's merge resolved
the binary conflict by keeping master's copy, and the estate then served a model whose facets were
in the `.ttrm` files and not in the artifact anyone reads. Nothing was wrong on either branch — the
gate that would have caught it is the one that runs on the MERGE RESULT, and by then ttr-core master
had also moved to a `v5` compiler, so the gate was failing for a second, unrelated reason and its
red told nobody anything.

Two rules come out of it, and they are why `model-gate.yml` now pins `ref: grammar/v0.13.5`:

1. **`generated/` is a build output with a source, so never resolve a conflict in it by picking a
   side.** Take either, then rebuild and re-record — the bytes are not reviewable, so "ours" and
   "theirs" are both guesses.
2. **The toolchain is an input to the id.** Pin it to the tag the serving images were built
   against, bump it in the change that rolls the readers, and rebuild in that same commit. An
   unpinned compiler turns a drift gate into a rumour about someone else's repository.

### Previously (2026-09-04, on the toolchain's provenance-path fix)

From `just build-lexicon`:

| | |
|---|---|
| archive id | `sha256:1f5466535cd161f799d39853a5313544ebd39dfe58207753b287ad0113b643ec` |
| model id | `sha256:588f17662890d74e5c6ed594834a7889588af86badc62fa3ebe7414f5776378f` |
| entries | **351** |
| — `MODEL_OBJECT` | 118 (66 DECLARED, 52 METADATA) |
| — `MEMBER` | **100** (0 DECLARED, 100 METADATA `valueLabels`) |
| — `OPERATOR` | 35 (the six stdlib operators' triggers) |
| — `GROUNDING_TRIGGER` | 98 (72 stdlib + 26 from `grounding/hartland.lex.yaml`) |
| operators | 6 |
| build warnings | **2** (both `RG-LEXC-004`, MH T1 — see below) |
| md-targeted rows | **100, all `METADATA`** |

**No vocabulary changed.** The entry table is byte-identical to the previous archive once
`provenance` is set aside; 52 rows — every `METADATA` row harvested from `model/er/*.ttrm` —
recorded the **builder's absolute path** and now record a repo-relative one:

```
- { "file": "/Users/…/collite-gh/hartland-mh/model/er/parties.ttrm", "line": 0 }
+ { "file": "model/er/parties.ttrm",                                 "line": 0 }
```

That path is inside the entry table, inside `sourceHashes.metadata`, and inside the compiler's
merge precedence, so the archive id depended on **where the repo was checked out**. Measured on
this commit with the pre-fix toolchain: `2d570ada…` from `collite-gh/hartland`, `4610e831…` from
a second worktree of the same SHA — and the committed archive still carried `hartland-mh/` paths
from whichever worktree last rebuilt it. `just check-lexicon` therefore failed on a clean master
for anyone whose clone sat anywhere else, which is the drift gate reporting the filesystem rather
than the vocabulary. With the fix both paths compile to the id above. Toolchain side:
`Collite/ttr-core` — `MetadataExtractor` now spells the model tier's provenance relative to the
estate root, the way every other layer already did.

⚑ **The two `RG-LEXC-004` warnings are not new here** and are not a regression: `prodejna` and
`stores` are each claimed by both `er.entity.store_sales` (declared) and `er.entity.store`
(metadata anchor). MH T1 added the warning; the collision predates it, and it is the MH resolver's
business to decide, not the compiler's. The table below recorded `0` because it was written
before that code existed.

### Previously (2026-08-13, after `aliases/` returned, er-targeted)

> ⚠ Neither id below matches what was actually committed on master: the archive in the tree at
> that point was `a2617910…` over model `588f1766…`. Two causes, and the first is why this file
> keeps drifting — the recorded id was path-dependent, so it described the machine that ran the
> build as much as the vocabulary; MH-P2 then rebuilt the archive without re-recording here.
> With the path out of the id, an entry in this table is finally a fact about the estate.

| | |
|---|---|
| archive id | `sha256:15fb55aeb2615b2a505e57bafc5d475fe4df7f60b0d1343d9d09a16c320a594c` |
| model id | `sha256:07cfb8bf74cc7f62b7c034e4034517c96c1c217250cb6cc6b1f5c8e5377d0e68` |
| entries | **351** |
| — `MODEL_OBJECT` | 118 (66 DECLARED, 52 METADATA) |
| — `MEMBER` | **100** (0 DECLARED, 100 METADATA `valueLabels`) |
| — `OPERATOR` | 35 (the six stdlib operators' triggers) |
| — `GROUNDING_TRIGGER` | 98 (72 stdlib + 26 from `grounding/hartland.lex.yaml`) |
| operators | 6 |
| build warnings | **0** |
| md-targeted rows | **100, all `METADATA`** |

**What changed on 2026-08-13**: `aliases/hartland.lex.yaml` returned with **44 DECLARED rows** at
`er.` attribute depth — **13** revenue forms across the three channel entities (cs + en,
channel-qualified), **12** stock-on-hand forms on `er.entity.inventory`, and **19** calendar-grain
forms on `er.entity.date_dim.{month,year,quarter,week_seq}`. Nothing md-targeted came back; the
100 harvested `MEMBER` rows are untouched.

The calendar rows are the RV-P6.6 half. Before them, *"…by month"* stopped at a `ground:chrono`
trigger, which names no column — so the query door had nothing to group by and refused every
dated question. They are **grain phrases** (`by month`, `měsíčně`, `monthly`), not the bare nouns:
declaring bare `month` alongside its chrono trigger would be legal but would put two classes in
competition on one span. Verified in the artifact — no term lands in both `ground:chrono` and a
`date_dim` column.

⚑ Grouping by a calendar column means a question now spans **two entities**, which the door
refused outright until RV-P6.6 taught it to check the model for a direct relation
(`rel_catalog_sales_date` and siblings) and let `EXPAND_JOINS-logical` insert the join.

> ⚠ **This table had drifted, and the drift is worth reading before the numbers.** Both the
> `312`/`79` row and the model id above described 2026-08-10; the artifact actually committed and
> deployed since `492f892` (*"queries back and descriptions v02"*) carried **307 entries,
> `MODEL_OBJECT` 74, model id `07cfb8bf…`** — that commit changed the model and rebuilt the
> archive without re-recording either here. So this change's real delta is **307 → 332** and
> `MODEL_OBJECT` **74 → 99**, and the model id moved before this edit, not because of it. Read
> the archive id as the drift gate; `just check-lexicon` is what enforces it, and it is the gate
> that would have caught the stale table had it been run.

### Previously (2026-08-10, after the md removal)

| | |
|---|---|
| archive id | `sha256:27f46856dd0e52e3527e8cfa71df813766b9d734083a4a952338ca674a4229ab` |
| model id | `sha256:de06296473acbbcb89bd7dc59f05bf0bb5c97d5e329aa0dd88e24151f94ebef8` |
| entries | **312** |
| — `MODEL_OBJECT` | 79 (22 DECLARED, 57 METADATA) |
| — `MEMBER` | **100** (0 DECLARED, 100 METADATA `valueLabels`) |
| — `OPERATOR` | 35 (the six stdlib operators' triggers) |
| — `GROUNDING_TRIGGER` | 98 (72 stdlib + 26 from `grounding/hartland.lex.yaml`) |
| operators | 6 |
| build warnings | **0** |
| md-targeted rows | **100, all `METADATA`** |

⚠ **The last row is the one to read.** Removing the files removed every **DECLARED** md row (111
of them). The 100 that remain are **harvested**, not authored: the compiler's metadata pass reads
`valueLabels` off `model/md/{dimensions,product}.ttrm` and emits a MEMBER row per label per
locale. They go when the md model does, which is the separate exercise — deleting them here would
mean deleting the model, not the vocabulary.

### Previously (2026-08-06, before the md removal)

From `just build-lexicon` after RV-P3.2 T4 authored the alias/value area:

| | |
|---|---|
| archive id | `sha256:2f1d28e1004da7f7c397f34b76482c7d2c54728751dec8ed10772341d8f560b3` |
| model id | `sha256:e434903b86466236149298b49039122ed307e701ba113c93ef46de4a838ddabf` |
| entries | **423** |
| — `MODEL_OBJECT` | 178 (121 DECLARED, 57 METADATA) |
| — `MEMBER` | **112** (12 DECLARED, 100 METADATA `valueLabels`) |
| — `OPERATOR` | 35 (the six stdlib operators' triggers) |
| — `GROUNDING_TRIGGER` | 98 (72 stdlib + 26 from `grounding/hartland.lex.yaml`) |
| operators | 6 |
| build warnings | **0** |
| md-targeted rows | 211 |

Those numbers are what `p3-3` verifies a pod is actually serving.

**What changed at RV-P3.2 T4** (was: 350 entries, MODEL_OBJECT 117, MEMBER 100): `aliases/` and
`values/` were authored, adding **73 rows** — 61 objects and 12 members. The vocabulary that
arrived is the half the `.ttrm` sugar surface never covered: orders and quantities, the Customer,
Promotion and ReturnReason dimensions, the category/state/age attributes the demo slices by, the
inventory cubelet, and the five distribution centres by bare name.

**What changed at RV-P3.4** (was: 212 entries, MEMBER 0, 38 warnings): the compiler's reference
index learned md, so the estate's measure and dimension vocabulary — *tržba*, *obrat*, *revenue*,
*turnover*, *reklamace*, *vyprodáno*, *produkt*, *sklad* — resolves instead of dangling, and every
`valueLabels` entry on an md dimension attribute (the DC names, the 35 return reasons) becomes a
MEMBER row. All 38 dangling-ref warnings are gone.

⚑ **The target shape is kinded**: `md.measure.revenue`, `md.dimension.Product`, attribute depth
`md.dimension.Customer.state`, member depth `md.dimension.DistributionCentre.dcCode.5`. Addressable
kinds are **measure, dimension (+ attribute/member depth), cubelet**; `domain`, `hierarchy` and
`map` deliberately are not. A ref in any other shape drops its row with a warning and the build
still exits 0 — so read the warning count, not just the exit code.

## Adding a word

1. Check it is not already declared — `model/lexicon/{cs,en}/*.ttrm` is the other surface of the
   same layer, and `just verify-model`'s T4 guard fails the build if you restate one of its forms.
2. Put it in the file that matches what it names: `aliases/` for an object, `values/` for a member
   code, `grounding/` for a chrono/money/geo trigger.
3. Name the corpus line it came from in the block comment. Every term in this area is attested in
   `design/demo-transcript.md`, `model/queries/q_hartland.ttrm`, a Shem's `example_questions` or
   `data/recon/R0.md` — that discipline is what keeps the estate's vocabulary the users' and not
   the author's.
4. Watch the method. Short codes and proper nouns take `EXACT` (a one-edit neighbourhood around a
   short name reaches its siblings — this estate has both `Brno` and `Reno` as distribution
   centres); anything at or below three characters cannot fire `typos` at all (⚑M-4).
5. `just build-lexicon`, then re-record the id and counts above. **Read the warning count**, and
   commit the rebuilt archive with the change.
