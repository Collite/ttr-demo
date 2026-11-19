SELECT "t13"."line_id", "t13"."request_number", "t13"."item", "t13"."quantity", "t13"."way", "t13"."customer", "t13"."credit_note_id", "t13"."issued_date", "t13"."payment_id", "t13"."paid_date", "t13"."shipment_id", "t13"."shipped_date", "t13"."max_late", "t13"."kinds_open", "t13"."credit_note_open", "t13"."payment_open", "t15"."replacement_open", 'credit_note_issued' AS "route", 'credit note ' || CASE WHEN "t13"."credit_note_id" IS NULL THEN '' ELSE CAST("t13"."credit_note_id" AS VARCHAR(65536)) END || ' issued' AS "verdict_reason"
FROM (SELECT "t10"."line_id", "t10"."request_number", "t10"."item", "t10"."quantity", "t10"."way", "t10"."customer", "t10"."credit_note_id", "t10"."issued_date", "t10"."payment_id", "t10"."paid_date", "t10"."shipment_id", "t10"."shipped_date", "t10"."max_late", "t10"."kinds_open", "t10"."credit_note_open", "t12"."payment_open"
        FROM (SELECT *
                FROM (SELECT "t6"."line_id", "t6"."request_number", "t6"."item", "t6"."quantity", "t6"."way", "t6"."customer", "t6"."credit_note_id", "t6"."issued_date", "t6"."payment_id", "t6"."paid_date", "t6"."shipment_id", "t6"."shipped_date", "t6"."max_late", "t6"."kinds_open", "t8"."credit_note_open"
                        FROM (SELECT "p_77af0c22"."line_id", "p_77af0c22"."request_number", "p_77af0c22"."item", "p_77af0c22"."quantity", "p_77af0c22"."way", "p_77af0c22"."customer", "p_77af0c22"."credit_note_id", "p_77af0c22"."issued_date", "p_77af0c22"."payment_id", "p_77af0c22"."paid_date", "p_77af0c22"."shipment_id", "p_77af0c22"."shipped_date", "t5"."max_late", "t5"."kinds_open"
                                FROM "p_77af0c22"
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
                                        GROUP BY "t"."line_id") AS "t5" ON "p_77af0c22"."line_id" = "t5"."line_id") AS "t6"
                            LEFT JOIN (SELECT "p_927a867d1"."line_id", COUNT("p_1943c707"."kind") AS "credit_note_open"
                                FROM "p_927a867d" AS "p_927a867d1"
                                    INNER JOIN "p_1943c707" ON "p_1943c707"."entity" = 'er.entity.return_request_line' AND "p_1943c707"."key" = '{"line_id":' || CAST("p_927a867d1"."line_id" AS VARCHAR(65536)) || '}'
                                GROUP BY "p_927a867d1"."line_id") AS "t8" ON "t6"."line_id" = "t8"."line_id") AS "t9"
                WHERE "t9"."credit_note_open" > 0) AS "t10"
            LEFT JOIN (SELECT "p_927a867d2"."line_id", COUNT("p_5a31f3a2"."kind") AS "payment_open"
                FROM "p_927a867d" AS "p_927a867d2"
                    INNER JOIN "p_5a31f3a2" ON "p_5a31f3a2"."entity" = 'er.entity.return_request_line' AND "p_5a31f3a2"."key" = '{"line_id":' || CAST("p_927a867d2"."line_id" AS VARCHAR(65536)) || '}'
                GROUP BY "p_927a867d2"."line_id") AS "t12" ON "t10"."line_id" = "t12"."line_id") AS "t13"
    LEFT JOIN (SELECT "p_927a867d3"."line_id", COUNT("p_2e30a994"."kind") AS "replacement_open"
        FROM "p_927a867d" AS "p_927a867d3"
            INNER JOIN "p_2e30a994" ON "p_2e30a994"."entity" = 'er.entity.return_request_line' AND "p_2e30a994"."key" = '{"line_id":' || CAST("p_927a867d3"."line_id" AS VARCHAR(65536)) || '}'
        GROUP BY "p_927a867d3"."line_id") AS "t15" ON "t13"."line_id" = "t15"."line_id"
