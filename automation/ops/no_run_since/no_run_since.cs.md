# Chybějící běh

Upozorníme provoz, pokud plánované nasazení neběželo po dobu dvojnásobku očekávané periody. Jde o recept nad balíčkem `automation.ops`, který je pouze pro čtení (D-72). Pomocný model pro tvorbu receptu zůstává do zpřístupnění balíčku v Server P4; referenční případy zůstávají výchozími daty bez připnutí k běhu.

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

Posuzujeme nasazení s uvedenou periodou plánování.

```ttrp
candidates scheduled(out deployments) target automation """sql
        SELECT d.name, d.recipe, d.schedule, d.period_minutes
        FROM   er.entity.deployment d
        WHERE  d.period_minutes IS NOT NULL
    """
```

Vyhledáme poslední běh každého nasazení. Nasazení, které ještě neběželo, nemá čas posledního běhu.

```ttrp
context last_run(in deployments, out rows) target automation """sql
        SELECT q.name, MAX(r.started_at) AS last_run
        FROM   deployments q LEFT JOIN er.entity.run r ON r.deployment = q.name
        GROUP  BY q.name
    """
```

Upozorníme, pokud běh neexistuje nebo je poslední běh starší než dvojnásobek periody nasazení. Včasný běh nevytváří výsledek; hodinový program zaznamená protokol pouze při aktivaci upozornění (D-80).

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

Vyrozumíme provozní roli s podrobnostmi o posledním běhu. Výraz `minutes(2 * period_minutes)` závislý na řádku nyní vyvolává zdokumentované odmítnutí překladače TTRP-TYP-001; tento dokument provozní nasazení nepovoluje.

```ttrp
actions {
        silence.late -> notify { who: role.ops, detail: last_run }
    }
```
