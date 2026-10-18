-- AU-hartland P1 · S1.1 — the working day (D-82; README.md "Calendar"): not a holiday and not a weekend, every
-- day of date_dim. A real boolean (model/db/dims.ttrm `type: bool`), not a Y/N char like its two sources.
UPDATE date_dim SET d_working_day = (coalesce(d_holiday, 'N') = 'N' AND coalesce(d_weekend, 'N') = 'N');

INSERT INTO _automation_meta (step, as_of, rows) SELECT '25-calendar', :'as_of', count(*) FILTER (WHERE d_working_day) FROM date_dim;
