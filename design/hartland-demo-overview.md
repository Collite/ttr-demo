# The Hartland Demo — Overview & Operator's Guide

*A reference for the whole Hartland demo: the data, the model, the test fixtures,
how to stand the cluster up, and the demo story plus the satellite demos that hang
off it. Written 2026-07-20. Companion to the two authoritative field docs it draws
on: `design/demo-transcript.md` (the narrative — "the demo **is** its transcript")
and `design/demo-quirks.md` (what actually works, and why).*

---

## 0. What the Hartland demo is, in one paragraph

Hartland Stores is a fictional Tennessee retailer (HQ Nashville, ≈ $2.1 B/yr across
three channels — Stores, Web, and a third-party **Marketplace** it fulfils from five
distribution centres). A category manager types a plain-language question into one
input box; the platform classifies it, routes it to the right agent, compiles it
against a **governed model** of the warehouse, executes it on the real data, and
answers in sentences and charts — every block showing its work (ⓘ → the exact SQL,
`db=hartland`, a timestamp). The thesis the whole thing exists to prove: **the LLM
handles intent only; everything from intent to data execution is deterministic and
governed.** The seeded plot is an operational incident — the *Memphis DC melts down
for ~17 weeks in late 2025* — buried in otherwise-flat data, so that an AI-driven
root-cause investigation lands on the true cause while every wrong hypothesis dies on
real numbers. The demo runs bilingually: identical arc in English over `hartland_us`
(USD, Memphis) and in Czech over `hartland_cz` (CZK, Brno).

---

## 1. Data overview

### 1.1 Basis — TPC-DS SF1, re-grounded

The underlying data is **TPC-DS at Scale Factor 1** (`tpc-ds-1g`, dsdgen-generated).
Both worlds are restored from one pristine source dump and put through a deterministic,
idempotent pipeline (`hartland/data/README.md`): **redate → localize-cz → catalog →
seed → recon**. Every stage is hash- or snapshot-guarded so any world is rebuildable
from `tpc-ds-1g` + the committed scripts.

- **Redate (+23 years).** `data/redate/run-redate.sh` re-points every `*_date_sk` and
  bumps `c_birth_year` so 1998–2003 becomes **2021–2026** with believable ages;
  `date_dim` is left intact. Guarded (aborts if `store_sales` max year ≥ 2010; refuses
  to touch `tpc-ds-1g` unless named explicitly).

### 1.2 Row counts (demo-ready state, both worlds identical)

From `data/recon/results-us/r00_rowcounts.csv` (identical in `results-cz/`):

| table | rows | | table | rows |
|---|---|---|---|---|
| store_sales | 2,880,404 | | catalog_sales | 1,424,874 |
| store_returns | 287,514 | | catalog_returns | 142,371 |
| web_sales | 719,384 | | web_returns | 71,763 |
| inventory | 11,745,000 | | customer | 100,000 |
| item | 18,000 | | warehouse | 5 |
| store | 12 (6 logical, SCD-doubled) | | promotion | 300 |
| call_center | 6 | | reason | 35 |

**Time coverage.** As restored, sales run 2021-01-01 → 2026-01-08 (store and web to 2026-01-02)
and inventory to 2025-12-26 — the table above. `data/extend/` (LR-P4) then copies the template year
2024 forward week by week to a date you name, re-run before a show; extended to 2026-10-31 the
facts reach 2026-11-02 and gain 368,898 store, 191,657 marketplace and 98,686 web lines, 32,337
returns and 1,980,000 inventory rows (both worlds; 2026 figures in `data/recon/R1.md`). The meltdown
DC is recovered in extended weeks — 2026 reads as a normal year.

The pre-seed baseline (`results-precatalog/`) differs on exactly two tables — the seed's
S2 deletion removes 16,674 `catalog_sales` and 1,696 `catalog_returns` lines. Everything
else is identical, which is the point (see §1.5). Post-catalog the item population carries
**10 categories, 42 brands, 99 classes**.

### 1.3 The two worlds — `hartland_us` (USD) vs `hartland_cz` (CZK)

Two schema-identical Postgres databases on **one CNPG cluster** (Q-BM-3a: one CNPG,
two DBs), one TTR-M model set, **two connections** (`pg-hartland-us` / `pg-hartland-cz`).
The physical TPC-DS schema is byte-identical; only the *lexicon* (en vs cs) and the
currency data differ. Currency is a data fact plus a per-locale display label, not a
structural difference — `md.Money` is a currency-agnostic `decimal` domain.

- **FX constant = 23** (`data/localize-cz/fx.conf`). CZ was derived from US by FX-scaling
  every monetary column ×23, rounded to a believable price point (nearest 10 Kč ≥ 100,
  nearest 1 Kč below). Applied **once**, guarded by `_localize_meta` (a second run would
  compound to ×529 and is refused).
