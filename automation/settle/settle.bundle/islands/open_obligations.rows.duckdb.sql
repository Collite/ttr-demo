SELECT "p_927a867d"."line_id", "p_53d4630f"."id" AS "obligation_id", "p_53d4630f"."kind", "p_53d4630f"."due"
FROM "p_927a867d"
    INNER JOIN "p_53d4630f" ON "p_53d4630f"."entity" = 'er.entity.return_request_line' AND "p_53d4630f"."key" = '{"line_id":' || CAST("p_927a867d"."line_id" AS VARCHAR(65536)) || '}'
