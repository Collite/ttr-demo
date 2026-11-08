# Uvolnění pořízené objednávky

## O čem recept rozhoduje

- `hold_sales`: stock shortfall or price difference (podrobnosti: `shortfall`, `price_differences`)
- `hold_ar`: overdue invoices (podrobnosti: `overdue`)
- `release_confirmed`: all checks passed; above the confirmation threshold
- `release`: all checks passed

## Co čte

- Individuální cena (`er.entity.customer_price`)
- Stavy zásob (`er.entity.inventory`)
- Faktura (`er.entity.invoice`)
- Objednávka (`er.entity.order`)
- Ceník (`er.entity.price_list`)
- Řádek objednávky (`er.entity.sales_line`)
- Výpadek skladu (`er.entity.warehouse_outage`)

## Co dělá

- `verdict.release` → `release`: `order` = `order_number`. uvolnil by objednávku {order}
- `verdict.release_confirmed` → `release_confirmed`: `order` = `order_number`, `value` = `value`. požádal by vedoucího prodeje o potvrzení uvolnění objednávky {order} ({value})
- `verdict.hold_sales` → `hold`: `department` = `"Sales"`, `order` = `order_number`. pozastavil by objednávku {order} pro oddělení {department}
- `verdict.hold_sales` → `notify`: `detail` = `shortfall, price_differences`, `who` = `role.sales`. upozornil by {who}, řádků: {detail.count}
- `verdict.hold_ar` → `hold`: `department` = `"AR"`, `order` = `order_number`. pozastavil by objednávku {order} pro oddělení {department}
- `verdict.hold_ar` → `notify`: `detail` = `overdue`, `who` = `role.ar`. upozornil by {who}, řádků: {detail.count}

## Parametry

- Cenová tolerance (`tolerance`) = `0.01` (decimal)
- Limit pro potvrzení (`confirmation_threshold`) = `50000` (decimal)

## Režim

`per-candidate`
