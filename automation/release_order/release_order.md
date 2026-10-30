# Releasing a placed order

Every placed order is checked before it is released for shipping.

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

Consider every order in state `placed` or `held`.

```sql candidates placed_orders(out orders) target erp
        SELECT o.order_number, o.customer, o.channel, o.fulfilling_warehouse, o.value, o.placed_date, o.state
        FROM   er.entity.order o
        WHERE  o.state IN ('placed', 'held')
```

An order passes when all three checks pass:

1. **Stock.** Every line of the order can be covered from the fulfilling distribution center's current
   on-hand quantity, and the center has no outage on the day.

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

2. **Prices.** The unit price of every line matches the price list of the order's channel — or, when the customer
   has an individual price for the item, that individual price — within a tolerance of 0.01. The parameter
   `tolerance` names this allowed price difference.

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

3. **Receivables.** The customer has no open invoice past its due date.

```sql context overdue(in orders, out rows) target erp
        SELECT o.order_number, i.invoice_id, i.due, i.amount - i.paid AS open_amount
        FROM   orders o JOIN er.entity.invoice i ON i.customer = o.customer
        WHERE  i.status = 'open' AND i.due < :as_of
```

An order that passes is released. An order that fails the stock or the price check is held for **Sales**, who
receive the list of lines with the shortfall or the price difference. An order that fails the receivables check
is held for **Accounts Receivable**, who receive the list of overdue invoices. An order may be held for both.

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

Releasing an order above 50 000 needs a confirmation by the sales manager. The parameter
`confirmation_threshold` names this limit; a confirmation that is not received within two working days holds
the order for Sales.

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

Held orders are re-checked every morning until they are released or cancelled. Sales and AR receive one
message per morning with all their held orders; a single order can also be checked on request, when the
order is placed.
