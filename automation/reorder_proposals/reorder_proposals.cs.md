# Návrhy doobjednávek

Pro každé zboží v každém distribučním centru porovnáme poslední známou zásobu s poptávkou z webových objednávek a objednávek tržiště vyřízených daným centrem. Parametry jsou `demand_period` (Období poptávky (týdny), 8), `cover_target` (Cílové krytí zásob (týdny), 3) a `order_up_to` (Doobjednat na (týdny), 6).

Zápis návrhu výslovně mapuje všech osm povinných atributů. Volitelné výchozí hodnoty odvozují záporné bigint ID návrhu ze stejného připnutého běhu a kandidáta i při opakování, zachovají UUID běhu a nastaví stav `proposed`. O krytí rozhoduje nezaokrouhlená týdenní poptávka; až ukládaná poptávka se zaokrouhlí na dvě desetinná místa a navržené množství se převede na celé číslo. Úplný náhled schválení stále vyžaduje podporu Serveru pro vnořenou akci nákupu a lhůtu v pracovních dnech.

```ttrp preamble
uses world "hartland.worlds.demo"
import hartland.*
import hartland.automation.*
```

```ttrp
recipe {
key:        [sales_line.item, sales_line.warehouse]
    as of:      now
    parameters: [cover_target, order_up_to, demand_period]
    document:   "reorder-proposals.md"
}
```

Posuzujeme dvojice zboží a distribučního centra s prodejem v období poptávky.

```ttrp
candidates selling(out pairs) target erp {
        load(er.entity.sales_line)
            -> within(sold_date, last: weeks(:demand_period))
            -> aggregate { group_by: item, warehouse  lines = count(line_no) }
            -> pairs
    }
```

Použijeme nejnovější snímek zásob každé dvojice. Chybějící snímek znamená nulovou zásobu; snímky nikdy nesčítáme.

```ttrp
context on_hand(in pairs, out rows) target erp {
        stock = load(er.entity.inventory) -> latest(by: as_of_date, per: item, warehouse)
        pairs -> join(right: stock, kind: left, on: left.item = right.item and left.warehouse = right.warehouse)
              -> calc(on_hand = coalesce(stock.quantity_on_hand, 0))
              -> select(item, warehouse, on_hand)
              -> rows
    }
```

Průměrnou týdenní poptávku vypočteme z prodejů dané dvojice v období poptávky.

```ttrp
context weekly_demand(in pairs, out rows) target erp {
        pairs -> join(right: load(er.entity.sales_line), kind: inner, on: left.item = right.item and left.warehouse = right.warehouse)
              -> within(sold_date, last: weeks(:demand_period))
              -> aggregate { group_by: item, warehouse  sold = sum(quantity) }
              -> calc(weekly_demand = cast(sold as bigint) * 1.0 / :demand_period)
              -> rows
    }
```

Pokud zásoba nepokrývá cílové období, navrhneme doobjednání rozdílu do cílové úrovně zaokrouhleného nahoru na celý kus. Velikost balení se v Hartlandu nemodeluje; návrh je v kusech stejně jako v certifikovaném pravidle P2.

```ttrp
decision cover(in pairs, in on_hand, in weekly_demand) {
        v = pairs -> join(right: on_hand,       kind: left, on: left.item = right.item and left.warehouse = right.warehouse)
                  -> join(right: weekly_demand, kind: left, on: left.item = right.item and left.warehouse = right.warehouse)
                  -> calc(proposed_qty = ceil(:order_up_to * weekly_demand - on_hand))
        v -> switch {
            propose: on_hand < :cover_target * weekly_demand
                     because: "{on_hand} on hand covers less than {cover_target} weeks of {weekly_demand} a week"
            else:    none                                       // enough stock — no verdict row (D-80)
        }
    }
```

Před jakýmkoli zápisem zobrazíme tabulku návrhů (C-6). Návrhy čekají na schválení a seskupují se podle centra. Nákupčí centra dostane jeden úkol za skupinu se lhůtou dvou pracovních dnů; schválení zahájí nákupní proces dané skupiny. Nákupní systém zastupuje n8n.

```ttrp
actions {
        cover.propose -> propose { item: item, warehouse: warehouse, on_hand: on_hand, weekly_demand: round(weekly_demand * 100) * 0.01,
                                   proposed_qty: cast(proposed_qty as int) }
        cover.propose -> ask     { who: role.buyer, about: warehouse, action: start { process: "purchasing" },
                                   group_by: warehouse, due: 2 working_days }
    }
```
