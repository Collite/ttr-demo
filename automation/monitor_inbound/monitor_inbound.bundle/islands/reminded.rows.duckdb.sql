SELECT "t"."line_id", COUNT("p_4fd248ed"."run") AS "reminders"
FROM (SELECT "p_da15c438"."line_id", "p_da15c438"."request_number", "p_da15c438"."item", "p_da15c438"."quantity", "p_da15c438"."way", "p_da15c438"."customer0" AS "customer", "p_da15c438"."email" AS "customer_email", "p_34ee525c"."id" AS "obligation_id", "p_34ee525c"."due", "p_34ee525c"."state" AS "obligation_state"
        FROM "p_da15c438"
            INNER JOIN "p_34ee525c" ON "p_34ee525c"."entity" = 'er.entity.return_request_line' AND "p_34ee525c"."key" = '{"line_id":' || CAST("p_da15c438"."line_id" AS VARCHAR(65536)) || '}' AND "p_34ee525c"."kind" = 'inbound' AND "p_34ee525c"."state" IN ('open', 'overdue', 'reopened')) AS "t"
    LEFT JOIN "p_4fd248ed" ON "t"."line_id" = "p_4fd248ed"."line_id" AND "p_4fd248ed"."route" = 'remind'
GROUP BY "t"."line_id"
