# Vyřízení reklamace

## O čem recept rozhoduje

- `credit_note_issued`: credit note {credit_note_id} issued
- `money_received`: refund paid on {paid_date}
- `goods_shipped`: replacement shipped on {shipped_date}
- `money_overdue`: refund {max_late} working days late (podrobnosti: `open_obligations`)
- `goods_overdue`: replacement {max_late} working days late (podrobnosti: `open_obligations`)
- `closed`: settled

## Co čte

- Dobropis (`er.entity.credit_note`)
- Kalendář (`er.entity.date_dim`)
- `er.entity.obligation`
- Úhrada (`er.entity.refund_payment`)
- Náhradní zásilka (`er.entity.replacement_shipment`)
- Reklamace (`er.entity.return_request`)
- Řádek reklamace (`er.entity.return_request_line`)

## Co dělá

- `settlement.credit_note_issued` → `fulfil`: `kind` = `credit_note`, `line` = `line_id`, `to` = `fulfilled`. označil by {kind} k řádku reklamace {line} jako {to}
- `settlement.credit_note_issued` → `expect`: `due` = `working_days(:settlement)`, `kind` = `payment`, `line` = `line_id`. očekával by {kind} k řádku reklamace {line} do {due}
- `settlement.money_received` → `fulfil`: `kind` = `payment`, `line` = `line_id`, `to` = `fulfilled`. označil by {kind} k řádku reklamace {line} jako {to}
- `settlement.goods_shipped` → `fulfil`: `kind` = `replacement`, `line` = `line_id`, `to` = `fulfilled`. označil by {kind} k řádku reklamace {line} jako {to}
- `settlement.money_overdue` → `task`: `about` = `line_id`, `detail` = `open_obligations`, `who` = `role.finance`. zadal by {who} úkol k {about}
- `settlement.goods_overdue` → `task`: `about` = `line_id`, `detail` = `open_obligations`, `who` = `role.logistics`. zadal by {who} úkol k {about}
- `settlement.closed` → `set_state`: `line` = `line_id`, `to` = `closed`. převedl by řádek reklamace {line} do stavu {to}

## Parametry

- Lhůta vyřízení (`settlement`) = `5` (working_days)

## Režim

`per-candidate`
