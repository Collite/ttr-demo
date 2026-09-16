# investment-questions — the IE-C62 eval sheet

Ten questions, each in English and Czech, that the **golem-investment** Shem must answer over the
investment book. IE-P4·S4.2·T1. The bar is **≥ 8/10 per locale**, scored on the local estate first
(S4.2·T4/T5) and again on hartland as run 2 (S4.3·T4).

## How to score a question

A question **passes** when both hold:

1. **The source is the expected one** — the turn used the `q.investment.*` query named below (or, for
   the entity questions, answered from the entity roster) rather than free SQL over something else.
   Read it from the turn's plan: `pattern_id`, or `source: FREE_SQL`.
2. **The pass rule is met** — the figure named below appears in the answer, or the stated behaviour
   happens (a clarification, a refusal). A right number from the wrong source is **not** a pass:
   this sheet exists to prove the curated queries are reachable by ordinary language.

⛔ **For every miss, fix the MODEL, not the prompt** (S4.2·T5). The entity's *first description line*
must carry the vocabulary the question used, in both languages; attribute descriptions must name
units and id shapes; `search.patterns` on the query that should have matched must include the
phrasing. Prompt-only fixes are how an estate learns to pass its own eval and fail a person.

## The book these answers come from

The local estate is seeded by `kantheon/packages/investment/model/queries/tests/fixture/book.sql`,
whose hand-computed answers are `expectations.json` (written before any query ran — IE-C28). The
figures below are copied from it, so a wrong answer is a real disagreement and not a stale sheet.

| Fact | Value |
|---|---|
| Clients | **2** — `conseq:8801234` Jan Novák, `conseq:8809876` Eva Dvořáková |
| Portfolios | 4 — three of Novák's (`…142`, `…143`) and one of Dvořáková's (`conseq:200712001`) |
| The worked portfolio | `conseq:200619142` **Dynamické portfolio Plus**, CZK |
| Its holdings | 3 funds: `CZ0008473618` (7 600 units, 912 000,00), `CZ0008474053` (2 400, 252 000,00), `CZ0008472271` (300, 16 500,00) |
| Its cash | **755 000,00 CZK** at 2026-08-31 · 505 000,00 at 2026-03-31 |
| Its quarters | 2025-09-30 995 000,00 · 2025-12-31 1 220 000,00 · 2026-03-31 1 379 800,00 · 2026-06-30 1 350 300,00 (`missing:1`) |

⚑ **`conseq:8801234` is versioned twice** (an e-mail change) and `conseq:200619142` is versioned with
a *rename* — so "how many clients" answered as **3**, or two rows for one portfolio, is an SCD2
mistake, not a data question. That is deliberate: Q9 exists to catch it.

## The ten questions

| # | en | cs | Expected source | Pass rule |
|---|---|---|---|---|
| Q1 | Which portfolios does client `conseq:8801234` hold? | Která portfolia drží klient `conseq:8801234`? | `portfolios_of_client` | Names **Dynamické portfolio Plus** and **Konzervativní portfolio** — two portfolios, not three rows |
| Q2 | What does portfolio `conseq:200619142` hold right now, and what is it worth? | Co je v portfoliu `conseq:200619142` a jakou to má hodnotu? | `positions_current` | The three funds, with **912 000** for `CZ0008473618`; figures in CZK |
| Q3 | How much cash is in portfolio `conseq:200619142`? | Kolik hotovosti je v portfoliu `conseq:200619142`? | `cash_balance` | **755 000** (as of the latest date), per currency |
| Q4 | Show the last transactions in portfolio `conseq:200619142`. | Zobraz poslední transakce v portfoliu `conseq:200619142`. | `transactions_recent` | Newest first, starting **2026-08-10**; no reversed movement and no `-rev` row appears |
| Q5 | What money came into portfolio `conseq:200619142` this year? | Jaké peníze přišly do portfolia `conseq:200619142` letos? | `transactions_between` or `period_values` | Names the **300 000** deposit of 2026-07-15; external flows only, not the cash leg beside them |
| Q6 | How did portfolio `conseq:200619142` develop quarter by quarter? | Jak se portfolio `conseq:200619142` vyvíjelo čtvrtletí po čtvrtletí? | `quarterly_evolution` | Four quarters with **1 379 800** at 2026-03-31; says the last quarter's prices were incomplete |
| Q7 | Which quarter did portfolio `conseq:200619142` lose value in? | Ve kterém čtvrtletí portfolio `conseq:200619142` ztratilo hodnotu? | `quarterly_evolution` | Identifies **2026-06-30** (1 350 300 after 1 379 800) — a reading of the same rows, not a new query |
| Q8 | What is `CZ0008473618` — its name, kind and currency? | Co je `CZ0008473618` — název, druh a měna? | the `asset` entity (roster or free SQL) | **Conseq Invest Akciový**, fund, CZK |
| Q9 | How many clients are there? | Kolik je klientů? | the `client` entity | **2** — a 3 means the SCD2 versions were counted |
| Q10 | What was our return last year? | Jaký jsme měli loni výnos? | **none** — must refuse | A **clarification or refusal that says returns are not modelled** and offers the quarterly value instead. ⛔ Any number here is a failure, however plausible |

Q10 is the one that matters most: returns, dividend totals and fee totals are unanswerable on this
book (⚑IE-9 · S4.1), and a Golem that invents one is worse than a Golem that says so.

## Score sheet

One row per question per locale per run. Append runs; never overwrite — the trail is the deliverable
(S4.2·T5).

| q | locale | run-date | pass | source-seen | notes |
|---|---|---|---|---|---|
| — | — | — | — | — | *(no run yet — S4.2·T4 is blocked, see below)* |

## ⛔ Not yet run, and why

**S4.2·T4 has no venue.** The task list points at a local golem deploy recipe
(`just deploy-local-golem golem-investment`, or an overlay path in `agents/golem/README.md`);
neither exists — kantheon has no golem entry under `deployment/local/` (only `mssql` and `postgres`),
no such recipe in its justfile, and no `agents/golem/README.md` at all. So the iterate-locally loop
this stage is built on cannot run as written.

**And S4.2·T3 cannot enable the Shem yet.** `olymp/clusters/hartland/appset-golems.yaml` reads each
instance's Shem bundle from **`Collite/ttr-demo`** (`agents/golem/shems/<shem>`), which is where
`golem-hartland` and `golem-hartland-finance` live — hand-authored, with no sync recipe. S4.1 built
`golem-investment`'s bundle in **kantheon**, where this ApplicationSet never looks, so adding
`golem-investment.json` would generate an Application whose first source 404s.

Both are Bora's calls, recorded as S4.2·D1 and D2 in the stage's task list.
