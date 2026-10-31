# Handling a return request

## What this recipe decides

- `complete`: returned in full (details: `receipts`)
- `damaged`: incomplete or damaged return (details: `receipts`)
- `expired`: nothing returned after {inbound_close} days
- `remind`: nothing returned after {inbound_reminder} days

## What it reads

- Customer (`er.entity.customer`)
- Calendar (`er.entity.date_dim`)
- `er.entity.monitor_inbound_verdict`
- `er.entity.obligation`
- Return Receipt (`er.entity.return_receipt`)
- Return Request (`er.entity.return_request`)
- Return Request Line (`er.entity.return_request_line`)

## What it does

- `inbound.complete` → `fulfil`: `kind` = `inbound`, `line` = `line_id`, `to` = `fulfilled`. would mark the {kind} of return line {line} {to}
- `inbound.complete` → `set_state`: `line` = `line_id`, `to` = `goods_received`. would set return line {line} to {to}
- `inbound.complete` → `expect`: `due` = `working_days(:settlement)`, `kind` = `credit_note`, `line` = `line_id`; when `way = "refund_after_return"`. would expect the {kind} of return line {line} by {due}
- `inbound.complete` → `expect`: `due` = `working_days(:settlement)`, `kind` = `replacement`, `line` = `line_id`; when `way = "exchange"`. would expect the {kind} of return line {line} by {due}
- `inbound.damaged` → `task`: `about` = `line_id`, `detail` = `receipts`, `who` = `role.customer_care`. would give {who} a task about {about}
- `inbound.expired` → `fulfil`: `kind` = `inbound`, `line` = `line_id`, `to` = `cancelled`. would mark the {kind} of return line {line} {to}
- `inbound.expired` → `set_state`: `line` = `line_id`, `to` = `not_returned`. would set return line {line} to {to}
- `inbound.remind` → `notify_customer`: `customer` = `customer`, `template` = `"return-reminder"`, `to` = `customer_email`. would send customer {customer} the {template} message

## Parameters

- Return reminder (`inbound_reminder`) = `14` (days)
- Return deadline (`inbound_close`) = `30` (days)
- Settlement time (`settlement`) = `5` (working_days)

## Mode

`per-candidate`
