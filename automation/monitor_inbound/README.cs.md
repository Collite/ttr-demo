# Vyřízení reklamace

## O čem recept rozhoduje

- `complete`: returned in full (podrobnosti: `receipts`)
- `damaged`: incomplete or damaged return (podrobnosti: `receipts`)
- `expired`: nothing returned after {inbound_close} days
- `remind`: nothing returned after {inbound_reminder} days

## Co čte

- Zákazník (`er.entity.customer`)
- Kalendář (`er.entity.date_dim`)
- `er.entity.monitor_inbound_verdict`
- `er.entity.obligation`
- Příjemka vratky (`er.entity.return_receipt`)
- Reklamace (`er.entity.return_request`)
- Řádek reklamace (`er.entity.return_request_line`)

## Co dělá

- `inbound.complete` → `fulfil`: `kind` = `inbound`, `line` = `line_id`, `to` = `fulfilled`. označil by {kind} k řádku reklamace {line} jako {to}
- `inbound.complete` → `set_state`: `line` = `line_id`, `to` = `goods_received`. převedl by řádek reklamace {line} do stavu {to}
- `inbound.complete` → `expect`: `due` = `working_days(:settlement)`, `kind` = `credit_note`, `line` = `line_id`; když `way = "refund_after_return"`. očekával by {kind} k řádku reklamace {line} do {due}
- `inbound.complete` → `expect`: `due` = `working_days(:settlement)`, `kind` = `replacement`, `line` = `line_id`; když `way = "exchange"`. očekával by {kind} k řádku reklamace {line} do {due}
- `inbound.damaged` → `task`: `about` = `line_id`, `detail` = `receipts`, `who` = `role.customer_care`. zadal by {who} úkol k {about}
- `inbound.expired` → `fulfil`: `kind` = `inbound`, `line` = `line_id`, `to` = `cancelled`. označil by {kind} k řádku reklamace {line} jako {to}
- `inbound.expired` → `set_state`: `line` = `line_id`, `to` = `not_returned`. převedl by řádek reklamace {line} do stavu {to}
- `inbound.remind` → `notify_customer`: `customer` = `customer`, `template` = `"return-reminder"`, `to` = `customer_email`. poslal by zákazníkovi {customer} zprávu {template}

## Parametry

- Upomínka vrácení zboží (`inbound_reminder`) = `14` (days)
- Lhůta pro vrácení zboží (`inbound_close`) = `30` (days)
- Lhůta vyřízení (`settlement`) = `5` (working_days)

## Režim

`per-candidate`
