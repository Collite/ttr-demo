# agents — the Hartland agent def + both Golem Shems (D-7, BM-9)

`hartland.yaml` is the ai-models-analog agent definition (Ariadne's Git source, per BM-9's
"model repo -> Ariadne -> assembled Shem" onboarding path). `golem/shems/` holds the two
assembled-Shem overlays (kantheon canon: identity+model from the agent def, area terminology
from the model, the per-agent residue in `shem.yaml`, template constants at boot).

## Persona -> `visibility_roles` mapping (Q-BM-4a, Stage 2.6 T5)

As the hartland realm overlay wires them (olymp `platform/auth/keycloak/overlays/hartland/realm/kantheon.json`):

| Persona | User | World | Realm roles | Shem(s) it grants | Row scope |
|---|---|---|---|---|---|
| Maya Chen (Senior Category Manager) | `maya` | US | `kantheon-area-hartland` | golem-hartland ("Hartland Analytics") | — |
| Markéta Nováková (Senior Category Manager) | `marketa` | CZ | `kantheon-area-hartland` | golem-hartland | — |
| Sam Reyes (Memphis DC Manager) | `sam` | US | `kantheon-area-hartland`, `kantheon-scope-dc-5` | golem-hartland | distribution centre 5 (Memphis DC) |
| Petr Svoboda (Vedoucí distribučního centra Brno) | `petr` | CZ | `kantheon-area-hartland`, `kantheon-scope-dc-5` | golem-hartland | distribution centre 5 (Brno DC) |
| Dan Whitaker (CFO) | `dan` | US | `kantheon-area-hartland`, `kantheon-role-finance`, `kantheon-area-investment`, `studio-operations` | golem-hartland, golem-hartland-finance ("Hartland Finance"), golem-investment ("Investment Q&A", IE-P4) | — |
| Tomáš Horák (Finanční ředitel) | `tomas` | CZ | `kantheon-area-hartland`, `kantheon-role-finance` | golem-hartland, golem-hartland-finance | — |

**Row scope (LR C-5·4, ⚑LR-13).** `kantheon-scope-dc-5` grants no Shem. It is a row rule: for its
holders, validate narrows `inventory`, `warehouse`, `catalog_sales`, `web_sales` and `channel_sales`
to warehouse 5 — Memphis DC in the US world, Brno DC in the Czech one (olymp `apps/validate`
`configFragment`). Store sales, items, customers and the calendar stay open. A store line in
`channel_sales` has no distribution centre (`warehouse_sk` NULL, `data/views/channel_sales.sql`), so a
DC-scoped caller asking by channel sees its DC's web and marketplace lines and no store lines. The
Golem ends such an answer with the rights sentence (contracts C-6·1/2).

## golem-investment — the DEPLOYED copy of a bundle authored in kantheon

`golem/shems/golem-investment/` is the copy the estate runs, and it is **not** the copy that is
tested. The authoring copy is kantheon `agents/golem/shems/golem-investment/`, where
`GolemInvestmentBundleSpec` and `GolemInvestmentRegistrationSpec` assert the overlay against the live
`ShemOverlayParser` and `ShemAssembler`. It lives here as well because olymp's `hartland-golems`
ApplicationSet reads every instance's bundle from **this repo** (IE-P4·S4.2·D1, ruled 2026-09-16).

Two copies with no compiler between them is how S1.5·D14 happened, so `tests/shems.test.mjs` compares
them and fails on drift: **change one side and copy it in the same commit.** Two deliberate
differences the guard allows, both ttr-demo standards — `source.repo: hartland` with a local
`agents/investment.yaml` (BM-9 self-containment, where kantheon names `ai-models`), and per-locale
`example_questions` / `counter_examples` (BM-6) where kantheon authors flat lists. The bundle also
omits `free-sql`/`chip-topup`: only `intent` has a live consumer.

**The governance-cameo contrast (F-1, verify in Stage 2.6 T6 / live in Phase 3 H3.2):**
`golem-hartland`'s `visibility_roles` = `[kantheon-area-hartland]` only;
`golem-hartland-finance`'s = `[kantheon-role-finance]` only — the two role sets are
disjoint, so the finance Shem is structurally unroutable for Maya/Markéta (B-2α). As wired
(table above), both CFOs also hold `kantheon-area-hartland`, so they see both Shems; the contrast
is the analysts', who never see the finance Shem in Discover **or** in Golem routing.

## Prompts

`golem/shems/<shem>/prompts/{en,cs}/system.yaml` — per-Shem system prompts (BM-6: cs is in
scope, not "unused per FI-4" as in the pre-delta ai-models precedent). Adapted from
ai-models' generic golem intent-classifier prompt (`prompts/golem/{en,cs}/intent.yaml`) with
the domain framing swapped to Hartland retail analytics; the classifier role and JSON output
contract are unchanged. Per the golem-ucetnictvi precedent, prompts belong to the Shem, not
the model.
