# Návrhy doobjednávek

## O čem recept rozhoduje

- `propose`: {on_hand} on hand covers less than {cover_target} weeks of {weekly_demand} a week

## Co čte

- Stavy zásob (`er.entity.inventory`)
- Řádek objednávky (`er.entity.sales_line`)

## Co dělá

- `cover.propose` → `propose`: `item` = `item`, `on_hand` = `on_hand`, `proposed_qty` = `cast(proposed_qty as integer)`, `warehouse` = `warehouse`, `weekly_demand` = `round(weekly_demand * 100) * 0.01`. navrhl by doobjednat {proposed_qty} ks položky {item} pro centrum {warehouse}
- `cover.propose` → `ask`: `about` = `warehouse`, `action` = `start { process: "purchasing" }`, `due` = `2 working_days`, `group_by` = `warehouse`, `who` = `role.buyer`. požádal by {who} o schválení {action} pro {about}

## Parametry

- Cílové krytí zásob (týdny) (`cover_target`) = `3` (int)
- Doobjednat na (týdny) (`order_up_to`) = `6` (int)
- Období poptávky (týdny) (`demand_period`) = `8` (int)

## Režim

`per-candidate`
