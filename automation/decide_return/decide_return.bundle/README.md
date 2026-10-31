# Handling a return request

## What this recipe decides

- `reject_not_ours`: not bought here
- `reject_late`: delivered more than {return_window} days ago
- `reject_abuse`: return share {share} above the limit
- `to_customer_care`: request above the care threshold
- `refund_no_return`: small value, {reason}
- `replacement_no_return`: {reason}, replacement on stock
- `exchange`: requested variant on stock
- `refund_after_return`: goods back, then the money

## What it reads

- Customer (`er.entity.customer`)
- Inventory Snapshots (`er.entity.inventory`)
- Order (`er.entity.order`)
- Return Request (`er.entity.return_request`)
- Return Request Line (`er.entity.return_request_line`)
- Order Line (`er.entity.sales_line`)

## What it does

- `way.reject_not_ours`, `way.reject_late`, `way.reject_abuse` → `set_state`: `line` = `line_id`, `to` = `rejected`. would set return line {line} to {to}
- `way.reject_not_ours`, `way.reject_late`, `way.reject_abuse` → `notify_customer`: `customer` = `customer`, `template` = `"return-rejected"`, `to` = `customer_email`. would send customer {customer} the {template} message
- `way.to_customer_care` → `ask`: `about` = `request_number`, `action` = `set_state`, `due` = `3 working_days`, `group_by` = `request_number`, `who` = `role.customer_care`. would ask {who} to approve {action} for {about}
- `way.refund_no_return` → `set_state`: `line` = `line_id`, `to` = `settling`, `way` = `refund_no_return`. would set return line {line} to {to}
- `way.refund_no_return` → `expect`: `due` = `working_days(:settlement)`, `kind` = `credit_note`, `line` = `line_id`. would expect the {kind} of return line {line} by {due}
- `way.replacement_no_return` → `set_state`: `line` = `line_id`, `to` = `settling`, `way` = `replacement_no_return`. would set return line {line} to {to}
- `way.replacement_no_return` → `expect`: `due` = `working_days(:settlement)`, `kind` = `replacement`, `line` = `line_id`. would expect the {kind} of return line {line} by {due}
- `way.exchange` → `set_state`: `line` = `line_id`, `to` = `awaiting_goods`, `way` = `exchange`. would set return line {line} to {to}
- `way.refund_after_return` → `set_state`: `line` = `line_id`, `to` = `awaiting_goods`, `way` = `refund_after_return`. would set return line {line} to {to}
- `way.exchange`, `way.refund_after_return` → `expect`: `due` = `days(:inbound_reminder)`, `kind` = `inbound`, `line` = `line_id`. would expect the {kind} of return line {line} by {due}
- `way.exchange`, `way.refund_after_return` → `notify_customer`: `customer` = `customer`, `template` = `"return-instructions"`, `to` = `customer_email`. would send customer {customer} the {template} message

## Parameters

- Return window (`return_window`) = `30` (days)
- Return share limit (`abuse_share`) = `0.40` (decimal)
- Small-value limit (`small_value`) = `15` (decimal)
- Customer care threshold (`care_threshold`) = `500` (decimal)
- Settlement time (`settlement`) = `5` (working_days)
- Return reminder (`inbound_reminder`) = `14` (days)

## Mode

`per-candidate`
