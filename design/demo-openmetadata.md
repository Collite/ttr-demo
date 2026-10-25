# Hartland in OpenMetadata — XM-P3

The catalog receives the physical inventory from Postgres and a projection of the
authored model from Veles. Model changes remain reviewed repository changes.

Prerequisites: the paired XM-P3 PRs are merged; Veles0.11.17 and connector0.1.2 are
published; the bot Secret is synced; the scan/projection Job template exists in
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

Check that no scheduled/manual projection is running. `Forbid` protects scheduled
runs only; never overlap manual Jobs on the state PVC. The03:30UTC Job runs
`scan-us`, then `scan-cz` as initContainers before `project`. A failed scan fails
the Job and prevents projection. The3600s deadline covers the whole sequence;
measure the first manual run before tuning it. local-path can keep the PVC Pending
until the first Job creates its consumer; PVC and CronJob share the same Argo wave.

```sh
kubectl --context hartland -n openmetadata get jobs
kubectl --context hartland -n openmetadata create job om-project-demo \
  --from=cronjob/om-project-tatrman
kubectl --context hartland -n openmetadata wait --for=condition=complete \
  job/om-project-demo --timeout=65m
# List pods, then inspect the Succeeded pod (a Job may have a failed first attempt).
kubectl --context hartland -n openmetadata get pods -l job-name=om-project-demo
kubectl --context hartland -n openmetadata logs pod/<succeeded-pod> -c project
```

Use fresh Job names when repeating. Inspect both initContainer logs on a failed
scan and the main summary on success. Warnings mean incomplete projection;
connector0.1.2 preserves the previous state so a later run retries skipped assets.
Do not manufacture source snapshots or delete the primary state claim.

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

Run the following command twice, waiting for each named Job to complete before
starting the next, without editing the model. Each unique Job name selects its own
fresh state file, forcing a real full sync against OM instead of an HTTP304.
Both summaries must say `not_modified: false`; all second-run counters must be zero.

```sh
kubectl --context hartland -n openmetadata create job "om-project-pair-$(date -u +%s)" \
  --from=cronjob/om-project-tatrman --dry-run=client -o json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); a=d["spec"]["template"]["spec"]["containers"][0]["args"]; a[a.index("--state-file")+1]="/state/"+d["metadata"]["name"]+".json"; json.dump(d,sys.stdout)' \
  | kubectl --context hartland -n openmetadata create -f -
# Wait for the name printed above; repeat the command only after completion.
kubectl --context hartland -n openmetadata wait --for=condition=complete \
  job/<printed-job-name> --timeout=65m
export OM_URL=https://openmetadata.hartland.collite.cz
# Set OM_TOKEN_FILE to an existing protected bot-JWT file, or supply OM_TOKEN securely.
just verify-openmetadata
```

The rig has ten read-only checks and exits with its failure count. It pages through
inventory/terms, counts entities separately from attributes, checks retained asset
links, and compares the latest two labeled projection Jobs: same snapshot, both
successful real syncs (`not_modified: false`), no overlap, all second-run counters
zero. A missing marker requires connector >=0.1.2;304 Jobs cannot prove idempotency. It does not fetch Secrets,
trigger Jobs or test a browser. Threshold overrides are `OM_MIN_TABLES`,
`OM_MIN_ENTITIES`, `OM_MIN_METRICS`; `KUBE_CONTEXT` defaults to `hartland`.

## Reset and rebuild (target: at most five minutes; measure after deployment)

**Bora's operator action.** Stop/wait for any active scan/projection first. Supply
an **admin JWT**, not the admin password or ingestion-bot token. The reset defaults
to a read-only plan, is restricted to this catalog host, and targets only the two
named glossaries and metrics owned by the `md.measure.` qname prefix. It retains scanned tables,
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

Wait for completion and inspect its summary. Run the same command again: the new
Job name creates a new state file and a real full sync. Its summary must have
`not_modified: false` and all counters zero. Each reset run leaves an
`/state/om-project-reset-<ts>.json` on the PVC (the acceptance pair similarly leaves
`om-project-pair-<ts>.json`). After collecting evidence, with no other Jobs running,
clean only those auxiliary files using a temporary PVC consumer (not the primary state):

```sh
kubectl --context hartland -n openmetadata run "om-state-cleanup-$(date -u +%s)" --image=busybox:1.37.0 --restart=Never --rm -i --overrides='{"spec":{"securityContext":{"runAsUser":1000,"runAsGroup":1000,"runAsNonRoot":true,"fsGroup":1000},"automountServiceAccountToken":false,"containers":[{"name":"cleanup","image":"busybox:1.37.0","command":["sh","-c","rm -f /state/om-project-reset-*.json /state/om-project-pair-*.json"],"volumeMounts":[{"name":"state","mountPath":"/state"}]}],"volumes":[{"name":"state","persistentVolumeClaim":{"claimName":"om-project-state"}}]}}'
```

Do not run the reset automatically in CI or as a scheduled Job.
