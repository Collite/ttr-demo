# Obligation past due

Alert operations when an open obligation is more than one working day past its due date. The automation service owns the obligation ledger; the authoring stub remains until Server P4 serves its operational package. Golden cases remain seeds.

```ttrp preamble
uses world "hartland.worlds.demo"
import hartland.automation.*
```

```ttrp
recipe {
key:        obligation.id
    as of:      now
    parameters: []
    document:   "obligation-due-passed.md"
}
```

Consider obligations in state open, overdue or reopened whose due date has passed.

```ttrp
candidates past_due(out obligations) target automation """sql
        SELECT ob.id, ob.recipe, ob.entity, ob.key, ob.kind, ob.due, ob.state
        FROM   er.entity.obligation ob
        WHERE  ob.state IN ('open', 'overdue', 'reopened') AND ob.due < :as_of
    """
```

Calculate working days between the due date and the run instant using the calendar (D-82).

```ttrp
context lateness(in obligations, out rows) target automation {
        obligations -> calc(days_late = working_days(between: due, and: :as_of))
                    -> select(id, kind, entity, key, due, days_late)
                    -> rows
    }
```

Alert only after more than one working day has passed. The first working day is a grace day and produces no verdict; the hourly program records a protocol only when an alert route fires (D-80).

```ttrp
decision overdue(in obligations, in lateness) {
        v = obligations -> join(right: lateness, kind: left, on: left.id = right.id)
        v -> switch {
            late: days_late > 1   because: "{kind} for {entity} {key}, due {due}, {days_late} working days late"   detail: lateness
            else: none                                               // inside its grace day — no verdict, no protocol (D-80)
        }
    }
```

Notify the operations role with the obligation kind, entity, key, due date and lateness details. This document does not enable an ops deployment.

```ttrp
actions {
        overdue.late -> notify { who: role.ops, detail: lateness }
    }
```
