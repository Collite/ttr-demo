SELECT "line_id", "request_number", "item", "quantity", "way", "customer", "credit_note_id", "issued_date", "payment_id", "paid_date", "shipment_id", "shipped_date", "max_late", "kinds_open", "credit_note_open", "payment_open", "replacement_open", 'goods_shipped' AS "route", 'replacement shipped on ' || CASE WHEN "shipped_date" IS NULL THEN '' ELSE CAST("shipped_date" AS VARCHAR(65536)) END AS "verdict_reason"
FROM (SELECT "t12"."line_id", "t12"."request_number", "t12"."item", "t12"."quantity", "t12"."way", "t12"."customer", "t12"."credit_note_id", "t12"."issued_date", "t12"."payment_id", "t12"."paid_date", "t12"."shipment_id", "t12"."shipped_date", "t12"."max_late", "t12"."kinds_open", "t12"."credit_note_open", "t12"."payment_open", "t14"."replacement_open"
        FROM (SELECT "t9"."line_id", "t9"."request_number", "t9"."item", "t9"."quantity", "t9"."way", "t9"."customer", "t9"."credit_note_id", "t9"."issued_date", "t9"."payment_id", "t9"."paid_date", "t9"."shipment_id", "t9"."shipped_date", "t9"."max_late", "t9"."kinds_open", "t9"."credit_note_open", "t11"."payment_open"
                FROM (SELECT "t6"."line_id", "t6"."request_number", "t6"."item", "t6"."quantity", "t6"."way", "t6"."customer", "t6"."credit_note_id", "t6"."issued_date", "t6"."payment_id", "t6"."paid_date", "t6"."shipment_id", "t6"."shipped_date", "t6"."max_late", "t6"."kinds_open", "t8"."credit_note_open"
                        FROM (SELECT "p_99be0ef6"."line_id", "p_99be0ef6"."request_number", "p_99be0ef6"."item", "p_99be0ef6"."quantity", "p_99be0ef6"."way", "p_99be0ef6"."customer", "p_99be0ef6"."credit_note_id", "p_99be0ef6"."issued_date", "p_99be0ef6"."payment_id", "p_99be0ef6"."paid_date", "p_99be0ef6"."shipment_id", "p_99be0ef6"."shipped_date", "t5"."max_late", "t5"."kinds_open"
                                FROM "p_99be0ef6"
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
                                        GROUP BY "t"."line_id") AS "t5" ON "p_99be0ef6"."line_id" = "t5"."line_id") AS "t6"
                            LEFT JOIN (SELECT "p_927a867d1"."line_id", COUNT("p_1943c707"."kind") AS "credit_note_open"
                                FROM "p_927a867d" AS "p_927a867d1"
                                    INNER JOIN "p_1943c707" ON "p_1943c707"."entity" = 'er.entity.return_request_line' AND "p_1943c707"."key" = '{"line_id":' || CAST("p_927a867d1"."line_id" AS VARCHAR(65536)) || '}'
                                GROUP BY "p_927a867d1"."line_id") AS "t8" ON "t6"."line_id" = "t8"."line_id") AS "t9"
                    LEFT JOIN (SELECT "p_927a867d2"."line_id", COUNT("p_5a31f3a2"."kind") AS "payment_open"
                        FROM "p_927a867d" AS "p_927a867d2"
                            INNER JOIN "p_5a31f3a2" ON "p_5a31f3a2"."entity" = 'er.entity.return_request_line' AND "p_5a31f3a2"."key" = '{"line_id":' || CAST("p_927a867d2"."line_id" AS VARCHAR(65536)) || '}'
                        GROUP BY "p_927a867d2"."line_id") AS "t11" ON "t9"."line_id" = "t11"."line_id") AS "t12"
            LEFT JOIN (SELECT "p_927a867d3"."line_id", COUNT("p_2e30a994"."kind") AS "replacement_open"
                FROM "p_927a867d" AS "p_927a867d3"
                    INNER JOIN "p_2e30a994" ON "p_2e30a994"."entity" = 'er.entity.return_request_line' AND "p_2e30a994"."key" = '{"line_id":' || CAST("p_927a867d3"."line_id" AS VARCHAR(65536)) || '}'
                GROUP BY "p_927a867d3"."line_id") AS "t14" ON "t12"."line_id" = "t14"."line_id") AS "t15"
WHERE "t15"."replacement_open" > 0
