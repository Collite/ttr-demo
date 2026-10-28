# Hartland writer preview gate

Normal local/CI gate against the clean accepted Server commit in
`toolchain.lock` `[automation-preview].server-ref` (Server#320 merge 88c12a8b).
Run from this repository with JDK 21, Python 3.11+, Git and package-read credentials:

```sh
just writer-preview /path/to/clean/ttr-server
```

The checkout must already be at the exact locked commit; the script refuses wrong/dirty source.
CI checks it out automatically. No candidate frontend override or Maven Local repository is used.
The runner verifies services/automation's published runtime classpath against the separate
`[automation-preview].grammar` pin (0.18.12), not every Server module. Recipe authoring independently uses 0.18.14.
The model/reader and deployed-image pins remain independent.

Five named cases use actual committed Hartland bundles, the Server loader/verifier/bindings,
PartRunner/staging and ApplyPlanner. Only Query result tables are faked. They cover six-bundle
approval coverage in an arbitrary checkout path, all required H3 writer fields/exact bigint ID,
full H5 both routes/eleven UTC boundary and edge instants, pinned Open context, replayed actions
and rows (except written_at), idempotent completion and empty routes. Full H3 must also produce
the same proposal as the writer projection, plus the buyer ask with deferred `start`/`purchasing`,
`2 working_days`, warehouse grouping and would-text. Empty full H3 produces neither actions nor rows.
This is descriptive preview evidence; it does not resolve/dispatch callees, create tasks or allocate calendar deadlines.

JUnit XML is in the Server checkout's `services/automation/build/test-results/test/` and retained
by `.github/workflows/writer-preview.yml`. This gate does not call a connector, execute recipe SQL
against real model data, write to the model, deploy a runtime or certify live US/CZ behavior.
