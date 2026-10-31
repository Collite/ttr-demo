# Oslovení neaktivních zákazníků

## O čem recept rozhoduje

- `premium`: lapsed for {quiet_months} months, a top income band
- `standard`: lapsed for {quiet_months} months

## Co čte

- Zákazník (`er.entity.customer`)
- Demografie domácnosti (`er.entity.household_demographics`)
- Příjmové pásmo (`er.entity.income_band`)
- Objednávka (`er.entity.order`)
- Win-back e-mail (`er.entity.winback_mail`)

## Co dělá

- `offer.premium` → `emit`: `customer` = `sk`, `offer` = `"premium"`, `to` = `email`. poslal by zákazníkovi {customer} win-back nabídku {offer}
- `offer.standard` → `emit`: `customer` = `sk`, `offer` = `"standard"`, `to` = `email`. poslal by zákazníkovi {customer} win-back nabídku {offer}
- `offer.premium` → `record`: `customer` = `sk`, `offer` = `"premium"`. zaznamenal by win-back e-mail zákazníkovi {customer}
- `offer.standard` → `record`: `customer` = `sk`, `offer` = `"standard"`. zaznamenal by win-back e-mail zákazníkovi {customer}

## Parametry

- Období bez objednávky (měsíce) (`quiet_months`) = `12` (int)
- Objednávky před obdobím bez objednávky (`active_orders`) = `4` (int)
- Interval win-back e-mailů (`mail_window`) = `92` (days)

## Režim

`per-candidate`
