# Závazek po lhůtě

Upozorníme provoz, pokud je otevřený závazek více než jeden pracovní den po lhůtě. Evidenci závazků vlastní automatizační služba; pomocný model pro tvorbu receptu zůstává do zpřístupnění provozního balíčku v Server P4. Referenční případy zůstávají výchozími daty bez připnutí k běhu.

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

Posuzujeme závazky ve stavu open, overdue nebo reopened s uplynulou lhůtou.

```ttrp
candidates past_due(out obligations) target automation """sql
        SELECT ob.id, ob.recipe, ob.entity, ob.key, ob.kind, ob.due, ob.state
        FROM   er.entity.obligation ob
        WHERE  ob.state IN ('open', 'overdue', 'reopened') AND ob.due < :as_of
    """
```

S pomocí kalendáře vypočteme počet pracovních dnů mezi lhůtou a okamžikem běhu (D-82).

```ttrp
context lateness(in obligations, out rows) target automation {
        obligations -> calc(days_late = working_days(between: due, and: :as_of))
                    -> select(id, kind, entity, key, due, days_late)
                    -> rows
    }
```

Upozorníme až po více než jednom pracovním dni. První pracovní den je toleranční a nevytváří výsledek; hodinový program zaznamená protokol pouze při aktivaci upozornění (D-80).

```ttrp
decision overdue(in obligations, in lateness) {
        v = obligations -> join(right: lateness, kind: left, on: left.id = right.id)
        v -> switch {
            late: days_late > 1   because: "{kind} for {entity} {key}, due {due}, {days_late} working days late"   detail: lateness
            else: none                                               // inside its grace day — no verdict, no protocol (D-80)
        }
    }
```

Vyrozumíme provozní roli s druhem závazku, entitou, klíčem, lhůtou a podrobnostmi o zpoždění. Tento dokument provozní nasazení nepovoluje.

```ttrp
actions {
        overdue.late -> notify { who: role.ops, detail: lateness }
    }
```
