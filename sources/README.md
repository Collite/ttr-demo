# Metadata reader fixtures

These invented inputs are adapted from the Core `grammar/v0.22.13` conformance
fixtures. The generated trees include reports and provenance sidecars.

| Input | Expected coverage |
| --- | --- |
| `om/shop-tables.json` | Tables and composite FK |
| `glossary/trade.ttl` | SKOS broader and related edges, English and Czech lexicons, role/event overlay |
| `glossary/trade.csv` | OM glossary approvals, skipped terms and synonyms |
| `xmi/carried-world/` | Core's 15-definition round-trip control for the MDG writer's carried CN, ER and MD subset |
| `xmi/xm-world/` | Full XM writer fixture. On this pin, reimport of its unmodified export fails on an unconsumed `ownedAttribute/0/@outgoing`. |
| `xmi/ea/` | Two EA snapshots of the same ERD, retaining GUIDs across the Order rename, plus the stale overlay |
| `pdm/input/` | PD 16 CDM, LDM and PDM with cross-layer bindings and FK joins |
| `pdm/pd15.pdm` | Unsupported version diagnostic |

Round-trip equality compares the normalized `defs.json` semantic dumps with
the source fingerprint omitted. Each report golden pins the complete
`ignored[]` list, including location and reason.
