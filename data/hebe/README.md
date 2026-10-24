# Hebe's routine fixtures (HE-P1 · S1.3, HB contracts §4)

Markéta's standing routines on hartland, installed by script and preserved by every demo reset (ops manual §7.1).

| File | When | What it asks | State |
|---|---|---|---|
| `routines/monday-brief.json` | Mondays 07:00 Prague | "Jaký byl obrat podle prodejních kanálů za rok 2025 oproti roku 2024?" | on |
| `routines/friday-returns.json` | Fridays 16:00 Prague | "Jaké byly vratky podle prodejních kanálů za poslední týden?" | on |
| `routines/clarify-demo.json` | Wednesdays 07:00 Prague | a placeholder: the Beat-5 wording is chosen at HB-P3 | **off** |

- **`monday-brief`** is the Kantheon demo's standing fixture, the "Monday channel health brief" of Beat 1 (HB
  contracts §4.1). Its question lands on golem-hartland's prepared query "Meziroční tržby podle kanálu", which is
  what the beat shows.
- **`friday-returns`** is the HB demo's weekly returns summary (§4.2), the reference for the routine created on stage
  in Beat 4. golem-hartland answers it with free SQL.
- **`clarify-demo`** is installed disabled until HB-P3 pins a question that reliably triggers a clarification.
- **Language:** the questions are Czech (HE-D-10). Hebe sends `locale = cs` with every turn, so the answers are
  Czech too. Both live questions were asked through iris-bff as marketa on 2026-10-24 and answered.
- **Delivery:** every routine delivers to `telegram` (the presenter's phone) and `web` (Markéta's Iris inbox, a
  `brief` row since iris-bff 0.11.17).

**Time zone.** Hebe evaluates `cron` in **UTC**. The fixtures carry the winter offset (CET = UTC+1), so they fire at
07:00 and 16:00 Prague time from the last Sunday of October to the last Sunday of March. In summer (CEST) they fire
an hour later, local time. Shift the hour, and re-run the installer, if the demo needs the exact wall-clock time in
summer.

## Install, fire, list

```bash
data/hebe/install-routines.sh                       # port-forward to svc/hebe; Hebe admits the loopback caller as `local`
data/hebe/install-routines.sh --edge                # through https://hebe.hartland.collite.cz, signed in as marketa
data/hebe/install-routines.sh --fire monday-brief   # pre-show (ops manual §7.3 step 3): install, then fire
```

- **Idempotent by name:** a routine already installed is updated in place, with the same id and the same Iris
  session, so the script is safe to re-run after any edit here.
- **`--edge`** reads the persona password from `$HEBE_VERIFY_PASSWORD`, never from argv, as the rig does.
- **The same API as `hebe routines`:** `routines_api.py` speaks Hebe's `/api/routines` (`install | fire | list`),
  the calls `hebe routines install|fire|list` make, so this machine needs no hebe binary.
