# HB — Hebe demo on Hartland · Contracts

> Demo-specific artifacts only. Product contracts are **frozen inputs, cited not restated**:
> `project/kantheon/architecture/hebe/contracts.md` (§1.2 Routine/RoutineBody/RoutineRun ·
> §4 PG schemas + §4.4 instance provisioning · §5 axes/profiles), the iris contracts
> (`TurnOrigin`/`origin_ref`), and the hebe features/v1-specs docs. Anything here that
> contradicts those is a bug in this file. Cluster deployment truth:
> `olymp/clusters/hartland/apps/hebe/values.yaml` (+ the `hebe-dev` instance secret).

## 1. On-stage register (HB-D7)

Spoken/visible: **Hebe** · routine · brief · receipt · workspace / memory · the console ·
"bound to Maya" · check-out of nothing (no Studio vocabulary here — different plane).
Never spoken: profile/axis names (`k8s`, `platform_identity`…), module names, `iris-bff`,
`OBO` (say "as Maya, with her identity"), CAP/⚑ codes.

## 2. The instance binding (HB-P1 target state)

Instance **`dev`** on hartland (HB-D2), verified/probed then adjusted to:

> **Amended by HE-D-4:** the instance is **`marketa`**, bound to Markéta (secret `hebe-marketa`, schema `hebe_marketa`),
> run from the collite image. The last column is what HE-P1 · S1.2 delivered. `rig-hb/verify.sh` checked it on
> 2026-10-24 (hebe 0.11.6, llm-gateway 0.11.4): 12 pass · 0 fail · 1 n/a, twice, the second run after
> `rollout restart deploy/hebe`.

