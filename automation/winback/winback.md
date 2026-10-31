# Win-back

Customers who bought at least four times in the twelve months before the last twelve months, and nothing in the last twelve months, receive a win-back offer. `active_orders` is 4 and `quiet_months` is 12. The `mail_window` is 92 days: at most one win-back mail per customer in that rolling window (the demo’s interpretation of once per quarter, D-129).

The mailing record key uses the **UTC calendar quarter** of the pinned as-of instant (`YYYY-Qn`), in both worlds. Thus 2027-01-01 00:30 in Prague is `2026-Q4`, while 2026-12-31 20:00 at UTC−05:00 is `2027-Q1`. This label does not change the rolling 92-day exclusion. The run UUID and mailing timestamp come from committed Open context, independently of as-of.

```ttrp preamble
uses world "hartland.worlds.demo"
import hartland.*
import hartland.automation.*
```

```ttrp
recipe {
key:        customer.sk
    as of:      now
    parameters: [quiet_months, active_orders, mail_window]
    document:   "win-back.md"
}
```

Find customers with enough orders in the earlier twelve-month window and no orders in the quiet period.

```ttrp
candidates lapsed(out customers) target erp {
        before = load(er.entity.order)
                 -> within(placed_date, from: :as_of - months(:quiet_months) - months(12), to: :as_of - months(:quiet_months))
                 -> aggregate { group_by: customer  orders_before = count(order_number) }
                 -> filter(orders_before >= :active_orders)
        since  = load(er.entity.order)
                 -> within(placed_date, from: :as_of - months(:quiet_months), to: :as_of)
                 -> aggregate { group_by: customer  orders_since = count(order_number) }
        before -> join(right: since, kind: anti, on: left.customer = right.customer)
               -> join(right: load(er.entity.customer), kind: inner, on: left.customer = right.sk)
               // ttr-core#252 drops the right equality key; carry its equal left customer as sk.
               // Revert after ttr-core#252 lands in the [ttrp] pin.
               -> select(sk = customer, hdemo, email, orders_before)
               -> customers
    }
```

Customers in the top two household income bands receive the premium offer; the others receive the standard offer.

```ttrp
context band(in customers, out rows) target erp """sql
        WITH households AS (
            SELECT h.sk AS household_id, h.income_band FROM er.entity.household_demographics h
        ), top_bands AS (
            SELECT b.sk AS band_id, -b.lower_bound AS priority FROM er.entity.income_band b ORDER BY priority LIMIT 2
        )
        SELECT q.sk, hd.income_band,
               CASE WHEN t.band_id IS NOT NULL THEN 1 ELSE 0 END AS top_band
        FROM   customers q LEFT JOIN households hd ON hd.household_id = q.hdemo
        LEFT JOIN top_bands t ON t.band_id = hd.income_band
    """
```

Read the last win-back mail within the mail window. The recipe reads the records it previously wrote.

```ttrp
context mailed(in customers, out rows) target erp """sql
        SELECT q.sk, MAX(m.mailed_at) AS last_mailed
        FROM   customers q JOIN er.entity.winback_mail m ON m.customer = q.sk
        WHERE  m.mailed_at >= :as_of - :mail_window
        GROUP  BY q.sk
    """
```

Exclude every recently mailed customer from the list entirely, including the ten planted exclusions. Assign the premium or standard offer to each remaining customer.

```ttrp
decision offer(in customers, in band, in mailed) {
        v = customers -> join(right: mailed, kind: anti, on: left.sk = right.sk)     // mailed lately: no verdict row
                      -> join(right: band,   kind: left, on: left.sk = right.sk)
        v -> switch {
            mode: exclusive
            premium: top_band = 1   because: "lapsed for {quiet_months} months, a top income band"
            else:    standard       because: "lapsed for {quiet_months} months"
        }
    }
```

n8n sends the mail; the platform computes the customer list and records the offer. The exported workflow uses `emit` for Send Email and `record` for the write-back. The program runs monthly.

```ttrp
actions {
        offer.premium  -> emit   { customer: sk, to: email, offer: "premium" }
        offer.standard -> emit   { customer: sk, to: email, offer: "standard" }
        offer.premium  -> record { customer: sk, offer: "premium" }
        offer.standard -> record { customer: sk, offer: "standard" }
    }
```
