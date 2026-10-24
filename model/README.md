# model — the Hartland TTR-M model

One model set (BM-2/BM-5), served over `pg-hartland-us` (USD) and `pg-hartland-cz` (CZK).

- `db/` — `model db`: the physical TPC-DS subset (facts + used dims), types, PK/FK.
- `er/` — `model er` + `er2db` binding: the 19 curated entities + relationships (05-d/D-5).
  Plus one **logical query** (LQ, 2026-10-18): `er/customer_revenue.ttrm` declares `er.query.revenue_per_customer`
  (written over entities — `sales JOIN customer` — because it sits in a `model er` file) and the
  entity `customer_revenue` stacked on it (all-time totals, one row per customer), with `join:` relations to
  household demographics and customer. It is not a `q.hartland.*` pattern: agents are meant to ask over the
  entity (LQ-6). ⚑ veles 0.11.11 still LISTS it — ListQueries returns 18 (the 17 `q.hartland.*` + this one),
  and GetModel carries it in `namedQueries` — so meta-mcp `list_queries` offers it, and running it is refused
  (`query_ref_logical_query`). Its name is deliberately not the entity's: golem's descriptor lookup tries a
  query's local name before an entity's.
  And a second (BI-4, 2026-10-22): `er/stockouts.ttrm` declares `er.query.stockouts_monthly_dc` — stock-out weeks per
  distribution center per month, over `inventory JOIN warehouse JOIN date_dim` — and the entity `dc_stockout_month`
  stacked on it, related to its DC and to the calendar day its month starts on. Superset's "DC meltdown — stock-outs"
  dashboard reads it as `obj.query.stockouts_monthly_dc`. And `er/returns-by-category.ttrm`:
  `er.query.returns_monthly_by_category` (returns per item category per month, over the return family) with the entity
  `category_return_month` — the "Returns by category" dataset, BI's own (SO keeps `returns_review` on its demo branch).
  And a fourth (md/hop HP-H, 2026-10-24): `er/sales.ttrm` declares `er.query.sales_union` and the all-channel entity
  `sales` stacked on it (the `sales` design note below). ListQueries now returns 21.
  And two more (CN-P6 S6.1, 2026-10-24) — 23: `er/channel_returns.ttrm` (`er.query.returns_union`, the three returns
  facts as one entity — the ground of the conceptual `Return`; **not** conversational yet: no label, no measure facet,
  no term) and `er/placed_order.ttrm` (`er.query.placed_order_q` → `placed_order`, the phase `PlacedOrder` written as
  model text by `ttr cn materialize`).
- `cn/` — `model cn`: the conceptual package (CN-P6 S6.1 = AU-hartland P5 S5.1; design `11` §1): kinds, the role
  `Customer`, events, qualities, and the phases the recipes are written in (`PendingOrder`, `ShortLine`,
  `MispricedLine`, `DebtorCustomer`, …). Analytical concepts ground to md and reach er through the DERIVED hop — no
  md2er is authored (A-H-5) — the recipe world grounds to er; participant paths in `binding/cn.ttrm`, words in
  `lexicon/{cs,en}/cn.ttrm`. Its report is `just cn-hygiene` (over `model/` + `../automation/automation.ttrm`, whose
  parameters the parametric phases read), golden `cn/tests/hygiene.md`.
- `md/` — `model md` + `md2db`/`md2er` binding: the ROLAP star (cubelets, measures, conformed
  dimensions incl. the Product hierarchy Category→Class→Brand→Manufacturer→Item).