- **Full re-grounding, not a re-skin** (`data/localize-cz/`): CZK currency; geography
  mapped US-state → Czech kraj distribution-preservingly (stores → Praha, Brno, Ostrava,
  Plzeň, Olomouc, Liberec on the same `s_store_id` keys; 14 kraje + 1 null-fallback);
  distribution centres re-pointed (the meltdown DC `w_warehouse_sk=5` = **Brno DC**,
  mirroring US **Memphis DC**); Czech `lexicon`, reasons, and catalog.
- **Story mirrored, not re-invented** (BM-7): the seed % magnitudes are tuned once on US
  and inherited verbatim by CZ; the S2 deletion is currency-invariant (hash-keyed on
  `cs_order_number`), so both worlds delete the *same* lines. One locale per delivery,
  never both on stage (BM-8).

### 1.4 The catalog delta — real product names on top of dsdgen gibberish

BM-4 added a **full per-item bilingual catalog** for all 18,000 items — real
`i_product_name`, `i_brand`, `i_manufact`, `i_size`, `i_container` per world — so the
MD Product hierarchy (Category → Class → Brand → Manufacturer → Item) is a genuine drill
rather than dsdgen noise. Source of truth is `data/catalog/taxonomy.yaml` (10 categories,
hand-curated hero brands like Voltaic, Auravelle, Willowmere, Stridewell). The generator
(`data/catalog/generate.py`, v1.0.0) is **deterministic** — every choice is
`sha256(f"{i_item_sk}:{salt}") mod len`, no `random()`/wall-clock — emitting idempotent
PK-keyed UPDATEs (`catalog/us.sql`, `catalog/cz.sql`, 18,000 rows each).

**Orthogonal to the sales story.** The catalog rewrite never touches `i_item_sk`,
`i_category`, `i_category_id`, `i_class_id`, `i_current_price`, or the SCD validity window
— the invariants the (item-agnostic, warehouse×week-keyed) seeds and recon depend on. The
recon proves it: pre-catalog vs post-catalog aggregates are identical except where the seed
later moved them. "The catalog is orthogonal to the sales story" is made *physically* true,
not asserted.

### 1.5 R0 — the frozen numbers

`data/recon/R0.md` is the authoritative frozen-number record every `⟨R0⟩` slot in the
transcript and every test oracle resolves against. **Frozen 2026-07-18** (Stage 1.6) from
the final recon on both worlds. Rule: **CZ = US × FX(23)**; percentages are
currency-invariant and match across worlds. Key frozen signals:

- Marketplace weeks 32–48/2025 YoY vs 4-yr avg (**briefing headline**): **−10.62 %**.
- Marketplace calendar-H2 2025 YoY: **−8.44 %**; November 2025: **−12.45 %** (worst month).
- Meltdown-DC weeks 32–48/2025 YoY: **−58.99 %** (spec ≈ −60 %); zero-inventory streak
  **17 weeks** (wks 31–47); zero-row share 2025 **22.8 %** vs ~0.09 % elsewhere.
- "Did not get it on time / Nedorazilo včas" reason share on surviving meltdown-DC returns:
  **39.10 %** (vs **2.87 %** baseline).
- Four non-meltdown DCs 2025 flat at $144.2 M–$145.6 M; meltdown DC $102.8 M (−29 %).
- Deliberate red herrings, confirmed flat both worlds: Web channel, Stores, promo linkage
  (~99.6 %), buyer age, geography distribution.

### 1.6 The demo dumps (`data/recon/dump-manifest.md`, `pg_dump -Fc -Z6`, 2026-07-18)

| world | path | size | sha256 (head) |
|---|---|---|---|
| US | `tpcds-staging/hartland/us/hartland_us-demo-20260718.dump` | 380,116,857 B | `0ebfd948…` |
| CZ | `tpcds-staging/hartland/cz/hartland_cz-demo-20260718.dump` | 338,962,330 B | `9d7b02ed…` |

A DR pre-catalog snapshot is retained (`hartland_us-precatalog-20260718.dump`,
`4ea83a7a…`); the CZ pre-seed state is not snapshotted because it is fully reproducible
from `tpc-ds-1g` + scripts.

---

## 2. The model — all layers of the Hartland TTR-M

The model is a single TTR-M model set (root `hartland/model/`, every file declares
`package hartland`, flattened via `modeler.toml [packages] layout = "off"`). It is a
curated TPC-DS subset dressed as Hartland Stores, in **five layers plus bindings**.

### 2.1 The layer cake

