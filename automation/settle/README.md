# Handling a return request

## What this recipe decides

- `credit_note_issued`: credit note {credit_note_id} issued
- `money_received`: refund paid on {paid_date}
- `goods_shipped`: replacement shipped on {shipped_date}
- `money_overdue`: refund {max_late} working days late (details: `open_obligations`)
- `goods_overdue`: replacement {max_late} working days late (details: `open_obligations`)
- `closed`: settled

## What it reads

- Credit Note (`er.entity.credit_note`)
- Calendar (`er.entity.date_dim`)
- `er.entity.obligation`
- Refund Payment (`er.entity.refund_payment`)
- Replacement Shipment (`er.entity.replacement_shipment`)
- Return Request (`er.entity.return_request`)
- Return Request Line (`er.entity.return_request_line`)

## What it does

- `settlement.credit_note_issued` → `fulfil`: `kind` = `credit_note`, `line` = `line_id`, `to` = `fulfilled`. would mark the {kind} of return line {line} {to}
- `settlement.credit_note_issued` → `expect`: `due` = `working_days(:settlement)`, `kind` = `payment`, `line` = `line_id`. would expect the {kind} of return line {line} by {due}
- `settlement.money_received` → `fulfil`: `kind` = `payment`, `line` = `line_id`, `to` = `fulfilled`. would mark the {kind} of return line {line} {to}
- `settlement.goods_shipped` → `fulfil`: `kind` = `replacement`, `line` = `line_id`, `to` = `fulfilled`. would mark the {kind} of return line {line} {to}
- `settlement.money_overdue` → `task`: `about` = `line_id`, `detail` = `open_obligations`, `who` = `role.finance`. would give {who} a task about {about}
- `settlement.goods_overdue` → `task`: `about` = `line_id`, `detail` = `open_obligations`, `who` = `role.logistics`. would give {who} a task about {about}
- `settlement.closed` → `set_state`: `line` = `line_id`, `to` = `closed`. would set return line {line} to {to}

## Parameters

- Settlement time (`settlement`) = `5` (working_days)

## Mode

`per-candidate`
