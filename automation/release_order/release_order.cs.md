# Uvolnění pořízené objednávky

Každou pořízenou objednávku zkontrolujeme před uvolněním k expedici.

```ttrp preamble
uses world "hartland.worlds.demo"
import hartland.*
import hartland.automation.*
```

```ttrp
recipe {
key:        order.order_number
    as of:      now
    parameters: [tolerance, confirmation_threshold]
    document:   "releasing-a-placed-order.md"
}
```

Posuzujeme každou objednávku ve stavu `placed` nebo `held`.

```sql candidates placed_orders(out orders) target erp
        SELECT o.order_number, o.customer, o.channel, o.fulfilling_warehouse, o.value, o.placed_date, o.state
        FROM   er.entity.order o
        WHERE  o.state IN ('placed', 'held')
```

Objednávka projde, pokud vyhoví všem třem kontrolám:

1. **Zásoby.** Aktuální zásoba distribučního centra, které objednávku vyřizuje, pokryje každou její položku a centrum nemá v daný den výpadek.

```ttrp
context shortfall(in orders, out rows) target erp {
        lines = orders -> join(right: load(er.entity.sales_line), kind: inner, on: relation rel_order_line)
        stock = load(er.entity.inventory) -> latest(by: as_of_date, per: item, warehouse)
        out_  = load(er.entity.warehouse_outage) -> filter(from_date <= :as_of and to_date >= :as_of)
        lines -> join(right: stock, kind: left, on: left.item = right.item and left.warehouse = right.warehouse)
              -> join(right: out_,  kind: left, on: left.warehouse = right.warehouse)
              -> calc(on_hand = coalesce(stock.quantity_on_hand, 0), outage = (out_.warehouse is not null))
              -> filter(outage or on_hand < quantity)
              -> select(order_number, line_no, item, quantity, on_hand, outage, short = quantity - on_hand)
              -> rows
    }
```

2. **Ceny.** Jednotková cena každé položky odpovídá ceníku prodejního kanálu objednávky, případně individuální ceně zákazníka pro dané zboží, s tolerancí 0,01. Parametr `tolerance` (Cenová tolerance) určuje povolený rozdíl.

```sql context price_differences(in orders, out rows) target erp
        WITH l AS (
            SELECT s.order_number, s.line_no, s.item, s.unit_price, o.customer, o.channel, o.placed_date
            FROM   orders o JOIN er.entity.sales_line s ON s.order_number = o.order_number
        ),
        applicable AS (
            SELECT l.order_number, l.line_no, COALESCE(cp.price, pl.price) AS price
            FROM   l
            LEFT JOIN er.entity.customer_price cp ON cp.item = l.item AND cp.customer = l.customer
                                                 AND cp.valid_from <= l.placed_date AND (cp.valid_to IS NULL OR cp.valid_to >= l.placed_date)
            LEFT JOIN er.entity.price_list     pl ON pl.item = l.item AND pl.channel = l.channel
                                                 AND pl.valid_from <= l.placed_date AND (pl.valid_to IS NULL OR pl.valid_to >= l.placed_date)
        )
        SELECT l.order_number, l.line_no, l.item, l.unit_price, a.price AS list_price
        FROM   l JOIN applicable a ON a.order_number = l.order_number AND a.line_no = l.line_no
        WHERE  a.price IS NULL OR ABS(l.unit_price - a.price) > :tolerance
```

3. **Pohledávky.** Zákazník nemá žádnou neuhrazenou fakturu po splatnosti.

```sql context overdue(in orders, out rows) target erp
        SELECT o.order_number, i.invoice_id, i.due, i.amount - i.paid AS open_amount
        FROM   orders o JOIN er.entity.invoice i ON i.customer = o.customer
        WHERE  i.status = 'open' AND i.due < :as_of
```

Vyhovující objednávku uvolníme. Při nedostatku zásob nebo rozdílu v ceně ji pozastavíme pro **obchodní oddělení**, které obdrží seznam dotčených položek. Při neuhrazených pohledávkách ji pozastavíme pro **správu pohledávek**, která obdrží seznam faktur po splatnosti. Objednávka může být pozastavena pro obě oddělení současně.

```ttrp
decision verdict(in orders, in shortfall, in price_differences, in overdue) {
        n_short = shortfall         -> aggregate { group_by: order_number  n_short = count(line_no) }
        n_price = price_differences -> aggregate { group_by: order_number  n_price = count(line_no) }
        n_due   = overdue           -> aggregate { group_by: order_number  n_due   = count(invoice_id) }
        v = orders -> join(right: n_short, kind: left, on: left.order_number = right.order_number)
                   -> join(right: n_price, kind: left, on: left.order_number = right.order_number)
                   -> join(right: n_due,   kind: left, on: left.order_number = right.order_number)
                   -> calc(n_short = coalesce(n_short, 0), n_price = coalesce(n_price, 0), n_due = coalesce(n_due, 0))
        v -> switch {
            mode: overlapping
            hold_sales:        n_short > 0 or n_price > 0
                               because: "stock shortfall or price difference"   detail: shortfall, price_differences
            hold_ar:           n_due > 0
                               because: "overdue invoices"                       detail: overdue
            release_confirmed: n_short = 0 and n_price = 0 and n_due = 0 and value > :confirmation_threshold
                               because: "all checks passed; above the confirmation threshold"
            release:           n_short = 0 and n_price = 0 and n_due = 0 and value <= :confirmation_threshold
                               because: "all checks passed"
        }
    }
```

Uvolnění objednávky nad 50 000 vyžaduje potvrzení vedoucího prodeje. Parametr `confirmation_threshold` (Limit pro potvrzení) určuje tuto hranici. Pokud potvrzení nepřijde do dvou pracovních dnů, objednávku pozastavíme pro obchodní oddělení.

```ttrp
actions {
        verdict.release           -> release { order: order_number }
        verdict.release_confirmed -> ask     { who: role.sales_manager, about: order_number, action: release,
                                               due: 2 working_days, on_due: hold { order: order_number, department: "Sales" } }
        verdict.hold_sales        -> hold    { order: order_number, department: "Sales" }
        verdict.hold_sales        -> notify  { who: role.sales, detail: shortfall, price_differences }
        verdict.hold_ar           -> hold    { order: order_number, department: "AR" }
        verdict.hold_ar           -> notify  { who: role.ar, detail: overdue }
    }
```

Pozastavené objednávky kontrolujeme každé ráno až do uvolnění nebo zrušení. Obchodní oddělení a správa pohledávek dostávají každé ráno jednu zprávu se všemi svými pozastavenými objednávkami. Jednotlivou objednávku lze na vyžádání zkontrolovat i při jejím pořízení.
