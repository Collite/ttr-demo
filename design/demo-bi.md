# Hartland — the BI demo (Superset, the Flight SQL edge, one number three times)

> **What it shows.** A business user's BI tool reads the governed model, not the tables. Every chart runs through the
> one query door as the viewer: their own Keycloak token, their roles, their row rules. The same number comes out of
> the dashboard, out of Iris and out of the saved query, because all three are the same door. Contracts:
> `project/platform/features/bi` (C-23 dashboards, C-25 this script, C-6 receipts).
>
> **Language.** The walk is written in English. The strings the UI shows are given as they appear: Czech in the cz
> world (Markéta, Petr over `hartland_cz`), English in the us world (Maya, Sam over `hartland_us`). Superset's own
> UI is English in both.
>
> **Status (2026-10-23).** Dashboards authored and imported from git (ttr-demo#97, olymp#122). They were walked as
> the four personas on hartland, and the one number checked on every path (§3). Not yet rehearsed in front of
> anyone. Known quirks: §4.

## 0 · Before the show

| check | how | expect |
|---|---|---|
| Superset answers | `https://superset.hartland.collite.cz/health` | `OK` |
| the dashboards are the git ones | ArgoCD app `superset-dashboards` Synced; its last hook Job `superset-dashboards-import` Complete, its log ending `4 dashboards, 12 charts, 4 datasets equal their files` | — |
| one number, every path | `just bi-one-number cz` (and `us` after a world flip) | every leg ✓ 17: oracle, edge ×2, Iris ×2, Superset ×2 |
| the world Iris serves | olymp `just world cz` before a Czech show (ops manual §7.6) | Iris answers in Czech over `hartland_cz` |
| a clean browser | a private window per persona, or sign out between personas (§2.3) | — |
| Tatrman styling | the sign-in page | the Tatrman lockup in the navbar, the title "Tatrman BI" (olymp `tatrman_brand`) |
| each world authorized | as each persona you will show, open one dashboard per world within the half hour before; click through any "Authorization needed" (§2.1 step 3) | charts with data, no yellow box |

Superset needs no world flip: each world is its own Superset database, so both are always there (C-20). Only Iris
serves one world at a time.

Personas (realm `kantheon`, the demo password: ops manual §3.2):

| persona | world | in BI | row rule |
|---|---|---|---|
| **marketa** (Markéta) | cz | analyst: every DC | — |
| **petr** (Petr) | cz | DC manager of DC 5, Brno DC | `kantheon-scope-dc-5` → dc-scope |
| **maya** | us | analyst: every DC | — |
| **sam** | us | DC manager of DC 5, Memphis DC | `kantheon-scope-dc-5` → dc-scope |

All four sign in to Superset as `BI Viewer`: charts and dashboards, no SQL Lab. Admin is the realm group `admins`,
never a persona.

## 1 · The story in one paragraph

The Brno DC (Memphis DC in the us world) melted down in H2 2025. From August to November, 17 of its weekly inventory
snapshots were stock-out weeks. The other four DCs had none. The analyst sees the whole network and the one DC
in Tatrman Yellow. The DC's own manager sees only his DC, on the same dashboard, because the door narrows every statement to what
his role allows. Superset knows nothing about that rule. And the 17 is the same 17 wherever it is asked: on the
tile, in Iris, in the saved query.

## 2 · The walk

### 2.1 Landing → Superset, as the analyst

1. `https://hartland.collite.cz` → the tile **BI · Superset**.
2. Sign in with Keycloak as **marketa**. Superset ("Tatrman BI", the Tatrman lockup top left) opens on its home
   page. **Dashboards** lists four, two per world:
   - «Výpadky zásob v distribučních centrech» and «Reklamace podle kategorie» (cz);
   - "DC meltdown — stock-outs" and "Returns by category" (us).
3. Open **«Výpadky zásob v distribučních centrech»**.
   - ⚑ **Authorization needed.** Superset reads each world with the viewer's OWN token for that database
     (per-database OAuth2). When the persona has none, or the one Superset holds has lapsed, every chart shows a
     yellow box: "Authorization needed. You need to **provide authorization** in order to run this operation." Its
     lapse is the Keycloak session's idle timeout, so after a pause in the show it comes back.
     1. Click **provide authorization** (the amber link). A tab opens, passes through Keycloak with no password (the
        persona is signed in), and says "You can close this window and re-run the query."
     2. Close that tab, then reload the dashboard. The charts do not re-run by themselves.

     It happens once per persona and world. *Say:* Superset holds no data credential of its own. The viewer lends
     it theirs, and only for their own charts.
4. What the dashboard shows:
   - **«Týdny s výpadkem zásob v roce 2025»: 17.** Subtitle «týdny, kdy byla alespoň polovina skladových položek DC
     na nule».
   - **«Týdny s výpadkem podle DC, 2025»**: five rows. Brno DC 17 of 52 weeks; Hradec Králové, Ostrava, Plzeň and
     Praha DC 0 of 52.
   - **«Týdny s výpadkem po měsících a DC, 2025»**: one DC in Tatrman Yellow, the one that melted down. Brno DC has
     Aug 5 · Sep 4 · Oct 5 · Nov 3, and five DCs are in the legend.

   *Say:* this dataset is not a table. It is `obj.query.stockouts_monthly_dc`, a logical query of the model. The
   chart asked the model, and the door wrote the SQL.

### 2.2 The other world

Open **"DC meltdown — stock-outs"**: the same dashboard over `hartland_us`. Memphis DC with 17, and Allentown,
Columbus, Dallas and Reno DC with 0. One world per database (D-2: a world is a tenant, switch, never mix).

### 2.3 The same dashboard, as the DC manager

1. Sign out (top right → Log out). Keycloak asks "Do you want to log out?" once, then returns to Superset's
   sign-in page (review-123 R6, ⚑R123-B).
2. Sign in as **petr**. Open **«Výpadky zásob v distribučních centrech»**:
   - the tile: **17**, the same number, because only DC 5 stocked out;
   - **«Týdny s výpadkem podle DC, 2025»: one row, Brno DC 17 of 52**;
   - the bars: the same four, and only **Brno DC** in the legend.

   *Say:* nobody built Petr a dashboard. The door added `WHERE warehouse = 5` to every chart's statement, because
   Petr's token carries `kantheon-scope-dc-5`. The receipts (§2.6) show the rule inside the SQL.
3. Open **«Reklamace podle kategorie»** as petr. **«Řádky reklamací v roce 2025»: 41 962**, the same as Markéta's.
   - *Say:* returns are not DC-scoped. A row rule narrows the tables it governs (inventory, warehouse) and nothing
     else.
   - The bars: Electronics 4 332, Shoes 4 330, Home 4 288 … Jewelry 3 964, and `<NULL>` 110 (items without a
     category).

### 2.4 Outside Superset: the SQL client, as petr

DataGrip, or DBeaver, IntelliJ, any JDBC tool, with the stock Arrow Flight SQL JDBC driver 18.3.0 (ttr-server
`docs/jdbc.md`):

```
jdbc:arrow-flight-sql://flight.hartland.collite.cz:443/?useEncryption=true&world=hartland_cz
user: petr      password: the demo password
```

1. The catalog shows one world, `hartland_cz`. Its schemas are `er.entity`, `obj.query` and `db.dbo`: the model's
   layers, not the database's.
2. Run:
   ```sql
   SELECT warehouse_name, SUM(stockout_weeks) AS stockout_weeks
   FROM obj.query.stockouts_monthly_dc
   WHERE month_start >= CAST('2025-01-01' AS DATE) AND month_start < CAST('2026-01-01' AS DATE)
   GROUP BY warehouse_name
   ```
   → **one row, Brno DC 17**. As marketa: five rows.

   *Say:* the same door and the same rule, from a tool we did not build.

### 2.5 One number three times

| where | as | how | gives |
|---|---|---|---|
| the Superset tile | petr (or marketa) | «Týdny s výpadkem zásob v roce 2025» | **17** |
| Iris | petr (or marketa) | «Kolik týdnů v roce 2025 mělo Brno DC výpadky zásob?» / "How many weeks in 2025 did Memphis DC have stockouts?" | **17**. The protocol names the saved query `warehouse_stockout_week_count` (act 3.5) |
| the SQL client | petr | §2.4 | **17** |

`just bi-one-number cz` runs all of these as the personas, plus an oracle SQL on the world database, in about a
minute (`run-set/bi-one-number/`).

The Studio report joins this table when SO's `returns_review` report reaches master (⚑BI-4-A).

### 2.6 The receipts: governance you can read

Every statement through the Flight edge leaves a receipt: who asked, in which world, the SQL the door ran, and the
row rules it applied. An admin reads them (ops manual §6, "BI receipts"; it needs the realm group `admins` and a
fresh `jdbc` token):

```
GET /receipts?user_id=petr&since=<the show's start>
```

For petr's dashboard: one receipt per chart, each with
- `client`: `superset`;
- `security_applied`: `dc-scope` on inventory and warehouse;
- `executed_sql`: the rule inside it, `WHERE "inv_warehouse_sk" = 5`;
- `roles`: what his token carried.

His DataGrip statement is there too, with `client` = `jdbc`.

*Say:* the BI tool never saw the rule, and it could not have skipped it.

## 3 · What the screen shows (recorded 2026-10-23, S4.2 T4)

The four personas on hartland, after the import from git (project `platform/features/bi/spikes/bi4-evidence/`:
`s42-persona-walk.json` holds every chart's rows per persona, `s42-<persona>-<dashboard>.png` the screenshots):

| persona | «Výpadky zásob…» / "DC meltdown…" | per-DC table | bars: series | returns tile |
|---|---|---|---|---|
| marketa | 17 | 5 rows (Brno DC 17/52, four DCs 0/52) | 5 DCs (60 rows) | 41 962 |
| petr | 17 | 1 row: Brno DC 17/52 | Brno DC (12 rows) | 41 962 |
| maya | 17 | 5 rows (Memphis DC 17/52) | 5 DCs | 41 962 |
| sam | 17 | 1 row: Memphis DC 17/52 | Memphis DC | 41 962 |

- **The first read of each world:**
  - The scripted walk's first chart of each database answered `OAUTH2_REDIRECT`; the walk followed it and read.
  - In the browser (recorded later, after the personas' sessions had idled), every chart showed "Authorization
    needed". Clicking "provide authorization" opened a tab: Keycloak (no password), then Superset's "You can close
    this window and re-run the query".
  - The dashboard showed data only after a reload (§2.1 step 3).
  - A persona with a live token for that database sees no prompt at all.
- **The receipts** (`query.bi_receipts`, the same rows `GET /receipts` reads): one per chart. Each has
  `client = superset` and the viewer's own `user_id`. For the per-DC table, marketa's receipt has no row rule
  (`security_applied` empty, 5 rows). petr's runs the same statement with `dc-scope` on `db.dbo.inventory` and
  `db.dbo.warehouse`, `"inv_warehouse_sk" = 5` inside `executed_sql`, and 1 row.
- **One number:** `just bi-one-number cz` → the oracle and all six legs 17 (edge, Iris and the Superset tile, each
  as marketa and as petr). On `us` the edge and Superset legs are 17 as maya and sam, and the Iris legs need
  `just world us` first.
- **A dashboard's owner reads "Not available"**: an imported dashboard has no owner. Admin edits it all the same.

## 4 · Known quirks

- **The tile does not tell the personas apart.** Only DC 5 stocked out, so the whole network's 17 is DC 5's 17.
  The table and the legend tell them apart. Say it before someone asks.
- **Superset's UI is English** in the cz world too. The dashboards' titles, charts and column labels are Czech. The
  item categories are English because they are the data's (TPC-DS).
- **Return lines, not requests, on the returns tile.** A request with lines in two categories counts once in each,
  so the categories' requests add up to 41 949, but 41 849 requests were filed. Lines add up exactly
  (`dashboards/returns-by-category/README.md`).
- **The period is fixed to 2025** in every chart. There are no dashboard filters yet.
- **Every receipt carries `schema_mismatch` WARNINGs**, one per table. They are noise (ops manual §6).
- **Many connections at once as one persona** (a SQL client that opens several, or a script) can trip Keycloak's
  brute-force detection on the password grant: `password_refused … 401 invalid_grant`. Thirty refusals lock the
  account temporarily. Superset is not affected: it uses each viewer's OAuth token, never their password.
- **An edit in Superset's UI does not survive** the next import from git. To keep it, export it into the bundle
  (`dashboards/README.md`).
- **"Authorization needed" comes back after an idle pause** (§2.1 step 3): one click and a reload per persona and
  world. Rehearse it, or show it on purpose as part of the governance story.
- **Superset's own messages still name "Apache Superset"** (the authorization box, for example). The styling
  changes the brand, not Superset's text; the logo's tooltip credits Superset.
