# run-set/bi-one-number — one number, read on every path (BI-4, contracts C-25)

The BI demo's "one number three times": the same figure on the Superset tile, in Iris, and in the saved query. A case
names the figure (`expect`), an oracle SQL on the world DB, and the legs, each a path a viewer can read it from. Every
leg must give `expect`, and so must the oracle; one leg that differs is a red run. The number is DC 5's stock-out
weeks in 2025 (⚑BI-4-A, Bora 2026-10-22): 17, in both worlds.

Run by `scripts/bi-one-number.py` (uv: httpx, pyyaml, and ttr-sqlalchemy for the edge legs):

```sh
just bi-one-number-test                  # the runner's own specs and the case schema; no cluster (model-gate CI)
just bi-one-number cz                    # every leg, on the world the cluster serves
just bi-one-number cz --out /tmp/one     # + one-number-<world>.json
```

Exit 0 = every leg that runs gives `expect`. A `pending` leg is listed, not run, and does not redden.

## The case — `<id>.yaml`

```yaml
id: stockout-weeks-dc5-2025              # == the filename stem
expect: 17                               # the figure, frozen with its anchor (the seed's verify-story.sql §3)
dc: 5                                    # the DC key an edge leg's number is read from (warehouse 5 in both worlds)
oracle: ../routing/validation/dc5-stockout-weeks-2025.yaml   # a routing validation: its `core` + `assert.scalar.value`
legs:
  - id: edge-analyst
    via: edge                            # edge | iris | superset
    persona: analyst                     # analyst | dc_manager → ../routing/personas.yaml
    sql: SELECT warehouse, SUM(stockout_weeks) AS stockout_weeks FROM obj.query.stockouts_monthly_dc … GROUP BY warehouse
    value: stockout_weeks                # the number's column (a part of its name: unique, case-insensitive)
    dcs: 5                               # edge only: how many DCs the persona sees, or the list of their keys
  - id: saved-query
    via: iris
    persona: analyst
    question: {cs: …, en: …}             # the world's language asks (cz → cs, us → en)
    pattern: warehouse_stockout_week_count   # iris only, optional: the protocol's sql.patternId must be this
    value: stockout_weeks
  - id: superset-analyst
    via: superset
    persona: analyst
    chart: {cz: 65572edb-…, us: dcdb1d8e-…}   # superset only: the tile per world, a big-number chart of dashboards/
    value: stockout_weeks_sum            # the chart's metric
  - id: some-later-leg
    via: iris
    pending: "what it waits for"         # any leg: declared, not run, does not redden
```

- **edge**: the statement through the Flight edge (`flight.hartland.collite.cz`), as the persona, on
  `hartland_<world>`. The SQL groups by the DC; the number is the `dc` row's `value`.
- **iris**: the question through the public iris-bff as the persona (the routing runner's client). The number is
  `value`'s column, summed over the answer's rows. `pattern` asserts which saved query answered.
- **superset**: the tile as the persona sees it. The runner signs in at `superset.hartland.collite.cz` through
  Keycloak (the `superset` client's form) and finds the chart by its uuid. It reads the chart's saved query through
  `GET /api/v1/chart/<id>/data/`. The first read of a database answers `OAUTH2_REDIRECT`; the runner follows that SSO
  hop and reads again with the viewer's own per-database token. The schema check holds the uuid to a big-number
  chart of the world's bundle under `dashboards/`, so a re-authored tile cannot leave the case pointing at nothing.

The Iris legs need the world the cluster serves (olymp `just world <us|cz>`); the edge and Superset legs read
either world (one Superset database each). Persona
passwords come from the realm, as for the routing corpus: `HARTLAND_DEMO_PASSWORD` or `--realm-file`.

## Not in a nightly yet

hartland runs no nightly. The routing nightly is collite-o1's, and it is suspended until that cluster runs the
hartland stack (olymp `clusters/collite-o1/platform/routing-nightly`). When it resumes, this run is one more line in
its script: two Iris turns, two edge reads and two Superset reads, about a minute.