- `lexicon/` — `model lexicon locale en` + `locale cs`: the bilingual naming layer + valueLabels.
- `queries/` — the `q.hartland.*` preferred queries (#1–15, D-2).
- `binding/` — cross-model mapping: `er2db` (Stage 2.2) + `md2db` (Stage 2.4) `.ttrm` files.
- (`worlds/` moved to `../automation/worlds/` at AU P2: the world names the automation package's programs and roles,
  and veles and the lexicon build read `model/` alone — see the automation paragraph below.)
- `connections.toml` — the two connection descriptors (`pg-hartland-us`/`pg-hartland-cz`).
  **Not a TTR-M construct** (the grammar has no `connection` def and no per-connection
  currency `unit` — verified against `packages/grammar/src/TTR.g4`): this is a repo-level
  descriptor Ariadne/Arges consumes at deploy time (Phase 3, plan-cluster.md H3). Both
  connections point at the *same* physical model (`modeler.toml`'s `[schemas.dbo]` handle) —
  the two databases are schema-identical (Phase 1); currency is a display fact carried by
  the lexicon locale (Stage 2.5), not a structural difference. "Loads clean and resolves
  against both connections" (the Phase 2 DONE bar) therefore means: the one model parses
  and resolves clean, and both connection descriptors target the identical schema — the
  live per-world round-trip is Phase 3 H3, not a Phase 2 blocker.

**Verify:** `just verify-model` (mocked parse/resolution unit tests, no live DB) and
`just resolve-packages` / `just check-model` (the tatrman Modeler CLI's deterministic
`resolved-packages.json`, same tool `ai-models` uses) — both run from the repo root,
borrowing the sibling `tatrman` checkout's built toolchain rather than vendoring one here.

**Packaging (Stage 2.2 finding — read before adding a new model/*.ttrm file):** the BM-9
tree groups files by model kind (`db/`, `er/`, `md/`, ...), which would normally give each
subfolder its own directory-inferred package, forcing an `import` in nearly every
cross-kind binding. Instead, **every model/*.ttrm file declares `package hartland`
explicitly** (first line, after any file-level comment), collapsing the whole model into
one flat package — same-package refs (`db.dbo.*`, `er.entity.*`) need no import anywhere.
`modeler.toml`'s `[packages] layout = "off"` suppresses the resulting intentional
directory/declaration mismatch; verified this doesn't block resolution (zero
`ttr/unresolved-reference` project-wide). One residual, accepted, non-blocking diagnostic
remains on every file — `ttr/package-prefix-divergence` — documented in `modeler.toml`.
**Also:** `date` is a reserved grammar keyword — don't use it as a bare attribute name
(hit this on `date_dim`/`inventory`; used `cal_date`/`as_of_date` instead). Entity-level
`aliases:` is deprecated (`ttr/lexicon-legacy-aliases`) — declare a lexicon `term` instead
(Stage 2.5). New accepted-residual diagnostic codes go in
`model/tests/project-harness.mjs`'s `ACCEPTED_RESIDUAL_CODES` (shared across every stage's
test file, not copy-pasted per file).

**MD calendar (Stage 2.3 finding):** the v1 calc-map catalog (`docs/features/md/map-
catalog.md`) ships `yearOfDate` as an EXTRACTION straight from `Day`, not a `Quarter->Year`
ROLL-UP (no such entry ships in v1 — only `quarterOfMonth` does). So `model/md/calendar.ttrm`
declares **three** hierarchies sharing the `day` leaf (`calendarMonthly`: day→month→quarter,
`calendarYearly`: day→year, `calendarWeekly`: day→week) rather than one Day→Month→Quarter→Year
chain — the pattern `docs/manual/en/15-md-model.md`'s own hierarchy section sanctions ("a
second hierarchy sharing the day leaf"). The MD "dot-path" drill notation
(`product.electronics.<class>`) named in the Stage 2.3 task list is unimplemented design-stage
sugar (`docs/features/md/dot-path-sugar.md`: "brainstorm output... Not yet a contract") — the
mocked test suite checks hierarchy-level resolution through the real resolver instead.

**Full dimension binding (review follow-up, 2026-07-18):** every md dimension attribute now
has a physical binding, not just the grain keys + measures the wide cubelets carry. There is
no `md2db_dimension` construct, so each descriptive/analytic attribute is reached the same way
the Product hierarchy is: a table-backed `def map` (key→attribute) + an `md2db_map` to the dim
table (`store_to_name`, `dc_to_name`, `promo_to_name`, `reason_to_desc`, `item_to_name`, plus
`customer_to_birthyear`). `Customer.state` is the customer's HOME state, reached via a two-hop
`CustomerCode → AddressCode (c_current_addr_sk) → State (customer_address.ca_state)` chain
because an `md2db_map` targets a single table; it is deliberately distinct from query #11
(`revenue_by_customer_state`), which slices by the sale-time BILLING address and stays raw SQL.
`Customer.ageBand` (which had "physical source TBD" and no source — TPC-DS stores no age band)
became `Customer.birthYear` bound to `c_birth_year`; age is derived at query time (`:year -
birth_year`, #12). `md2db.test.mjs` **T6.8** now enforces this completeness (every attribute is
a bound grain key or has a bound map), so a future unbound attribute fails the suite rather than
loading silently clean — the lint has no rule for descriptive-attribute binding.

**md2db (Stage 2.4 finding):** `md/table-map-no-binding` is `scope: 'document'`
(`packages/lint/src/rules/md.ts`) — it only looks for an `md2db_map` in the SAME file as
the `def map`. All 4 Product table-maps ARE bound in `model/binding/md2db.ttrm`, just in a
different file than `model/md/product.ttrm` where the maps are declared — the rule's own
docstring says "Phase 3 refines cross-file", so this stays an accepted residual
(`project-harness.mjs`) even though the binding is complete; real completeness is checked
directly against the AST in `model/binding/tests/md2db.test.mjs`, not via this diagnostic.

**Lexicon (Stage 2.5 finding):** the task list's suggested `model/lexicon/value-labels.ttrm`
standalone file doesn't match how `valueLabels` actually works — it's a **property on an
existing `def attribute`** (er or md, both share `attributeProperty` in the grammar), not a
lexicon-schema construct with a `for:` target. `valueLabels` are attached directly on
`Product.categoryCode` (`model/md/product.ttrm`), `ReturnReason.reasonCode`, and
`DistributionCentre.dcCode` (`model/md/dimensions.ttrm`) instead — keyed on whatever the
physical value actually is (`categoryCode`: the stable English category string, same in
both worlds; `reasonCode`/`dcCode`: the `*_sk` integer, since `r_reason_desc` is already
localized per-connection and isn't a stable cross-world key). `desugarLexicon`/`foldId`
(`@tatrman/semantics`) are real, exported APIs — used directly in
`model/lexicon/tests/lexicon.test.mjs` for en/cs twin-parity and diacritic-fold checks
rather than reimplementing that logic.

**Queries + Shems (Stage 2.6 finding — Phase 2 close):** the `15-query.ttrm` conformance
fixture's own `search { keywords {...} }` pattern is itself deprecated
(`ttr/lexicon-legacy-keywords`, RS-32) — none of the 15 `q.hartland.*` queries
(`model/queries/q_hartland.ttrm`) carry it; Discover-chip triggering rides Stage 2.5's
lexicon terms instead. There's also no "language: MD"/dot-path query form in the
grammar, so the "md-derived" drills (#3/#4/#5) are literal SQL against the physical `db`
layer like every other query, not md dot-paths — consistent with Stage 2.3's dot-path
finding. All 15 were EXPLAIN-verified against live `hartland_us` (bonus, not part of the
mocked DONE bar). `agents/hartland.yaml` + both Shem overlays
(`agents/golem/shems/golem-hartland{,-finance}/shem.yaml`) mirror the real, schema-
validated `ai-models` agent-def shape and the `golem-ucetnictvi` assembled-Shem
precedent; checked structurally with `js-yaml` (also borrowed from the sibling tatrman
checkout — see `agents/tests/shems.test.mjs`).

**`sales` — the three channels as one entity (md/hop HP-H, 2026-10-24; ⚑H-1, ⚑H-7 — Bora 2026-10-22).** "Revenue by
channel" needs the channel as a column and revenue as one measure. Since 2026-09-24 that was `channel_sales`, an
entity on the db view `data/views/channel_sales.sql`; its columns were its own, so the lineage of its revenue lived in
the database and no model reader could see that it is the three facts' `ext_sales_price` (the md/hop design §4: the
bearer rule had nothing to restrict to). Now the union is the model's: `er/sales.ttrm` declares the logical query
`er.query.sales_union` over `store_sales`, `web_sales` and `catalog_sales` and the entity `sales` stacked on it —
`channel` an attribute (`store` · `web` · `marketplace`), `store` a store line's, `warehouse` a web or marketplace
line's, relations by `join:` pairs. What a reader would not guess:
- **no relation to `store`**: four Czech cities and Memphis are both a store and a DC, and a bare city resolves through
  the fact's reach — with the store in reach, «Tržby z tržiště … pro Brno» would bind the store and answer an empty
  marketplace. A store name is the composer's (as by-store questions already were on `channel_sales`);
- the channel literals are **CAST to VARCHAR** in the body: bare, the translator types them CHAR(5)/CHAR(3)/CHAR(11),
  unifies the union at CHAR(11) and writes padded `'store      '`, which `channel = 'store'` never matches;
- the DC-scope row rule needs no entry for `sales`: the body is inlined where `sales` is read, so the rule on
  `web_sales` and `catalog_sales` narrows those lines, and the store channel stays whole (Bora, 2026-10-24);
- **the three channel facts are sources only** (⚑H-7). The mechanism is the vocabulary: they carry no
  `displayLabel`/`labelPlural` (a label is a METADATA term) and no lexicon term names them or their attributes
  (`lexicon/tests/store-family.test.mjs` holds it), nor the revenue facet (`semantics { measures }`), and their
  descriptions point at `sales` — what a composer reads. Every channel word is a value of `sales.channel` instead — its
  `valueLabels` plus `lexicon/aliases/channels.lex.yaml` — which the resolver binds as `er.entity.sales.channel#<value>`
  and the query door restricts by. They stay in the package (the union reads them, and so may the composer's SQL), and
  the db-lane `q.hartland.*` queries read their tables;
- the db view `channel_sales` stays declared (it is in both databases, and the routing corpus's validation SQL reads
  it), but no entity reads it.

**Phase 2 is done** — `model/tests/phase2-done.test.mjs` is the single-file roll-up of
the DONE bar; 53 tests pass across all 6 stages (`just verify-model`).

**Automation extension (AU P0, 2026-10-17).** The automation agents' documents — orders and their
lines, price lists, invoices, outages, the return-request flow (`return_request` → lines → receipt,
credit note, refund, replacement shipment, `document_flow`), reorder proposals and win-back mailings:
14 tables, 2 views, 15 entities, 25 relations in `db/orders.ttrm`, `db/returns-flow.ttrm`,
`er/orders.ttrm`, `er/returns-flow.ttrm`, `er/proposals.ttrm`. Designed and planned in
`collite-gh/project/kantheon/features/automation-agents/` (the contract: `implementation/hartland/
contracts.md` §1–§3); `model/tests/automation-extension.test.mjs` holds it as data. What a reader would
not guess:
- the entity `order` reads the table **`sales_order`** — `order` is reserved in SQL (D-119);
- `return_request_line` carries the request's customer, **`rl_customer_sk`**, denormalized by the
  generator: a relation is one hop, and the recipes join a line to its customer (D-127);
- `return_request` and `document_flow` read **views**: the request's state is derived from its lines and
  nothing writes it (D-84); the request's relations bind logical keys on the view (the precedent of the former
  view-backed `channel_sales`, folded into `sales` at md/hop HP-H);
- every extension relation states its **`join:` pairs** beside its fk — TTR-P's `on: relation X` builds
  the join from join pairs only;
- the states are `text` attributes with `valueLabels` and, since AU P2 (grammar 0.16), `states:` /
  `transitions:` — the lifecycle the automation actions are checked against (D-67). Value labels are member terms of the lexicon, so none repeats a word the pre-AU
  vocabulary binds, and the `channel` attributes have none; the bare «reklamace» / «objednávka» are the
  documents by rule (⚑AU-H-3, `lexicon/cs/automation.ttrm`), guarded by
  `lexicon/tests/automation-lexicon.test.mjs`;
- the world `hartland.worlds.demo` is in `../automation/worlds/demo.ttrm` (AU P2): its automation half names
  the programs and roles of `../automation/*.ttrm`, and a reader of `model/` alone (veles, the lexicon build)
  would report each unresolved — the lexicon build refuses such a model. Nothing under `model/` may name an
  automation object (`automation/tests/package.test.mjs`). Nothing in the world names a world's database: the
  engine name is the credential name (`TTR_CONN_ERP`, `TTR_CONN_AUTOMATION`), so one world file serves both
  worlds by connection.

