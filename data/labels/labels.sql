-- The label columns: CHAR(n) → VARCHAR(n), trimmed (BI-4 · contracts C-24, ⚑BI-4-B ruled by Bora 2026-10-22).
--
-- dsdgen declares the descriptive columns CHAR(n), and Postgres returns a CHAR value blank-padded to n: every label
-- read from one reached Superset, a JDBC client and Iris as 'Books' + 45 blanks (BI-0 S-10). The translator cannot
-- trim them in the er mapping (an expression-bound attribute is not mapped yet), so the columns themselves become
-- VARCHAR of the same width; the cast drops the trailing blanks (USING rtrim makes that explicit). The codes and the
-- one-letter flags stay CHAR: a code fills its width, a flag is one letter, so neither is padded.
--
-- The list is the db model's (model/db/dims.ttrm, its VARCHAR columns; model/db/tests/db.test.mjs C-24 holds the two
-- equal). One transaction (run-labels.sh passes -1): a column that is missing, a view that depends on one (ALTER
-- refuses), or a value still padded afterwards rolls every table back. Idempotent: a column already VARCHAR is left
-- alone, so a second run changes nothing. One ALTER per table, so a table is rewritten once.

DO $$
DECLARE
  t record;
  bad text;
BEGIN
  CREATE TEMP TABLE _labels (tbl text, col text, len int) ON COMMIT DROP;
  INSERT INTO _labels VALUES
    ('item', 'i_product_name', 50), ('item', 'i_brand', 50), ('item', 'i_class', 50), ('item', 'i_category', 50),
    ('item', 'i_manufact', 50), ('item', 'i_size', 20), ('item', 'i_container', 10),
    ('reason', 'r_reason_desc', 100),
    ('promotion', 'p_promo_name', 50),
    ('household_demographics', 'hd_buy_potential', 15),
    ('date_dim', 'd_day_name', 9);

  SELECT string_agg(format('%I.%I', l.tbl, l.col), ', ') INTO bad
  FROM _labels l LEFT JOIN information_schema.columns c
    ON c.table_schema = 'public' AND c.table_name = l.tbl AND c.column_name = l.col
  WHERE c.column_name IS NULL OR c.data_type NOT IN ('character', 'character varying');
  IF bad IS NOT NULL THEN
    RAISE EXCEPTION 'labels: no such text column: %', bad;
  END IF;

  FOR t IN
    SELECT l.tbl,
           string_agg(format('ALTER COLUMN %I TYPE varchar(%s) USING rtrim(%I)', l.col, l.len, l.col), ', ' ORDER BY l.col) AS alters,
           string_agg(l.col, ', ' ORDER BY l.col) AS cols
    FROM _labels l JOIN information_schema.columns c
      ON c.table_schema = 'public' AND c.table_name = l.tbl AND c.column_name = l.col
    WHERE c.data_type = 'character'
    GROUP BY l.tbl ORDER BY l.tbl
  LOOP
    EXECUTE format('ALTER TABLE public.%I %s', t.tbl, t.alters);
    RAISE NOTICE 'labels: % — % now VARCHAR', t.tbl, t.cols;
  END LOOP;

  SELECT string_agg(format('%I.%I is %s(%s)', l.tbl, l.col, c.data_type, c.character_maximum_length), ', ') INTO bad
  FROM _labels l JOIN information_schema.columns c
    ON c.table_schema = 'public' AND c.table_name = l.tbl AND c.column_name = l.col
  WHERE c.data_type <> 'character varying' OR c.character_maximum_length <> l.len;
  IF bad IS NOT NULL THEN
    RAISE EXCEPTION 'labels: not VARCHAR of its width: %', bad;
  END IF;

  FOR t IN SELECT * FROM _labels LOOP
    EXECUTE format('SELECT count(*) FROM public.%I WHERE %I <> rtrim(%I)', t.tbl, t.col, t.col) INTO bad;
    IF bad::bigint > 0 THEN
      RAISE EXCEPTION 'labels: %.% still has % padded values', t.tbl, t.col, bad;
    END IF;
  END LOOP;
END
$$;
