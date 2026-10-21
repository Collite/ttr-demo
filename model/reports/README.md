# model/reports — report templates

One folder per report: `<id>/report.yaml` + `<id>/template.xlsx`. `report.yaml` names a saved query (`program`), the
sheets, and the columns each table takes from the query; `template.xlsx` carries the `{{anchor}}` and `{{table:…}}`
cells the renderer fills. Format: ttr-core `docs/manual/reports.md` (`report.yaml` v1).

There is none on master yet: the first, `returns_review_q`, comes with the demo branch `demo/returns-review`.
`tests/report.test.mjs` checks every folder — the id is the folder's name, the program is a `def query` the model
loads, an `er.query` program takes no parameters, the tables name only the program's output columns, the template is
there.

Designed and planned in `project/platform/features/studio/`.
