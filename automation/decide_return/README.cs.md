# Vyřízení reklamace

## O čem recept rozhoduje

- `reject_not_ours`: not bought here
- `reject_late`: delivered more than {return_window} days ago
- `reject_abuse`: return share {share} above the limit
- `to_customer_care`: request above the care threshold
- `refund_no_return`: small value, {reason}
- `replacement_no_return`: {reason}, replacement on stock
- `exchange`: requested variant on stock
- `refund_after_return`: goods back, then the money

## Co čte

- Zákazník (`er.entity.customer`)
- Stavy zásob (`er.entity.inventory`)
- Objednávka (`er.entity.order`)
- Reklamace (`er.entity.return_request`)
- Řádek reklamace (`er.entity.return_request_line`)
- Řádek objednávky (`er.entity.sales_line`)

## Co dělá

- `way.reject_not_ours`, `way.reject_late`, `way.reject_abuse` → `set_state`: `line` = `line_id`, `to` = `rejected`. převedl by řádek reklamace {line} do stavu {to}
- `way.reject_not_ours`, `way.reject_late`, `way.reject_abuse` → `notify_customer`: `customer` = `customer`, `template` = `"return-rejected"`. poslal by zákazníkovi {customer} zprávu {template}
- `way.to_customer_care` → `ask`: `about` = `request_number`, `action` = `set_state`, `due` = `3 working_days`, `group_by` = `request_number`, `who` = `role.customer_care`. požádal by {who} o schválení {action} pro {about}
- `way.refund_no_return` → `set_state`: `line` = `line_id`, `to` = `settling`, `way` = `refund_no_return`. převedl by řádek reklamace {line} do stavu {to}
- `way.refund_no_return` → `expect`: `due` = `working_days(:settlement)`, `kind` = `credit_note`, `line` = `line_id`. očekával by {kind} k řádku reklamace {line} do {due}
- `way.replacement_no_return` → `set_state`: `line` = `line_id`, `to` = `settling`, `way` = `replacement_no_return`. převedl by řádek reklamace {line} do stavu {to}
- `way.replacement_no_return` → `expect`: `due` = `working_days(:settlement)`, `kind` = `replacement`, `line` = `line_id`. očekával by {kind} k řádku reklamace {line} do {due}
- `way.exchange` → `set_state`: `line` = `line_id`, `to` = `awaiting_goods`, `way` = `exchange`. převedl by řádek reklamace {line} do stavu {to}
- `way.refund_after_return` → `set_state`: `line` = `line_id`, `to` = `awaiting_goods`, `way` = `refund_after_return`. převedl by řádek reklamace {line} do stavu {to}
- `way.exchange`, `way.refund_after_return` → `expect`: `due` = `days(:inbound_reminder)`, `kind` = `inbound`, `line` = `line_id`. očekával by {kind} k řádku reklamace {line} do {due}
- `way.exchange`, `way.refund_after_return` → `notify_customer`: `customer` = `customer`, `template` = `"return-instructions"`. poslal by zákazníkovi {customer} zprávu {template}

## Parametry

- Lhůta pro vrácení (`return_window`) = `30` (days)
- Limit podílu vratek (`abuse_share`) = `0.40` (decimal)
- Limit nízké hodnoty (`small_value`) = `15` (decimal)
- Limit pro péči o zákazníky (`care_threshold`) = `500` (decimal)
- Lhůta vyřízení (`settlement`) = `5` (working_days)
- Upomínka vrácení zboží (`inbound_reminder`) = `14` (days)

## Režim

`per-candidate`