| Concern | Target | Where it lives | Met (HE-P1·S1.2) |
|---|---|---|---|
| Profile | `k8s` (already set) | olymp values `hebe.profile` | met: `k8s`, `storage=postgres`, `tools.posture=restricted` |
| Bound user | **`maya`** (Keycloak realm `kantheon`) | `hebe-dev` secret (Keycloak client creds + bound-user) — provisioning runbook §4.4 | met as **`marketa`**: the OBO token's `sub` is marketa (rig `obo-identity`); `hebe-marketa` carries the seven keys |
| Telegram | bot token (⚑HB-3) + `[channels.telegram]` config | `hebe-dev` secret + values `extraToml` | met: round trip from the presenter's phone, chat history kept (rig `telegram`); token rotation is olymp#148 |
| chat_user_map | presenter's Telegram chat-id → `maya`; **nothing else mapped** | hebe settings (console/config) — the Beat-6 rejection depends on this being the ONLY row | met: one row, presenter's chat → marketa. The stranger step is not in the demo (B-4.4), so rig `unmapped-chat` is n/a |
| Console | reachable per ⚑HB-2 (route `hebe.20-218-224-115.nip.io` default; else port-forward `svc/hebe 8765`) | olymp HTTPRoute or ops-manual §6 recipe | met: `https://hebe.hartland.collite.cz`, an HTTPRoute on the shared edge (rig `console-redirect`) |
| Console auth | per `console_auth` axis as shipped for k8s (probe; password-from-secret acceptable for the demo) | `hebe-dev` secret | met: `console_auth="edge"` (OIDC at the gateway, client `hebe-console`). marketa → 200, maya → 403, maya with a forged identity header → 403 |
| LLM | llm-gateway `/v1`, `claude-sonnet-4-6`, embeddings `ada-002` (already set) | values `extraToml [llm]` | met with other models: `gpt-4.1` (no Anthropic key on hartland) and embeddings `text-embedding-3-small` (no `ada-002` deployment exists; olymp#152). Memory write → search checked live |
| Registry | registered + heartbeating, `non_routable` honored (Beat 0 fact) | capabilities-mcp — verify via list/search vs routing view | met: `hebe-marketa` registered `non_routable`, absent from the routing view (rig `registry`, `routing-view`) |
| Storage | PG schema `hebe_dev` (memory/workspace/receipts) on central PG | provisioned by `just hebe-provision dev` | met as `hebe_marketa`: the receipt chain verifies across restarts, 8 records, and records 7 and 8 were written after a restart (rig `receipts-chain`) |

Any delta between probed reality and this table is an HB-P1 task (values/secret/provision
re-run via olymp PR — freeze rules apply, architecture §3).

## 3. Workspace / memory fixtures (`data/hebe/workspace/`, HB-D5)

Seeded via the workspace write path (console editor or workspace tools — NOT raw SQL), so
revision/consistency semantics hold. Fixture set (plain markdown, EN):

- `MEMORY.md` — curated: the Memphis conclusion (17 weeks, wks 31–47, Marketplace pinned
  to warehouse — numbers **quoted from `data/recon/R0.md`**, cite-checked), the win-back
  promo decision (November, Marketplace), the FY26 plan decision line (post-SD tie-in,
  optional), Maya's standing preferences ("weekly returns summary by channel, Fridays").
- `USER.md` — who Maya is (title, categories, channels she watches) — consistent with the
  Keycloak persona attributes.
- `daily/2026-01-19.md` (the January demo day) + one or two February notes — the raw
  material the curated notes "came from".
- **Oracle:** `data/hebe/expected/memory-answers.md` — for each Beat-2 question, the
  facts the answer MUST contain and the fixture file it must trace to (grading sheet for
  rehearsal, since LLM wording varies — grade on facts + source, never exact text).

## 4. Routine fixtures (`data/hebe/routines/`)

1. **`monday-brief`** — the standing Kantheon-demo fixture ("Monday channel health
   brief"), body `kantheon_question`, delivery → Telegram + inbox. HB does not redefine
   it — it *reuses* the E-4 standing fixture and adds the Telegram delivery target if the
   standing definition lacks it (coordinate: this fixture is shared with the Kantheon
   demo's Beat 1; any change goes through the E-4 fixture install script, not ad hoc).
2. **`friday-returns`** — NEW: "weekly returns summary by channel", Fridays 16:00
   Europe/Prague, `kantheon_question` body wording pinned in the fixture file; created
   ON STAGE in Beat 4 (create-from-chat) — the fixture is the *reference* the created
   routine is diffed against in rehearsal, and the pre-created copy is the L1 fallback.
3. **`clarify-demo`** — the Beat-5 vehicle: a question engineered to trigger golem
   param-fill (one missing parameter → `AWAITING_AGENT`); exact wording chosen at HB-P3
   from live probing (quirks §5.3 behavior), pinned once found.
4. Delivery expectations: `data/hebe/expected/deliveries.md` — for each routine, the
   channel-message shape (conclusion + artifact count + deep-link pattern
   `https://iris.20-218-224-115.nip.io/...`) and the oracle numbers (returns ≈5% of
   revenue baseline; weekly figures from the run-set oracles).

## 5. Beat choreography artifacts

`beats/beat-{0..6}.md` (HB-P3 outputs, one per narrative beat): click/tap-by-tap, every
expected on-screen/on-phone string, screenshots, timing box, and the beat's fallback move.
Beat 6 additionally records: the exact refusal text (posture), the receipts-verify command
+ expected PASS output, and the unmapped-chat rejection behavior (silent-drop vs polite
refusal — record what the product actually does; do not invent).

## 6. Reset & readiness

**HB-R1 (demo-reset extension).** Added to the E-4/`demo-reset` family, never forked:
clear Hebe *session* state (conversations, drafts, pending approvals, routine RUN history
younger than the fixtures) · **preserve** the two standing routines, the workspace
fixtures, the chat_user_map, receipts (append-only — receipts are NEVER reset; the chain
is the point) · re-fire nothing (pre-show does the firing). Idempotent; runs alongside the
Kantheon-demo reset without breaking its preserve-list (cross-check against Stage 3.5 T1).

**HB-R2 (pre-show).** T-60: HB-R1 → fire `monday-brief` (phone shows the Beat-1 message)
→ verify console + Iris logins (TLS per ops-manual §2) → run one warm throwaway turn →
verify Telegram round-trip both directions → receipts chain-verify green → print the beat
sheet checklist.

**HB-B (the bar):**

1. instance green: pod Healthy, registered+heartbeating, doctor clean;
2. Beat 1–6 each runnable from its beat sheet by a non-builder;
3. memory answers graded green against `memory-answers.md` (facts + source);
4. delegation turn visible in Iris history with the scheduled/origin badge;
5. AWAITING_AGENT hand-back round-trips (phone → Iris → completion);
6. governance strikes behave as recorded (refusal receipted; chain verify PASS; stranger
   rejected);
7. **dry run: the full arc twice consecutively, ≤ 20′, zero operator intervention**
   (LLM wording variance allowed; *fact* variance = fail);
8. HB-R1 → repeat → same result.

## 7. Issue routing

Product defects → kantheon repo issues tagged `hebe-demo`, linked in `findings.md` here;
honest-degradation beat variants meanwhile (inherited SD-D2 discipline). Cluster changes →
olymp PRs; realm/fixture changes shared with the Kantheon demo → through the E-4 fixture
scripts only.
