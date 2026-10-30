# No run since

Alert operations when a scheduled deployment has not run for twice its expected period. This is a recipe over the read-only `automation.ops` package (D-72). The authoring stub remains until Server P4 serves that package; its golden cases remain seeds.

```ttrp preamble
uses world "hartland.worlds.demo"
import hartland.automation.*
import automation.ops.*
```

```ttrp
recipe {
key:        deployment.name
    as of:      now
    parameters: []
    document:   "no-run-since.md"
}
```

Consider deployments that have a schedule period.

```ttrp
candidates scheduled(out deployments) target automation """sql
        SELECT d.name, d.recipe, d.schedule, d.period_minutes
        FROM   er.entity.deployment d
        WHERE  d.period_minutes IS NOT NULL
    """
```

Look up the latest run of each deployment. A deployment with no run has no last-run timestamp.

```ttrp
context last_run(in deployments, out rows) target automation """sql
        SELECT q.name, MAX(r.started_at) AS last_run
        FROM   deployments q LEFT JOIN er.entity.run r ON r.deployment = q.name
        GROUP  BY q.name
    """
```

Alert if no run exists or the last run is older than twice the deployment’s period. An on-time deployment produces no verdict; the hourly program records a protocol only when an alert route fires (D-80).

```ttrp
decision silence(in deployments, in last_run) {
        v = deployments -> join(right: last_run, kind: left, on: left.name = right.name)
        v -> switch {
            late: last_run is null or last_run < :as_of - minutes(2 * period_minutes)
                  because: "{name} ({schedule}) has not run since {last_run}"   detail: last_run
            else: none                                               // ran in time — no verdict, no protocol (D-80)
        }
    }
```

Notify the operations role with the last-run details. Row-dependent `minutes(2 * period_minutes)` currently has the documented TTRP-TYP-001 compiler refusal; this document does not enable an ops deployment.

```ttrp
actions {
        silence.late -> notify { who: role.ops, detail: last_run }
    }
```