- **`db/` — physical (`schema dbo`).** The TPC-DS tables actually present.
  `facts.ttrm`: `store_sales`, `web_sales`, `catalog_sales` (Marketplace), the three
  `*_returns`, `inventory`. `dims.ttrm`: `date_dim`, `item`, `customer`,
  `customer_address`, the demographics dims, `store`, `warehouse`, `promotion`, `reason`,
  `call_center`. `fks.ttrm`: the foreign keys. Money columns are `decimal(10,2)` (superset
  of US `numeric(7,2)` and CZ's widened `numeric(10,2)`). **Deliberately not modelled
  (D-6a):** every `*_net_profit`, `*_net_paid*`, `*_wholesale_cost`, `*_list_price`,
  discount/tax/ship/coupon column — so **no margin or profit path exists at all**. (Two
  reserved-word workarounds: `date` → `cal_date`/`as_of_date`.)
- **`er/` — 19 curated logical entities** (`er2db` binding). Physical prefixes stripped;
  each entity carries a bilingual `displayLabel` (e.g. `catalog_sales` → *Marketplace
  Orders* / *Objednávky z tržiště*; `warehouse` → *Distribution Center* / *Distribuční
  centrum*). Relationships in `relations.ttrm` (all fact→dim, each bound to a `db` FK).
  `area.ttrm` defines **`def area hartland`** (tags `reporting`/`demo`) — this is what the
  agent's Ariadne resolves.
- **`md/` — the ROLAP star.** `measures.ttrm`: `revenue` (Money, additive), `quantity`,
  `orderCount` (countDistinct), `lineCount`, `returnAmount`, `onHandQty` (semi-additive,
  `time: latestValid`, `validBy: week`). `dimensions.ttrm` + `product.ttrm`: `Customer`,
  `Store`, `DistributionCentre` (5 DCs with valueLabels), `Promotion`, `ReturnReason` (all
  35 reasons; sk 3 = *Did not get it on time*), and `Product` with the 5-level
  `productDrill` (item → manufacturer → brand → class → category, 10 categories).
- **`lexicon/en/` + `lexicon/cs/` — bilingual naming** (§2.3).
- **`binding/` — `er2db.ttrm` + `md2db.ttrm`.** Descriptive attributes bind via
  table-backed `def map` (`store_to_name`, `dc_to_name`, `reason_to_desc`, `item_to_name`,
  …). `Customer.state` is the *home* state (two-hop through `c_current_addr_sk`),
  deliberately distinct from query #11's *billing* address.

### 2.2 Worlds and named connections

`model/connections.toml` (a repo descriptor — a connection is **not** a TTR-M grammar
construct) declares the two worlds against the same physical model:

```
[[connection]] id="pg-hartland-us" database="hartland_us" schema="dbo" currency="USD" locale="en"
[[connection]] id="pg-hartland-cz" database="hartland_cz" schema="dbo" currency="CZK" locale="cs"
```

Row-level security: read-only roles `hartland_us_readonly` / `hartland_cz_readonly` (CNPG
`managed.roles`), materialised by the `pg-hartland-us-ro` / `pg-hartland-cz-ro`
ClusterExternalSecrets. Arges (the Postgres worker) reaches each world via those
connections; Kyklop maps `world.table-connections` (same model tables → each DB).

### 2.3 The bilingual lexicon

`lexicon/en/` and `lexicon/cs/` use the **same `for:` targets** (the one-model,
two-locales invariant). Channel synonyms (`channels.ttrm`): EN `marketplace / 3P /
third-party / fulfilled by Hartland` → `catalog_sales`; CS `tržiště / třetí strana / 3P`.
Measure synonyms (`measures.ttrm`): EN `revenue / sales / turnover`, `returns / refunds /
RMA`; CS `tržba / obrat`, `reklamace / vratky`. valueLabels attach on `Product.categoryCode`
(10), `ReturnReason.reasonCode` (35), `DistributionCentre.dcCode` (5, e.g. `"5"` = Memphis
DC / Brno DC).

### 2.4 The 15 pattern queries — `model/queries/q_hartland.ttrm`

The curated pattern catalog is the heart of the deterministic path. All 15 are `def query`
blocks, `language: SQL`, literal `sourceText` against the physical `db` layer (there is no
MD/dot-path query form in the grammar). Each carries a `search { patterns, examples }` block
(EN + diacritic-folded CS regex). Channel literals in SQL are lowercase
(`'store'`/`'web'`/`'marketplace'`). Year params default 2021–2026 at the caller layer.

| # | name | params | answers |
|---|---|---|---|
| 1 | `channel_revenue_monthly` | year_from, year_to | monthly revenue per channel (the pinned "Channel Health" chart; **72 rows** = 24 mo × 3 ch) |
| 2 | `channel_revenue_yoy` | year, prior_year | YoY revenue per channel (the −11 %-ish briefing KPI) |
| 3 | `category_revenue` | channel, year | revenue by product category for one channel |
| 4 | `marketplace_revenue_by_warehouse` | year_from, year_to | Marketplace revenue by DC (Memphis/Brno stands out) |
| 5 | `top_items_by_revenue` | year, limit | top products by revenue on Marketplace |
| 6 | `returns_by_reason` | channel, year | returns by reason (the "did not get it on time" skew) |
| 7 | `returns_rate_by_channel` | year | return amount / revenue per channel |
| 8 | `warehouse_stockout_weeks` | year | weekly zero-inventory incidence per warehouse (the 17-week streak) |
| 9 | `inventory_on_hand_series` | warehouse, year | weekly on-hand series for one warehouse |
| 10 | `customer_channel_overlap` | year | customer channel-touch combinations (cannibalisation branch — dies) |
| 11 | `revenue_by_customer_state` | channel, year | revenue by billing state (regional branch — dies) |
| 12 | `buyer_age_profile` | channel, year | buyer age distribution (demographic branch — dies) |
| 13 | `promo_share` | channel, year | promoted vs unpromoted revenue share (promo branch — dies) |
| 14 | `store_sales_by_month` | — | store revenue by month (seed-heritage texture) |
| 15 | `customer_running_total` | — | running total of store spend per customer (window coverage) |

Queries #1–#8 carry the demo; #10–#13 are the RCA fan-out branches that *die on real
numbers*; #14/#15 are coverage. **No query touches profit/cost** — there is nothing to
select even if one tried (D-6a).

### 2.5 How the model is served (veles → ModelBundle → golem)

**veles** polls the model from git `Collite/ttr-demo` (branch `demo-p2`, subdir `model/`)
and serves it as a ModelBundle. golem asks Ariadne `ResolveArea(hartland)` → the flat
`hartland` package → `GetModel`, and loads the 15 `q.hartland.*` as its `preferred_queries`.
Two operational rules that have bitten hours (demo-quirks §1):

1. **veles filters packages by file *path*, not the declared `package`** — the checkout
   dir must contain a `/hartland/` segment (`METADATA_GIT_CHECKOUT_DIR=/tmp/metadata-git/hartland`).
2. **The two-refresh rule** — after any model edit you must refresh *both* veles
   (`VelesService/Refresh {force:true}`, confirm `ListQueries` → PARSED) **and** golem
   (`kubectl rollout restart deployment/golem-hartland -n kantheon` and `-finance`), because
   golem caches the ModelBundle at boot. Skipping the golem restart leaves it sending stale
   SQL that fails at the translator — which golem masks as `STATUS_DONE, 0 rows`.

### 2.6 Model quirks worth knowing (demo-quirks.md)

- **The meta-quirk (§0):** a failed query node reports `STATUS_DONE, rowCount=0`, *not* an
  error. "0 rows" usually means *rejected* (translator, empty, or RLS-zeroed). Read the
  `ttr-query` log by `correlation_id` for the real cause.
- **Calcite is stricter than Postgres (§2):** a CTE named `returns` is a reserved word
  (→ `rets`); `GROUP BY` on a SELECT alias is forbidden (→ group by the underlying column,
  why `buyer_age_profile` groups by `birth_year`); named params must be single-curly
  `{name}` only (`:name`/`@name`/`{{name}}` are not rewritten).
- **Case-sensitive text params (§3.3):** `WHERE channel = {channel}` bound from "Marketplace"
  vs the lowercase literal `'marketplace'` → 0 rows. The proper fix (`CaseFoldingParams`,
  a RESOLVE-stage `LOWER()` fold) is on tatrman `feat/case-insensitive-text-params`, not yet
  released — until then, phrase utterances with lowercase channel tokens.
- **`buyer_age_profile`** has a form-dependent translator quirk (the row-serving form leaks a
  null-age bucket); left with an inline NOTE, tracked as demo-polish.

---

## 3. Test fixtures

### 3.1 The shared `hartland-pg` fixture

The decision (`design/test-fixture-hartland-replan.md`, BM-10): the two Phase-1 worlds
become the **standard warehouse for all e2e / integration / nightly tests on every
cluster** (bp-dsk, collite-o1, hartland). Tests default to **CZ**; EN is used where
language-agnostic or specifically testing the US world. This replaces the old per-context
ad-hoc data (`tpc-ds-1g`, the erp fixture).

It is **one platform component authored once in olymp** (`platform/data/hartland-pg/`) and
composed into each cluster's data tier — the generalisation of the demo's own CNPG:
- `base/cluster.yaml` — CNPG `Cluster` `hartland-pg` (ns `data`, 20 Gi), `managed.roles`
  `hartland` + `hartland_us_readonly` + `hartland_cz_readonly`.
- `base/databases.yaml` — two CNPG `Database`s (`hartland_us`, `hartland_cz`).
- `overlays/<cluster>/` — the base plus the three role-password ExternalSecrets, per cluster.

### 3.2 Source of truth and restore

The fixture's source of truth is the Phase-1 versioned dumps in `tpcds-staging/hartland/{us,cz}/`
(SeaweedFS), pinned in the restore Job from `data/recon/dump-manifest.md`. When Phase 1
re-freezes R0, the fixture is re-restored — one values bump + a Job re-run per cluster.

`base/restore-job.yaml` (`hartland-restore`, ns `data`) is **deliberately not in any
kustomization** — it is applied *by hand* so ArgoCD never re-runs the ~700 MB restore on a
sync:

```
kubectl --context <c> -n data delete job hartland-restore --ignore-not-found
kubectl --context <c> -n data apply -f platform/data/hartland-pg/base/restore-job.yaml
```

It pulls each dump from SeaweedFS (`seaweedfs-s3.data.svc:8333/tpcds-staging`),
`pg_restore --clean --if-exists --no-owner` into each DB, GRANTs SELECT/CONNECT/USAGE to the
`<db>_readonly` role, and prints a row-count sanity check (expects item 18000, store_sales
2880404, catalog_sales 1424874). SeaweedFS is **per-cluster**, so a new cluster's bucket must
be seeded first (relay the dumps through a workstation; anonymous read/write, no S3 creds).

### 3.3 How test contexts consume it

- **Read path:** Arges reaches each DB read-only via `pg-hartland-us` / `pg-hartland-cz`,
  backed by the two RO ClusterExternalSecrets whose `namespaceSelectors` match harness run
  namespaces (label `olymp.collite/managed-by=test-harness`).
- **olymp test-contexts re-plan:** `tpcds-query → hartland-query`, `theseus-runquery`
  repointed at `hartland_cz` (the scheduled nightly moves first), `golem-erp → golem-hartland`,
  plus `pythia-rca` / `themis-routing`; `smoke` unchanged. The nightly matrix
  (`kantheon/deployment/test/…`, `olymp/.github/workflows/nightly-ecosystem.yml`) updates to
  the hartland context names.
- **Gating:** raw-SQL contexts need only Phase 1 (dumps); model/agent contexts also need
  Phase 2 (the model + Shems served by veles/Ariadne).
- The `hartland-query` run-set (oracle rows for all 15 queries on both worlds, run by
  `just demo-check hartland`) is **not yet populated** — drive live queries or the recon
  scripts for now.

---

## 4. Standing the cluster up (replication)

Root: `olymp/clusters/hartland/`; architecture at `olymp/docs/architecture.md`. Standalone
ArgoCD per cluster, bootstrap → root-app → app-of-apps → ApplicationSets.

### 4.1 GitOps structure

- **Entry:** `root-app-hartland.yaml` → `clusters/hartland` (project platform-ops,
  prune + selfHeal).
- **App-of-apps** (`clusters/hartland/kustomization.yaml`, ordered): namespaces + cluster
  identity → `sys-argocd` (full profile) → bootstrap tier (`sys-cert-manager` issuers,
  `sys-eso`, `sys-image-updater`) → AppProjects → the three ApplicationSets.
- **appset-ops** (`hartland-ops`): one Application per `platform/*` area —
  **auth, data, gateway, monitoring**.
- **appset-apps** (`hartland-apps`): one multi-source Application per `apps/*/config.json`
  (chart from the monorepo + values from olymp).
- **appset-golems** (`hartland-golems`): one golem per enabled Shem JSON in `golems/`
  (see §4.4). *Reminder:* this must be listed in the cluster root `kustomization.yaml` — it
  is easy to add the file and forget the wiring, in which case the ApplicationSet is never
  created.

### 4.2 Data tier (`platform/data/kustomization.yaml`)

CNPG operator + `postgres` (the per-agent central DB) + `test-pg` + **`hartland-pg`**
(the shared warehouse) + `backstage-postgres` + `kleio-pg` (pgvector/AGE) + `mssql` (Brontes)
+ `redis` (Charon session/cache) + `seaweed` (S3 object store). Barman PITR is intentionally
off on this cluster (O-5).

### 4.3 Services (`apps/*`, ~37 dirs) and the demo-turn constellation

- **`ttr-server` ns (the open spine, tatrman-server charts):** `veles` (+`veles-mcp`),
  `dispatch`, `query` (theseus) (+`query-mcp`), `translate`, `validate` (Argos governance),
  `llm-gateway` (gateway 2.0), `nlp`/`fuzzy` (+mcp), `identity`, `health`, plus data-plane
  workers.
- **`kantheon` ns (agents + frontend):** `iris` + `iris-bff`, `capabilities-mcp`,
  `themis-mcp`, `pythia`, `hebe`, `kleio`, `metis` (+mcp), `charon` (+mcp), `kallimachos`,
  `pinakes`, `landing`, and the golems.

**A single demo turn flows:** `golem-*` (kantheon :7420) → **veles**.ttr-server (:7261 gRPC,
ResolveArea/model) + **llm-gateway**.ttr-server (:7280, `Bearer ttrk-golem`) → **query-mcp**
(:7307/mcp) → **theseus** (`ttr-query`) → translate / validate / worker → **hartland-pg**
(`hartland_us`/`hartland_cz` in ns `data`). `capabilities-mcp` (:7501) handles registration
so Discover/Themis can route. Cross-namespace hosts **must** be FQDNs.

### 4.4 Golems (`golems/`)

`appset-golems.yaml` renders each enabled Shem from three sources: (1) the Shem ConfigMap from
`Collite/ttr-demo@demo-p2` (`agents/golem/shems/<shem>`, read via the `argocd-hartland-repo`
cred); (2) the golem chart from `Collite/kantheon@master`; (3) the `$values` ref (olymp).
Enablement is one JSON per Shem — `golem-hartland.json`, `golem-hartland-finance.json`.
`_values.yaml` pins the image (`ghcr.io/collite/golem:0.9.4`, `IfNotPresent`), the veles gate,
the nested prompt-bundle mount, the central `golem` DB, and the extraEnv wiring
(veles/gateway/query-mcp FQDNs, resume-HMAC, `GOLEM_LLM_GATEWAY_KEY`).

### 4.5 Secrets — the hartland vault

All ClusterExternalSecrets pull from ClusterSecretStore `azure-store` →
**`https://hartland.vault.azure.net/`** (a *separate* vault from olymp01/olymp — Collite
tenant). The demo-critical ones: `veles-github-pat` (+ `argocd-hartland-repo`, same key —
model + Shem-bundle access), `golem-llm-gateway-key` (vault `ttrk-golem`),
`llm-gateway-secrets` (vault `azure-openai-key` — the real Azure OpenAI provider key),
`pg-hartland-us-ro` / `-cz-ro`, and the warehouse role passwords in the data overlay
(`pg-hartland-cred` + the two RO creds).

### 4.6 Bring-up sequence and the manual (non-GitOps) steps

Pre-flight gates (`plan-cluster.md`): G1 release tags · G2 the `Collite/ttr-demo` repo
(model + 15 queries + both Shems) · G3 the seeded dump in Seaweed · G4 constellation proven
on bp-dsk · G5 hardware. Then H1 fork (`just new-cluster` → `just bootstrap` → re-seal
`eso-bootstrap-auth` → verify the four platform apps Synced/Healthy), H2 warehouse, H3 wiring,
H4/H5 rehearsal + freeze.

**Four steps GitOps does *not* do — run them by hand (and the collite-o1 bring-up on
2026-07-20 proved every one is a real gate):**

1. **Restore the warehouse** — `kubectl delete/apply` the `hartland-restore` Job after the
   dumps are staged to that cluster's SeaweedFS (§3.2).
2. **Seed the gateway virtual keys** — the LLM-gateway validates each caller's `ttrk-*` key by
   the SHA-256 of the key looked up in its `virtual_keys` Postgres table (`db.enabled=true` →
   `PgKeyValidator`; the config-based fallback validates nothing). Seed via SQL INSERT per the
   cutover runbook (`tatrman-server/services/ttr-llm-gateway/docs/cutover-runbook.md §2a`); the
   `teams` are auto-upserted from `governance.yaml` at boot. **The vault key value must be a
   properly-minted `ttrk-` key** (`ttrk-` + 43 base64url chars) — the validator rejects on the
   `ttrk-` prefix check *before* any DB lookup, so a malformed placeholder can never be seeded
   into working.
3. **Load the Keycloak realm personas** — realm `kantheon` (ns `auth`): Maya, Dan, Markéta,
   Tomáš, the two realm roles, and the `iris` public client. Note the config-sync is an ArgoCD
   **PostSync hook** — it only re-runs on a real **Sync** (not a refresh), and its
   `hook-finalizer` can wedge on a deletion (unwedge by terminating the op).
4. **The two-refresh rule** after any model edit (§2.5).

Other operational gotchas (demo-quirks.md): golem masks failures as "0 rows"; Helm `extraEnv`
*replaces* (re-list the chart's veles env or the validator loses it); `VALIDATE_DEFAULT_TOP_N=100`
is set on hartland (§5); images must be multi-arch (the node is amd64 — prefix jib with `CI=true`).

---

## 5. The demo story

The transcript (`design/demo-transcript.md`) is the design artifact — the demo *is* its
transcript. It runs in six beats plus two in-script satellites. Setting: a Monday morning,
mid-January 2026, "we just closed 2025."

- **Beat 1 — cold open (the scheduled brief).** Iris' inbox holds an overnight "Monday channel
  health brief" (a Hebe routine, `TurnOrigin.SCHEDULED`). A KPI table shows the three channels;
  Stores flat (+0.5 %), Web noise (−2.2 %), **Marketplace −6.18 % FY / −8.65 % H2**, with the
  incident's own 17-week window at **−10.62 %** (the headline). Rendered live from patterns
  #2 and #1 — "nothing on this stage is a mock-up."
- **Beat 2 — conversational Q&A with Golem (the core).** Five turns: (1) Marketplace 2025 monthly
  → the flattened Aug–Oct step; (2) Web vs Marketplace 2024→2025 → "Web is noise-level; something
  eats exactly one channel"; (3) categories → drop spread evenly −7.3 % to −13.7 %, "a product
  problem hits products; this hit a channel"; (4) **AOV** via plan source **`free_sql`** —
  visibly no prepared pattern, same governed model, same ⓘ→SQL — "it's not a decision tree,
  it's an analyst"; (5) **"What did the slump cost us in profit?"** → a graceful **model gap**
  (profitability isn't modelled, D-6a) — *"in a room full of AI demos, this is the most important
  answer you'll see today: when it doesn't know, it says so."*
- **Beat 3 — Pythia RCA (centerpiece).** *Investigate* routes Golem → Iris/Themis → Pythia (never
  Golem → Pythia direct); a `HandoffContext` carries the conversation, nothing re-asked. A live
  hypothesis tree with a budget meter: customer-shift, demographic, promo, and regional branches
  all **die on flat real numbers** (patterns #10–#13); the fulfilment branch **survives** — returns
  reason skew to 39.10 %, Memphis DC −58.99 %, a 17-week zero-on-hand streak (#6/#4/#8/#9).
  Conclusion: *Memphis DC stopped fulfilling for ~17 weeks; H2 impact −$44.9 M / −$36.8 M in the
  incident window*, plus honest LooseEnds.
- **Beat 4 — pin it.** The conclusion block + the monthly chart pin to a "Channel Health"
  dashboard — *"the chart re-executes on refresh (a living view); the conclusion's evidence is
  frozen (a record). Replay versus reproduce."*
- **Beat 5 — forecast + what-if.** Per-channel forecast with confidence intervals (Metis
  Fit/Project on the #1 series), then a live Metis Simulate what-if ("assume Memphis is back from
  June and we run a Marketplace win-back promo in November") — a runtime simulation, *not* an
  R0-frozen fact.
- **Beat 6 — close the loop.** "Set this up as my Monday morning brief" → Hebe creates the routine
  from chat — the same routine that wrote Beat 1.

**Personas** (Keycloak realm `kantheon`, all password `Hartland!2026`): **Maya Chen** (US, en,
Senior Category Manager, role `kantheon-area-hartland`) is the narrator; **Markéta Nováková**
(CZ, cs) runs the identical arc in Czech (Brno, Kč); **Dan Whitaker** (US CFO) and **Tomáš Horák**
(CZ CFO) hold `kantheon-area-hartland` **+** `kantheon-role-finance`. The **two Shems** point at
the *same* area and model — `golem-hartland` (Analytics, all 15 patterns, `kantheon-area-hartland`)
and `golem-hartland-finance` (a `preferred_query_subset` of three, `kantheon-role-finance`,
distinct agent id so Discover/routing don't collide). Themis does visibility-filtered routing on
the realm role; iris-bff filters Discover — the two roles are **disjoint**, so for Maya the finance
agent *does not exist* (nothing greyed-out to click), while Dan sees two cards.

**The "4-bug cascade"** behind the headline "72 rows" turn is the demo's cautionary tale: it only
works once four independent fixes line up — single-curly `{param}` (parse), correct
`source_language=sql` + `source_schema=DB` (not translator-rejected), lowercase channel token or
CaseFolding (filter matches instead of 0 rows), and `VALIDATE_DEFAULT_TOP_N=100` (all 72 rows
survive the governance cap) — each of which otherwise fails *silently* as a phantom "0 rows," and
each needing the two-refresh to take effect. The **72 rows** are 24 months × 3 channels; the TopN
cap of 100 was chosen to keep the series whole *and* leave room to demo a visibly-capped larger
query as a governance beat.

---

## 6. Satellite demos

The main pattern-answering demo can be surrounded by side-shows that each foreground one facet of
the platform. Below, honestly labelled by maturity (vocabulary from `tatrman-server/README.md`:
*live · extracted · planned · parked*).

### 6.1 Show the model — authoring & visualisation (tatrman)

- **VS Code TTR-M editing + live validation (EXISTS)** — the `ttr-modeler-vsc` extension over the
  shared LSP: open `hartland/model/`, edit an entity, watch live diagnostics (unresolved-reference
  class from `@tatrman/semantics`), hover, go-to-def, find-refs. Push to `demo-p2`, then the
  two-refresh, and *the answer changes* — a live "edit the governed model" satellite. (Respect the
  Calcite guardrails in §2.6.) The `openInDesigner` command is still a stub.
- **The Designer / "Studio Viewer" (EXISTS, read-only)** — `tatrman/packages/designer` (React +
  Cytoscape, LSP-in-a-Web-Worker, no server). Renders the `db` schema (tables + FK edges) and `er`
  (entities + crow's-foot relations) with an inspector. Crucially it has a backend selector:
  **`?veles=<base>` renders the *deployed* Hartland model straight from the running cluster's Veles
  catalog API** — not just local files. Live *editing* in the Designer is partial/unverified.

### 6.2 Show the processing — TTR-P (tatrman)

Further along than the ecosystem CLAUDE.md implies: TTR-P v1 is *implementing*, all four v1 checks
(A–D) MET as of 2026-07-20. TTR-P surfaces parse into one Calcite-RelNode execution graph, then
transpile to pandas / Polars / SQL dialects run on Kyklop workers.

- **TTR-P VS Code (EXISTS)** — `ttrp-vscode-ext`: diagnostics, hover with ER provenance, SSA-aware
  rename, and **Build / Run / Explain** commands over a Kotlin LSP. A concrete `.ttrp` authoring
  surface.
- **One program, two engines, identical output (LIVE, Check A)** — the same TTR-P program compiled
  to Postgres SQL and to Polars produces **byte-identical** results.
- **LLM-assisted TTR-P authoring (LIVE, Checks C+D)** — an assist demo running against the Kantheon
  llm-gateway → Azure, with a pinned eval baseline in CI.
- Not yet: the optimizer (TTR-P v2, *not started*), the graphical `ttrp-designer` (empty-README
  stub), the bare `.ttrb` hero live-run.

### 6.3 Show the runtime — the governed query path (tatrman-server)

The open runtime that already serves the demo (ns `ttr-server`).

- **Drive the MCP surface directly (LIVE)** — `ttr-query-mcp` (:7307, `/mcp`) exposes `query` and
  `compile`. The "any agent, any vendor, through a contract" pitch made literal.
- **The deterministic plan without executing (LIVE)** — `compile` returns the physical plan: *here
  is exactly what the LLM's intent compiled to, before a row moves.*
- **Provenance (LIVE)** — the ⓘ → SQL expander on any block (exact SQL, `db=hartland`, timestamp,
  `BlockProvenance`); this is Beat 2 of the main demo.
- **Identity fail-closed (LIVE, unit-tested)** — `ttr-query-mcp`'s `IdentityGate` refuses a
  service-account token with no user claim, and a token-vs-arg conflict (`identity_conflict`) —
  no spoofing.
- **RLS + the TopN cap, visibly (LIVE)** — `ttr-validate` injects row-level security *and* a TopN
  `LIMIT` into every plan (`effectiveCap = min(caller, serviceDefault)`; a caller can only ask for
  *fewer*). On hartland `VALIDATE_DEFAULT_TOP_N=100`, deliberately set so a large query is *visibly*
  capped — "there is no flag that bypasses the validator." (Caveat: `row_limit` on `RunRequest` is
  dead plumbing today; the only live lever is the service default — tracked as NEW-4.)

### 6.4 Show the constellation — Kantheon

- **The Discover UI, identity-filtered (EXISTS)** — `iris/…/DiscoverPanel.vue`: domain cards
  filtered by realm role. Backs the in-script Satellite D (Maya's domain card with six live
  example-question chips — "every chip a question that just worked") and Satellite G (Maya one card,
  Dan two — *"the finance agent doesn't exist in her world; identity travels down to the database,
  so there's nothing to click around"*).
- **Multiple agents, one router (LIVE on hartland)** — show Themis picking different agents for Q&A
  vs Investigate vs Forecast (Golem / Pythia / Metis), and `capabilities-mcp` as the registry it
  reads. Honest caveat: the *advanced* surfaces (Iris inbox/pins, Hebe scheduled-turns, the full
  Metis forecast/what-if with Charon + Polars + NATS) are the newest, highest-risk beats; the solid
  core is Beat 2 on the governed path.

### 6.5 Show the data — raw vs governed

Both DBs are live in ns `data`. The interesting satellite is *the divergence*, not the match:

- **Re-run the `free_sql` AOV answer raw** in `psql` on `pg-hartland-us` — same numbers, showing
  the agent wrote real SQL.
- **The governed path is deliberately *not* identical to raw psql:** the validator's TopN LIMIT is
  injected (governance made concrete); the Calcite translator is stricter than Postgres (a raw query
  can succeed where the governed one is *rejected* — the contract-vs-trust story); and RLS scopes the
  CFO's rows where raw psql sees everything (row-level security doing its job).
- Ground-truth assets to show *how the story was authored*: `data/recon/run-recon.sh` + `R0.md`
  (the frozen numbers), and the incident seeds
  `data/seed/02-seed-incident/{s1-inventory-zero,s2-marketplace-delete,s3-reason-skew}.sql`.

---

## Appendix — key paths

| what | path |
|---|---|
| Demo narrative | `hartland/design/demo-transcript.md` |
| Bring-up field notes (read this) | `hartland/design/demo-quirks.md` |
| Fixture re-plan | `hartland/design/test-fixture-hartland-replan.md` |
| Czech mirror + catalog delta | `hartland/design/08-czech-mirror-and-catalog-delta.md` |
| Data pipeline | `hartland/data/{README.md,redate,localize-cz,catalog,seed}` |
| Recon / R0 / dump manifest | `hartland/data/recon/{R0.md,dump-manifest.md,run-recon.sh}` |
| Model | `hartland/model/{db,er,md,binding,lexicon}/*.ttrm` |
| Pattern queries | `hartland/model/queries/q_hartland.ttrm` |
| Connections | `hartland/model/connections.toml` |
| Shems / agents | `hartland/agents/{hartland.yaml,golem/shems/golem-hartland{,-finance}}` |
| Warehouse fixture (olymp) | `olymp/platform/data/hartland-pg/` |
| Cluster | `olymp/clusters/hartland/` |
| Personas realm | `olymp/platform/auth/keycloak/overlays/hartland/realm/kantheon.json` |
| Gateway cutover runbook | `tatrman-server/services/ttr-llm-gateway/docs/cutover-runbook.md` |
