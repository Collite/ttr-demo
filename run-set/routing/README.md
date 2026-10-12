# run-set/routing — the routing corpus (LR P6, contracts C-9·3)

Which lane answers each demo question, and whether the answer is right. One case per question, asked
in **both** languages: `cz` (hartland_cz) asks the `cs` wording, `us` (hartland_us) the `en` one. The
cluster serves one world at a time (olymp `just world <us|cz>`), so a run covers the delivered world.

Run by `scripts/routing-run.py` (uv: httpx + pyyaml):

```sh
just routing-check                       # the corpus schema; no cluster (also: just routing-test)
just routing-run cz                      # every case, through the public iris-bff, as the case's persona
just routing-run cz --shadow             # + every FAST answer re-asked on the LLM lane (below)
uv run scripts/routing-run.py check --core cz --core us   # every validation's core SQL on both worlds
uv run scripts/routing-run.py report results-cz.json results-us.json > report.md   # cs/en side by side
```

A run writes `results-<world>.json` + `report.md` to `--out`. `baselines/<date>-<world>.json` is a run
kept for comparison. Exit 0 = no `FAIL` / `ERROR`.

## The case — `cases/<id>.case.yaml`

```yaml
id: a1-1-marketplace-by-month        # == the filename stem; sorted ids are the run order
title: Marketplace revenue 2025 by month — the opening question
act: "1.1"                           # the demo script's step, if it is one
shape: grain                         # what the question exercises; the shadow report groups by it
question:
  cs: Jaké byly tržby z tržiště v roce 2025 po měsících?
  en: What was marketplace revenue in 2025 by month?
persona: analyst                     # analyst | dc_manager → personas.yaml → marketa/maya, petr/sam
expected_route: FAST                 # FAST | LLM | ASK | REFUSE — the same in both worlds (C-9·2)
expected_reason: PRIOR_VIEW          # LLM only, optional: the fall-through reason's prefix (C-1·3); or {cs: …, en: …}
validation: marketplace-2025-by-month.yaml   # under validation/; none = the route is the assertion
session: a4                          # optional: cases of one session run in one Iris session, in id order
resume: {pick: {cs: místo, en: place}}   # instead of a question: answer the previous turn's ask
xfail: {en: "ttr-server#152 — …"}    # a deviation with a FILED issue: XFAIL, not FAIL; XPASS when fixed
notes: |
  …
```

Routes are read from the turn's protocol (`turnResolution.route`): `ROUTE_FAST_PATH` = FAST (the
query door, 0 LLM calls), `ROUTE_LLM_COMPOSE` = LLM (the composer wrote the query or picked a saved
one), `ROUTE_ASK` = ASK, `ROUTE_REFUSAL` = REFUSE.

## The validation — `validation/<name>.yaml`

```yaml
core: |                              # world-NEUTRAL SQL: keys, never names (warehouse 5 = Brno DC = Memphis DC)
  SELECT d.d_moy AS month, SUM(cs.cs_ext_sales_price) AS revenue
  FROM catalog_sales cs JOIN date_dim d ON cs.cs_sold_date_sk = d.d_date_sk
  WHERE d.d_year = 2025 GROUP BY d.d_moy
params: {cz: {term: Televizor}, us: {term: Television}}   # only for a literal the user typed ({term})
assert:
  row_count: 12                      # or {min: 1, max: 15}
  row_set: {keys: [month], value: revenue, tolerance: 0.001}   # every core row is in the answer
  scalar: {value: aov, tolerance: 0.002, scale: [1, 100]}      # one figure, in a cell or in the prose
  first_row: {keys: [dc]}            # the answer's first row is the core's first row
  empty: true                        # no rows (one all-NULL aggregate row counts as none)
  text_contains: {cs: "…", en: "…"}  # the headline/text says it (rights sentences, refusals)
```

`core` runs once per case, as `hartland_<world>_readonly`, with `{reference_date}` (UTC today, or
`--reference-date`) for relative periods. Matching ignores column NAMES — the door says
`ext_sales_price`, the LLM says `revenue` — and looks for the key values and the figure in the row's
cells. `row_set` takes one answer row per core row unless `pop: false` (a pivoted answer).

## The shadow (`--shadow`, LR-6)

For every case that answered on the FAST path, the runner asks the same question straight at golem
with `X-Golem-Force-Route: llm-compose` — honoured only where golem runs with
`GOLEM_EVAL_FORCE_ROUTE=true` (kantheon#181; the protocol then reads `EVAL_FORCED:llm-compose`) — and
scores the LLM's answer against the same validation: `AGREE`, `DOOR_WRONG`, `LLM_WRONG`,
`BOTH_WRONG`, or `NOT_HONOURED` (the flag is off). The per-shape table is the evidence that a shape
may stay on the door, or may join it (G5).

## What is in it

| group | cases | from |
|---|---|---|
| `a1-*` … `a6-*`, `r*` | every question of the demo script (Acts 1–6 + the reserve) | the local demo script (`design/demo-golem-261007.md`, not committed) |
| `p-*` | one example question per saved query (`q.hartland.*`, 17) | `model/queries/q_hartland.ttrm` |
| `e*` | the mention-homonymy catalogue E1–E9 („prodejna“ / store) | MH design §catalogue |
| `n*` | the six shapes the door must refuse with a named reason (compare, ratio, avg, last, two periods, an elliptic follow-up) | contracts C-1·3 |

Personas and their passwords come from the realm (olymp `platform/auth/keycloak/overlays/hartland/realm`);
set `HARTLAND_DEMO_PASSWORD` or pass `--realm-file`.
