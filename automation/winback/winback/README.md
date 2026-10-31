# Win-back

## What this recipe decides

- `premium`: lapsed for {quiet_months} months, a top income band
- `standard`: lapsed for {quiet_months} months

## What it reads

- Customer (`er.entity.customer`)
- Household Demographics (`er.entity.household_demographics`)
- Income Band (`er.entity.income_band`)
- Order (`er.entity.order`)
- Win-back Mailing (`er.entity.winback_mail`)

## What it does

- `offer.premium` → `emit`: `customer` = `sk`, `offer` = `"premium"`, `to` = `email`. would mail customer {customer} the {offer} win-back offer
- `offer.standard` → `emit`: `customer` = `sk`, `offer` = `"standard"`, `to` = `email`. would mail customer {customer} the {offer} win-back offer
- `offer.premium` → `record`: `customer` = `sk`, `offer` = `"premium"`. would record the win-back mail to customer {customer}
- `offer.standard` → `record`: `customer` = `sk`, `offer` = `"standard"`. would record the win-back mail to customer {customer}

## Parameters

- Quiet period (months) (`quiet_months`) = `12` (int)
- Orders before the quiet period (`active_orders`) = `4` (int)
- Win-back mail window (`mail_window`) = `92` (days)

## Mode

`per-candidate`
