# Superset dashboards — the demo's BI content

The two dashboards of the BI demo, in both worlds, as Superset bundles (BI-4 · contract C-23). Git is their source:
a merge here puts them into the cluster's Superset, and a fresh estate gets them back the same way.

| dashboard | cz | us | README |
|---|---|---|---|
| DC meltdown — stock-outs | «Výpadky zásob v distribučních centrech» | "DC meltdown — stock-outs" | [dc-meltdown-stockouts/](dc-meltdown-stockouts/README.md) |
| Returns by category | «Reklamace podle kategorie» | "Returns by category" | [returns-by-category/](returns-by-category/README.md) |

## What is here

```
import.yaml                      the worlds (their Superset database uuids) and the bundles per world
kustomization.yaml               GENERATED — every bundle file as one ConfigMap (`just dashboards-kustomize`)
<dashboard>/README.md            purpose, datasets, personas, the numbers each persona should see
<dashboard>/bundle/<world>/      Superset's export of that dashboard in that world, less olymp's files:
  datasets/  charts/  dashboards/
```

A bundle is Superset's own export of the dashboard, through "Export" or `GET /api/v1/dashboard/export/`, with three
changes:
- **No `databases/`, no `metadata.yaml`.** The two databases belong to olymp (`platform/bi/superset`, C-20).
  superset-init-db imports them with fixed uuids, and every dataset here names its database by that uuid
  (`import.yaml`).
- **One bundle per world.** The labels differ: Czech in `cz`, English in `us`. A world is one database (D-2),
  so a dashboard never mixes them.
- **Files named after their object** (`charts/tydny-s-vypadkem-zasob-v-roce-2025.yaml`). Superset names them
  `<title>_<id>.yaml`, and that id changes with every Superset instance.

## How a merge reaches Superset

olymp's `superset-dashboards` Application (`clusters/<cluster>/app-superset-dashboards.yaml`) has two sources:

1. **This directory.** `kustomization.yaml` renders every bundle file into the ConfigMap `superset-dashboards`.
   ConfigMap keys cannot hold `/`, so a key is `<dashboard>.<world>.<kind>.<file>`.
2. **The import Job** (`platform/bi/superset-dashboards`), an ArgoCD PostSync hook.

A merge that changes a bundle changes the ConfigMap. ArgoCD sees it on its repo poll (about 3 minutes, the same
rhythm as the lexicon), syncs, and the Job runs:
1. It re-nests the files.
2. It adds olymp's database files.
3. It runs `superset import-directory --overwrite`.
4. It checks every dataset, chart and dashboard row against its file, by uuid.

`import-directory` exits 0 on a bundle it rejected and keeps the old rows, so the check is what fails the Job. The
check also rewrites each chart's saved query to read the chart's own dataset. An export carries the dataset id of
the Superset it came from, and `GET /api/v1/chart/<id>/data/` would read whatever has that id.

**What an import does:**
- Re-running it is idempotent: it overwrites by uuid.
- A dashboard deleted in Superset comes back on the next sync. A merge here is one. An Admin can also press
  "Sync" on the `superset-dashboards` app in ArgoCD.
- An edit made in Superset's UI and not exported here is overwritten by the next import.
- Removing a bundle here does not delete its dashboard from Superset; delete it in the UI.

## Changing a dashboard

1. In Superset as an Admin (the realm group `admins`), edit the dashboard, then export it ("…" → Download → Export
   to YAML).
2. `just dashboards-unpack <the .zip> <dashboard id> <world>` replaces that bundle.
3. `just dashboards-kustomize`, then `just dashboards-check`.
4. Read the diff, update the dashboard's README numbers if they moved, and open the PR. model-gate runs the check.

The bundles were first authored in a local Superset of the same image (`ghcr.io/collite/superset:6.1.0-ttr<N>`),
whose two databases carry the cluster's uuids and read the hartland edge as the analyst persona. The script is in the
project repo (`platform/features/bi/spikes/bi4/s42_author.py`). Its exports are what is committed here.

## The rules (`just dashboards-check`, in model-gate)

Each rule refuses something the import would get wrong without a word:

- **Every directory here is in `import.yaml`, and every bundle it names exists with a README.**
- **No `databases/` or `metadata.yaml` in a bundle.** Those are olymp's.
- **Every dataset names its world's database uuid.** It reads `obj.query.<q>` or `er.entity.<e>`, and that object
  is a `def query` or `def entity` of `model/`. It is never a virtual (SQL) dataset: the import rewrites a virtual
  dataset's SQL through sqlglot.
- **Every chart's dataset is in the bundle, and the chart has a saved query for its own viz type.**
  `GET /api/v1/chart/<id>/data/` and the one-number check (`run-set/bi-one-number/`) read that saved query.
- **Every dashboard is published, and every chart its layout places is in the bundle.** Superset skips a dashboard
  with a missing chart, and a BI Viewer sees published dashboards only. Every chart is on a dashboard.
- **A uuid means one object everywhere.** The same uuid with other content in another bundle would overwrite it.
- **`kustomization.yaml` is current.**

⚠ Superset allows one dataset per model object per database (`UNIQUE (database_id, schema, table_name)` on
Postgres). A dataset made by hand in the UI over `obj.query.stockouts_monthly_dc` or
`obj.query.returns_monthly_by_category` makes the import fail until it is deleted.
