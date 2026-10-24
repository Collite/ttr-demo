# Reorder proposals

## What this recipe decides

- `propose`: {on_hand} on hand covers less than {cover_target} weeks of {weekly_demand} a week

## What it reads

- Inventory Snapshots (`er.entity.inventory`)
- Order Line (`er.entity.sales_line`)

## What it does

- `cover.propose` → `propose`: `item` = `item`, `on_hand` = `on_hand`, `proposed_qty` = `proposed_qty`, `warehouse` = `warehouse`, `weekly_demand` = `weekly_demand`. would propose reordering {proposed_qty} of item {item} for center {warehouse}
- `cover.propose` → `ask`: `about` = `warehouse`, `action` = `start { process: "purchasing" }`, `due` = `2 working_days`, `group_by` = `warehouse`, `who` = `role.buyer`. would ask {who} to approve {action} for {about}

## Parameters

- Stock cover target (weeks) (`cover_target`) = `3` (int)
- Order up to (weeks) (`order_up_to`) = `6` (int)
- Demand period (weeks) (`demand_period`) = `8` (int)

## Mode

`per-candidate`
