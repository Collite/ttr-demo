# Reorder proposals

For every product in every distribution center, compare the latest on-hand quantity with demand from web and marketplace orders fulfilled by that center. The parameters are `demand_period` (8 weeks), `cover_target` (3 weeks) and `order_up_to` (6 weeks).

The proposal writer maps all eight required attributes explicitly. Its optional defaults derive a retry-stable negative bigint proposal ID from the pinned run and candidate, retain the run UUID, and set state to `proposed`. Coverage decisions use unrounded weekly demand; only the stored demand is rounded to two decimal places, and proposed quantity is cast to an integer. Full approval preview still needs Server support for the nested purchasing action and working-day duration.

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

Consider the product and center pairs that sold during the demand period.

```ttrp
candidates selling(out pairs) target erp {
        load(er.entity.sales_line)
            -> within(sold_date, last: weeks(:demand_period))
            -> aggregate { group_by: item, warehouse  lines = count(line_no) }
            -> pairs
    }
```

Use the latest stock snapshot for each pair. A missing snapshot counts as zero on hand; snapshots are never added together.

```ttrp
context on_hand(in pairs, out rows) target erp {
        // D-153: latest over the candidates' rows, not the fact
        stock = pairs -> join(right: load(er.entity.inventory), kind: left, on: left.item = right.item and left.warehouse = right.warehouse)
                      -> latest(by: as_of_date, per: item, warehouse)
        stock
              -> calc(on_hand = coalesce(quantity_on_hand, 0))
              -> select(item, warehouse, on_hand)
              -> rows
    }
```

Calculate average weekly demand from the pair’s sales during the demand period.

```ttrp
context weekly_demand(in pairs, out rows) target erp {
        pairs -> join(right: load(er.entity.sales_line), kind: inner, on: left.item = right.item and left.warehouse = right.warehouse)
              -> within(sold_date, last: weeks(:demand_period))
              -> aggregate { group_by: item, warehouse  sold = sum(quantity) }
              -> calc(weekly_demand = cast(sold as bigint) * 1.0 / :demand_period)
              -> rows
    }
```

When stock covers less than the cover target, propose the difference to the order-up-to level, rounded up to a whole unit. Pack sizes are not modelled in Hartland; the proposal is in units, as in the certified P2 rule.

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

Preview the proposal table before any write (C-6). Each proposal also asks the buyer to approve its hand-off to purchasing, within two working days; on approval the process engine calls the purchasing process with the proposal’s stock and demand.

```ttrp
actions {
        cover.propose -> propose { item: item, warehouse: warehouse, on_hand: on_hand, weekly_demand: round(weekly_demand * 100) * 0.01,
                                   proposed_qty: cast(proposed_qty as int) }
        cover.propose -> handoff { process: "purchasing", rows: on_hand, weekly_demand }   // approval on the action (by the buyer); was ask … action: start
    }
```
