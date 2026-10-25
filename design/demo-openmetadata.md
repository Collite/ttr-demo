# Hartland in OpenMetadata — XM-P3

The catalog receives the physical inventory from Postgres and a projection of the
authored model from Veles. Model changes remain reviewed repository changes.

Prerequisites: the paired XM-P3 PRs are merged; Veles0.11.17 and connector0.1.1 are
published; the bot Secret is synced; scans and projection templates exist in
`openmetadata`. Olymp's Stage boundary ends before deployment. The commands below
are the subsequent operator/demo sequence, not evidence that it has run.

The current model contains **36 physical tables/views, 40 ER entities, six measures
and 83 CN concepts**. `dbo` is a model handle; the physical Postgres schema is
`public`. Both `pg-hartland-us` and `pg-hartland-cz` use catalog service `hartland-pg`.
The investment `entry` estate left Hartland; this demo does not recreate it.

## Prepare the catalog

Use the ingestion-bot JWT through `OM_TOKEN` or `OM_TOKEN_FILE`; never paste it into
a command argument, logs or this repository. `OM_URL` accepts the host or `/api`.
The optional landing card is a separate Kantheon PR247; the catalog can be opened
directly at <https://openmetadata.hartland.collite.cz>.

Check that no scheduled/manual scan or projection is already running. `Forbid`
protects scheduled runs only; never overlap manual Jobs on the state PVC. Schedules
are UTC: scan03:00, projection03:30. Times alone are not a dependency gate; for a
demo, wait for the scan to finish before projecting. A delayed/failed scan must be
fixed first. The local-path PVC can remain Pending until the first projection Job
creates its consumer; PVC and CronJob are created in the same Argo wave.

```sh
kubectl --context hartland -n openmetadata get jobs
kubectl --context hartland -n openmetadata create job om-scan-demo \
  --from=cronjob/om-scan-hartland
kubectl --context hartland -n openmetadata wait --for=condition=complete \
  job/om-scan-demo --timeout=30m
kubectl --context hartland -n openmetadata logs job/om-scan-demo
kubectl --context hartland -n openmetadata create job om-project-demo-1 \
  --from=cronjob/om-project-tatrman
kubectl --context hartland -n openmetadata wait --for=condition=complete \
  job/om-project-demo-1 --timeout=30m
kubectl --context hartland -n openmetadata logs job/om-project-demo-1
```

Use fresh Job names when repeating. Inspect failures and warnings; a Job's success
alone does not prove that every expected asset was linked. If a projection ran
before the scan, an unchanged source can return304 and skip missing assets. Use
the fresh-state rebuild below after fixing the scan; do not manufacture a new
source snapshot or delete the primary state claim.

## Show the beats (about 15 minutes)

1. **Scan.** Explore → Databases → `hartland-pg`: show
   `hartland_us.public.store_sales` and its CZ twin. OM owns this inventory;
   table/column types come from Postgres. No profiling or row sampling is configured.
2. **Project.** Open `hartland Entities`, find `store_sales` and its attributes,
   then follow a glossary tag back to the scanned table/column. Show
   `Tatrman.Grounded`, `ttrQname`, the six Metrics and their aggregation text plus
   `ttrAdditivity` (`onHandQty` is semi-additive). “The model stack in the catalog,
   pulled from one projection.” The actual catalog counts belong in XM's tracker
   after execution; authored counts above are the expected inventory.
3. **Deep link — pending Studio deployment.** Inspect the table's `ttrUrl`, e.g.
   `https://studio.hartland.collite.cz/viewer?qname=db.dbo.store_sales`. The rig
   verifies this address and object identity. **Studio was removed from Hartland
   with the investment estate; its replacement is a separate SO effort.** Do not
   present a successful browser round trip until that viewer is deployed and the
   exact URL opens this object. Record this beat as pending if the route is absent.
4. **Concepts.** CN-P6 has landed: open `hartland Concepts`. Show `Item`/Product,
   the role/event structure and English/Czech synonyms. The default glossary
   projection preserves the CN information that the OM2.0.6 RDF importer loses.
5. **Later — XM-P5.** Edit a description in OM → harvest into a proposed one-line
   repository PR. This phase does not implement harvest-back.

## Prove a second sync is a no-op

Run only after the first projection finishes, without editing the model:

```sh
kubectl --context hartland -n openmetadata create job om-project-demo-2 \
  --from=cronjob/om-project-tatrman
kubectl --context hartland -n openmetadata wait --for=condition=complete \
  job/om-project-demo-2 --timeout=30m
export OM_URL=https://openmetadata.hartland.collite.cz
# Set OM_TOKEN_FILE to an existing protected bot-JWT file, or supply OM_TOKEN securely.
just verify-openmetadata
```

The rig has ten read-only checks and exits with its failure count. It pages through
inventory/terms, counts entities separately from attributes, checks retained asset
links, and compares the latest two labeled projection Jobs: same snapshot, both
successful, no overlap, all second-run counters zero. It does not fetch Secrets,
trigger Jobs or test a browser. Threshold overrides are `OM_MIN_TABLES`,
`OM_MIN_ENTITIES`, `OM_MIN_METRICS`; `KUBE_CONTEXT` defaults to `hartland`.

## Reset and rebuild (target: at most five minutes; measure after deployment)

**Bora's operator action.** Stop/wait for any active scan/projection first. Supply
an **admin JWT**, not the admin password or ingestion-bot token. The reset defaults
to a read-only plan, is restricted to this catalog host, and targets only the two
named glossaries and the six model-owned metrics. It retains scanned tables,
custom-property registrations, classifications and the primary state PVC.

```sh
bash scripts/reset-openmetadata.sh             # inspect the exact target list
bash scripts/reset-openmetadata.sh --execute   # explicit destructive demo reset
```

Then restore the **bot** JWT for the rig. Rebuild using a new state filename so an
old URL ETag cannot suppress recreation. This changes only the manual Job's
state argument; the daily CronJob and `/state/last.json` remain intact:

```sh
kubectl --context hartland -n openmetadata create job "om-project-reset-$(date -u +%s)" \
  --from=cronjob/om-project-tatrman --dry-run=client -o json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); a=d["spec"]["template"]["spec"]["containers"][0]["args"]; a[a.index("--state-file")+1]="/state/"+d["metadata"]["name"]+".json"; json.dump(d,sys.stdout)' \
  | kubectl --context hartland -n openmetadata create -f -
```

Wait for completion and inspect its summary. The first reset rebuild can write;
repeat the same Job template/state filename (with a new Job name) to verify a no-op.
Do not run the reset automatically in CI or as a scheduled Job.
