SELECT "t13"."line_id", "t13"."request_number", "t13"."item", "t13"."quantity", "t13"."way", "t13"."customer", "t13"."credit_note_id", "t13"."issued_date", "t13"."payment_id", "t13"."paid_date", "t13"."shipment_id", "t13"."shipped_date", "t13"."max_late", "t13"."kinds_open", "t13"."credit_note_open", "t13"."payment_open", "t15"."replacement_open", 'money_received' AS "route", 'refund paid on ' || CASE WHEN "t13"."paid_date" IS NULL THEN '' ELSE CAST("t13"."paid_date" AS VARCHAR(65536)) END AS "verdict_reason"
FROM (SELECT *
        FROM (SELECT "t9"."line_id", "t9"."request_number", "t9"."item", "t9"."quantity", "t9"."way", "t9"."customer", "t9"."credit_note_id", "t9"."issued_date", "t9"."payment_id", "t9"."paid_date", "t9"."shipment_id", "t9"."shipped_date", "t9"."max_late", "t9"."kinds_open", "t9"."credit_note_open", "t11"."payment_open"
                FROM (SELECT "t6"."line_id", "t6"."request_number", "t6"."item", "t6"."quantity", "t6"."way", "t6"."customer", "t6"."credit_note_id", "t6"."issued_date", "t6"."payment_id", "t6"."paid_date", "t6"."shipment_id", "t6"."shipped_date", "t6"."max_late", "t6"."kinds_open", "t8"."credit_note_open"
                        FROM (SELECT "p_859395aa"."line_id", "p_859395aa"."request_number", "p_859395aa"."item", "p_859395aa"."quantity", "p_859395aa"."way", "p_859395aa"."customer", "p_859395aa"."credit_note_id", "p_859395aa"."issued_date", "p_859395aa"."payment_id", "p_859395aa"."paid_date", "p_859395aa"."shipment_id", "p_859395aa"."shipped_date", "t5"."max_late", "t5"."kinds_open"
                                FROM "p_859395aa"
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
                                        GROUP BY "t"."line_id") AS "t5" ON "p_859395aa"."line_id" = "t5"."line_id") AS "t6"
                            LEFT JOIN (SELECT "p_927a867d1"."line_id", COUNT("p_1943c707"."kind") AS "credit_note_open"
                                FROM "p_927a867d" AS "p_927a867d1"
                                    INNER JOIN "p_1943c707" ON "p_1943c707"."entity" = 'er.entity.return_request_line' AND "p_1943c707"."key" = '{"line_id":' || CAST("p_927a867d1"."line_id" AS VARCHAR(65536)) || '}'
                                GROUP BY "p_927a867d1"."line_id") AS "t8" ON "t6"."line_id" = "t8"."line_id") AS "t9"
                    LEFT JOIN (SELECT "p_927a867d2"."line_id", COUNT("p_5a31f3a2"."kind") AS "payment_open"
                        FROM "p_927a867d" AS "p_927a867d2"
                            INNER JOIN "p_5a31f3a2" ON "p_5a31f3a2"."entity" = 'er.entity.return_request_line' AND "p_5a31f3a2"."key" = '{"line_id":' || CAST("p_927a867d2"."line_id" AS VARCHAR(65536)) || '}'
                        GROUP BY "p_927a867d2"."line_id") AS "t11" ON "t9"."line_id" = "t11"."line_id") AS "t12"
        WHERE "t12"."payment_open" > 0) AS "t13"
    LEFT JOIN (SELECT "p_927a867d3"."line_id", COUNT("p_2e30a994"."kind") AS "replacement_open"
        FROM "p_927a867d" AS "p_927a867d3"
            INNER JOIN "p_2e30a994" ON "p_2e30a994"."entity" = 'er.entity.return_request_line' AND "p_2e30a994"."key" = '{"line_id":' || CAST("p_927a867d3"."line_id" AS VARCHAR(65536)) || '}'
        GROUP BY "p_927a867d3"."line_id") AS "t15" ON "t13"."line_id" = "t15"."line_id"
