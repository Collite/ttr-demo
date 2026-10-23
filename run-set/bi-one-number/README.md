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
  - id: superset-tile
    via: superset
    pending: "S4.2 T5 — …"               # declared, not run yet
```

- **edge**: the statement through the Flight edge (`flight.hartland.collite.cz`), as the persona, on
  `hartland_<world>`. The SQL groups by the DC; the number is the `dc` row's `value`.
- **iris**: the question through the public iris-bff as the persona (the routing runner's client). The number is
  `value`'s column, summed over the answer's rows. `pattern` asserts which saved query answered.
- **superset**: S4.2 T5 adds the tile's read through the Superset API (the chart's data endpoint).

The Iris legs need the world the cluster serves (olymp `just world <us|cz>`); the edge legs read either world. Persona
passwords come from the realm, as for the routing corpus: `HARTLAND_DEMO_PASSWORD` or `--realm-file`.

## Not in a nightly yet

hartland runs no nightly. The routing nightly is collite-o1's, and it is suspended until that cluster runs the
hartland stack (olymp `clusters/collite-o1/platform/routing-nightly`). When it resumes, this run is one more line in
its script: two Iris turns and two edge reads, about a minute.
