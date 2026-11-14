# Hartland writer preview gate

Normal local/CI gate against the clean accepted Server commit in
`toolchain.lock` `[automation-preview].server-ref` (the ttr-server#390 merge f28120e1: AU-server D3, grammar 0.22.3).
Run from this repository with JDK 21, Python 3.11+, Git and package-read credentials:

```sh
just writer-preview /path/to/clean/ttr-server
```

The checkout must already be at the exact locked commit; the script refuses wrong/dirty source.
CI checks it out automatically. No candidate frontend override or Maven Local repository is used.
The runner verifies services/automation's published runtime classpath against the separate
`[automation-preview].grammar` pin (0.22.3, translator/proto 0.14.1), not every Server module. Recipe authoring
uses the same grammar (compiler 0.22.3, the `[ttrp]` pin). The model/reader and deployed-image pins remain independent.

Five named cases use actual committed Hartland bundles, the Server loader/verifier/bindings,
PartRunner/staging and ApplyPlanner. Only Query result tables are faked. They cover six-bundle
approval coverage in an arbitrary checkout path, all required H3 writer fields/exact bigint ID,
H5's eleven UTC boundary and edge instants, pinned Open context, replayed actions and rows
(except written_at), idempotent completion, and empty full H3 and H5 selections.

Since `545527b` (P3E), H3's buyer approval (`handoff`) and H5's mail (`emit`) are engine actions with no native
sink. Grammar 0.21.1 predates engine actions; on 0.22.3 the Server's native preview refused them (D-178) until
AU-server S3.1 (ttr-server#397, ⚑AU-D3-1). Since S3.1 the preview lists an engine action as the engine's — `sink:
engine`, its arguments and `would` text, no batch rows — so both the full H3 and the full H5 case run again.
This is descriptive preview evidence; it does not resolve/dispatch callees, create tasks or allocate calendar deadlines.

JUnit XML is in the Server checkout's `services/automation/build/test-results/test/` and retained
by `.github/workflows/writer-preview.yml`. This gate does not call a connector, execute recipe SQL
against real model data, write to the model, deploy a runtime or certify live US/CZ behavior.
