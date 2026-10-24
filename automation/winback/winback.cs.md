# Oslovení neaktivních zákazníků

Zákazníci, kteří ve dvanácti měsících předcházejících posledním dvanácti měsícům nakoupili alespoň čtyřikrát a v posledních dvanácti měsících nenakoupili, dostanou nabídku k návratu. Parametr `active_orders` (Objednávky před obdobím bez objednávky) je 4 a `quiet_months` (Období bez objednávky (měsíce)) je 12. Parametr `mail_window` (Interval win-back e-mailů) je 92 dnů: nejvýše jeden e-mail za toto klouzavé období (výklad pravidla jednou za čtvrtletí pro demo, D-129).

```ttrp preamble
uses world "hartland.worlds.demo"
import hartland.*
import hartland.automation.*
```

```ttrp
recipe {
key:        customer.sk
    as of:      now
    parameters: [quiet_months, active_orders, mail_window]
    document:   "win-back.md"
}
```

Vyhledáme zákazníky s dostatečným počtem objednávek v předchozím dvanáctiměsíčním období a bez objednávek v období neaktivity.

```ttrp
candidates lapsed(out customers) target erp {
        before = load(er.entity.order)
                 -> within(placed_date, from: :as_of - months(:quiet_months) - months(12), to: :as_of - months(:quiet_months))
                 -> aggregate { group_by: customer  orders_before = count(order_number) }
                 -> filter(orders_before >= :active_orders)
        since  = load(er.entity.order)
                 -> within(placed_date, from: :as_of - months(:quiet_months), to: :as_of)
                 -> aggregate { group_by: customer  orders_since = count(order_number) }
        before -> join(right: since, kind: anti, on: left.customer = right.customer)
               -> join(right: load(er.entity.customer), kind: inner, on: left.customer = right.sk)
               // ttr-core#252 drops the right equality key; carry its equal left customer as sk.
               // Revert after ttr-core#252 lands in the [ttrp] pin.
               -> select(sk = customer, hdemo, orders_before)
               -> customers
    }
```

Zákazníci ve dvou nejvyšších příjmových pásmech domácností dostanou prémiovou nabídku, ostatní standardní.

```ttrp
context band(in customers, out rows) target erp """sql
        WITH households AS (
            SELECT h.sk AS household_id, h.income_band FROM er.entity.household_demographics h
        ), top_bands AS (
            SELECT b.sk AS band_id, -b.lower_bound AS priority FROM er.entity.income_band b ORDER BY priority LIMIT 2
        )
        SELECT q.sk, hd.income_band,
               CASE WHEN t.band_id IS NOT NULL THEN 1 ELSE 0 END AS top_band
        FROM   customers q LEFT JOIN households hd ON hd.household_id = q.hdemo
        LEFT JOIN top_bands t ON t.band_id = hd.income_band
    """
```

Načteme poslední e-mail s nabídkou k návratu v daném intervalu. Recept čte záznamy, které dříve sám zapsal.

```ttrp
context mailed(in customers, out rows) target erp """sql
        SELECT q.sk, MAX(m.mailed_at) AS last_mailed
        FROM   customers q JOIN er.entity.winback_mail m ON m.customer = q.sk
        WHERE  m.mailed_at >= :as_of - :mail_window
        GROUP  BY q.sk
    """
```

Každého nedávno osloveného zákazníka ze seznamu zcela vyřadíme, včetně deseti připravených kontrolních případů. Zbývajícím zákazníkům přiřadíme prémiovou nebo standardní nabídku.

```ttrp
decision offer(in customers, in band, in mailed) {
        v = customers -> join(right: mailed, kind: anti, on: left.sk = right.sk)     // mailed lately: no verdict row
                      -> join(right: band,   kind: left, on: left.sk = right.sk)
        v -> switch {
            mode: exclusive
            premium: top_band = 1   because: "lapsed for {quiet_months} months, a top income band"
            else:    standard       because: "lapsed for {quiet_months} months"
        }
    }
```

E-mail odešle n8n; platforma vypočte seznam zákazníků a zaznamená nabídku. Exportovaný postup používá `emit` pro Send Email a `record` pro zpětný zápis. Program běží měsíčně.

```ttrp
actions {
        offer.premium  -> emit   { customer: sk, offer: "premium" }
        offer.standard -> emit   { customer: sk, offer: "standard" }
        offer.premium  -> record { customer: sk, offer: "premium" }
        offer.standard -> record { customer: sk, offer: "standard" }
    }
```
