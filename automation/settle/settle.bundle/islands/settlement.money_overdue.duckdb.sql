SELECT "line_id", "request_number", "item", "quantity", "way", "customer", "credit_note_id", "issued_date", "payment_id", "paid_date", "shipment_id", "shipped_date", "max_late", "kinds_open", 'money_overdue' AS "route", 'refund ' || CASE WHEN "max_late" IS NULL THEN '' ELSE CAST("max_late" AS VARCHAR(65536)) END || ' working days late' AS "verdict_reason"
FROM (SELECT "p_202d930b"."line_id", "p_202d930b"."request_number", "p_202d930b"."item", "p_202d930b"."quantity", "p_202d930b"."way", "p_202d930b"."customer", "p_202d930b"."credit_note_id", "p_202d930b"."issued_date", "p_202d930b"."payment_id", "p_202d930b"."paid_date", "p_202d930b"."shipment_id", "p_202d930b"."shipped_date", "t5"."max_late", "t5"."kinds_open"
        FROM "p_202d930b"
            LEFT JOIN (SELECT "t"."line_id", MAX(CASE WHEN "t"."due" IS NULL THEN NULL ELSE COALESCE("t3"."_ttrp_n_n20_0", 0) END) AS "max_late", COUNT("t"."kind") AS "kinds_open"
                FROM (SELECT "p_927a867d"."line_id", "p_53d4630f"."id" AS "obligation_id", "p_53d4630f"."kind", "p_53d4630f"."due"
                        FROM "p_927a867d"
                            INNER JOIN "p_53d4630f" ON "p_53d4630f"."entity" = 'er.entity.return_request_line' AND "p_53d4630f"."key" = '{"line_id":' || CAST("p_927a867d"."line_id" AS VARCHAR(65536)) || '}') AS "t"
                    LEFT JOIN (SELECT "t1"."due" AS "_ttrp_k_n20_0_due", COUNT("p_7e21ab69"."_ttrp_d_n20_0") AS "_ttrp_n_n20_0"
                        FROM (SELECT "p_53d4630f0"."due"
                                FROM "p_927a867d" AS "p_927a867d0"
                                    INNER JOIN "p_53d4630f" AS "p_53d4630f0" ON "p_53d4630f0"."entity" = 'er.entity.return_request_line' AND "p_53d4630f0"."key" = '{"line_id":' || CAST("p_927a867d0"."line_id" AS VARCHAR(65536)) || '}'
                                GROUP BY "p_53d4630f0"."due") AS "t1"
                            INNER JOIN "p_7e21ab69" ON "t1"."due" < "p_7e21ab69"."_ttrp_d_n20_0" AND "p_7e21ab69"."_ttrp_d_n20_0" <= :as_of
                        GROUP BY "t1"."due") AS "t3" ON "t"."due" = "t3"."_ttrp_k_n20_0_due"
                GROUP BY "t"."line_id") AS "t5" ON "p_202d930b"."line_id" = "t5"."line_id") AS "t6"
WHERE "t6"."max_late" > 0
