# Hebe demo — the narrative (draft v0)

> ⟂ **SUPERSEDED as the story input, 2026-11-04 (HE-D-13/14 proposed):** the demo's stories are now
> `project/kantheon/features/hebe/design/06-demo-stories-redesign.md` §4 — Markéta (Czech, HE-D-4), **one phone, one
> bot, no stranger and no second Telegram account** (B-4.4, HE-D-13), the automation recipes (H-1, X-2, the generic
> "any BPMN" beat; H-2/H-3 later) as the spine, mail as Beat 10 when HE-P3 lands. HE-P4 T1 ports that sheet into the
> Czech beat sheets here. This file stays as the July trace (Maya, EN, six beats incl. the dropped stranger strike).

> **The story input for the HB effort** (the Hebe demo on the Hartland world) — third of the
> Hartland demo family: the **Kantheon demo** showed the constellation answering and
> investigating; the **Studio demo** shows deterministic modeling/planning; **this demo shows
> the personal agent** — Hebe, *Maya's own assistant*, running **on the hartland cluster**
> (Bora's preference; the local profile is the fallback, architecture §3). In the January
> demo Hebe appeared for exactly two beats (the inbox brief + create-from-chat); here she is
> the whole show. The final transcript is an HB-P4 deliverable; this draft fixes the arc,
> the beats, and the Requires lines.

## Setting

**Hartland Stores**, the same world. Maya Chen has been living with the platform since
January: the meltdown was found, the recovery is being planned. This demo is about the
*texture of her weeks*: the work that happens **when she isn't looking** — briefs that
arrive before she wakes, questions asked on schedule, an assistant that remembers what she
decided and knows what it is *not allowed* to do.

**The one-sentence pitch:** *"Every agent you've seen so far belongs to the company. This
one belongs to Maya."* Hebe is **single-user by design** — one instance per human, bound to
one identity, invisible to the platform's routing (registered `non_routable`: Themis cannot
send anyone's question to Maya's assistant). Dan doesn't share her Hebe; he'd get his own.

**Cast:** Maya (presenter acts; her Telegram = the phone on stage) · Dan (cameo — as the
*outsider* this time) · the constellation (Golem/Iris/Themis — reached only *through* the
platform door, as Maya).

**On stage:** a phone (Telegram), the Hebe **web console**, and Iris. Substrate (never
named): instance `dev` on the hartland cluster (k8s profile), llm-gateway, Keycloak OBO,
PG-backed memory/workspace/receipts, iris-bff headless client.

---

## Beat 0 — Framing: whose agent is it?

> BORA: *"In January you watched the company's agents: a router, an analyst, an
> investigator. They serve everyone and answer to the platform. Today: the one agent that
> serves exactly one person. Hebe is Maya's — her memory, her schedule, her identity. The
> platform can't even route to her. And everything she does leaves a receipt."*

**Machinery:** hebe registered in capabilities as `non_routable` (visible in list, absent
from routing). **Requires:** cluster instance registered + heartbeating (HB-P1).

## Beat 1 — The phone: work that arrived overnight

The phone buzzes (staged: the "Monday channel health brief" routine fired at pre-show).
Telegram shows: **the brief's conclusion text + artifact count + a deep link into Iris** —
deliberately *no charts in chat* (v1 rule, narrated as honesty: numbers belong where
provenance lives). Bora taps the link → Iris opens the full brief, badged **scheduled** —
the same inbox item the January audience saw, now caught at its *other* end.

> BORA: *"Same brief as January — but notice where it reached her: her pocket, before
> coffee. And notice what the chat message doesn't do: no chart, no numbers out of context —
> a conclusion and a door back into the governed surface. The phone is a doorbell, not a
> dashboard."*

**Machinery:** `kantheon_question` routine → iris-bff (`TurnOrigin.SCHEDULED`) → envelope →
channel rendering (conclusion + artifact counts + deep link) → Telegram delivery + delivery
record. **Requires:** Telegram bot live (⚑HB-3); routine fixture; deep link resolves on the
demo machine (TLS trusted per `../demo-ops-manual.md` §2).

## Beat 2 — Memory: she remembers what Maya decided

Web console (the second stage surface). Maya chats:

- `What did we conclude about the Memphis incident?` → Hebe answers **from her own
  memory/workspace** — the investigation conclusion she noted in January, with *when* and
  *where it came from* — not by querying the warehouse.
- `What did I decide about the win-back promotion?` → her note from the planning session
  (seeded fixture: "November, Marketplace, decided 2026-02-xx").
- Open the **memory browser**: the workspace — `MEMORY.md`, `USER.md`, daily notes — plain
  markdown Maya can read and edit; hybrid search (keyword + semantic) over it.

> BORA: *"Two different kinds of knowing. The warehouse knows what happened to the company;
> Hebe knows what happened to Maya — what she read, what she decided, what she cares about.
> It's hers: markdown files she can open, not an embedding soup she can't audit."*

**Machinery:** PG-backed MemoryStore + workspace (hybrid FTS+vector, RRF); memory browser
in the console. **Requires:** seeded workspace fixtures (HB-P2); console reachable (⚑HB-2).

## Beat 3 — Delegation with identity: Hebe never touches the warehouse

Maya (console or Telegram): `Ask the analytics team how Marketplace revenue developed last
week, and message me the answer.`

Hebe does **not** answer from memory — this is a *data* question. She opens a turn through
**iris-bff as Maya** (OBO — her identity travels), Golem answers it on the governed spine,
and the conclusion comes back to the channel with the deep link. In Iris: the turn sits in
Maya's session history, origin-badged.

> BORA: *"Watch the boundary. Hebe has no database connection, no SQL, no side door — she
> asked the same front door you saw in January, authenticated as Maya, and the answer
> carries the same provenance. A personal agent with your identity is a security nightmare
> — unless identity is enforced below every agent, which is the whole design here."*

**Machinery:** iris-bff headless client, OBO bound user, session per routine/thread; Themis
routes the question normally (Hebe is a *caller*, not a routee). **Requires:** OBO wired
for instance↔maya (HB-P1); a scripted question with a stable answer (seed oracle from the
Kantheon-demo run-set).

## Beat 4 — Routines: schedule it from a sentence

Maya: `Every Friday at 16:00, ask for a weekly returns summary by channel and message me.`

→ Hebe creates the routine (visible in the console's routine monitor: schedule, body,
last/next run). Bora fires it manually (demo can't wait for Friday) → the loop runs
end-to-end → phone buzzes → deep link. Then the January callback: *"the Monday brief you
saw in Beat 1 was created exactly this way — you watched Maya do it in the January demo's
closing beat."*

**Machinery:** routine CRUD from chat + console; manual fire; delivery records;
never-silent-failure policy. **Requires:** the Friday-returns routine scripted with oracle
numbers; retry/failure path rehearsed (kill iris-bff variant → failure *notification*, not
silence — a drill, maybe a fallback-only beat).

## Beat 5 — The hand-back: when the platform needs a human

The staged variant: a scheduled question deliberately missing a parameter (the same
param-fill machinery from January). The routine run parks as **AWAITING_AGENT**; the phone
gets: *"Your Friday summary needs an answer from you — continue in Iris"* + deep link.
Bora taps, answers the clarification in Iris, the turn completes.

> BORA: *"The agent didn't guess, didn't stall, didn't fail silently. It parked the work,
> told the human where to pick it up, and the thread continued in the governed surface with
> the whole context intact. That's what 'autonomous' should mean: knows when it isn't."*

**Machinery:** stream-state mapping → `AWAITING_AGENT` → channel message + Iris deep link
(human resumes in Iris — v1 rule). **Requires:** a reliably-clarifying question (engineer
it from the golem param-fill behavior — quirks §5.3 one-param-at-a-time).

## Beat 6 — Governance cameo: the leash, shown honestly

Three quick strikes:

1. **Posture.** Maya: `Run a shell command to check disk space on the cluster.` → refusal —
   the k8s profile runs the **restricted tool posture**; the refusal itself is receipted.
2. **Receipts.** Console (or CLI): the receipts view — every tool call, every delivery,
   **hash-chained and signed**; run the chain verify live. *"Tamper with one line and the
   chain breaks."*
3. **The stranger.** Dan (second phone / second Telegram account) texts Maya's bot →
   **rejected** — unmapped chat; single-operator allowlist; nothing enters the loop.
   *"Dan gets his own Hebe. This one doesn't talk to him."*
   And the cost line: every LLM call Hebe makes is metered through the gateway under
   `hebe/dev` — the assistant has a budget, not a blank check.

**Machinery:** tool posture matrix + dispatcher refusal receipts; Ed25519 hash-chained
receipts + verify; `chat_user_map` enforcement; llm-gateway cost attribution
(`X-Cost-Center`). **Requires:** ⚑HB-4 in-scope ruling; second Telegram account at hand.

## Close

> BORA: *"Three demos, one platform. The company's agents answer and investigate. The
> Studio plans and commits. And each person gets one agent that's actually theirs — with
> their memory, their identity, their budget, and a paper trail. The platform doesn't trust
> Hebe — it doesn't have to. It authenticates her, meters her, and receipts her, the same
> as everyone else at the door."*

## Pockets (if time)

- **Heartbeat:** `HEARTBEAT.md` watch — silence when OK, a message when not (narrate; a
  live heartbeat demo needs a staged non-OK).
- **Doctor:** `hebe doctor` — the instance self-diagnoses its wiring (gateway, Keycloak,
  channels, PG) — the ops-credibility flash.
- **Estop:** name it, don't run it: the human can halt everything with one command.

---

## Beat → build map

| Beat | Depends on | Built in |
|---|---|---|
| 0 framing | registered non_routable instance | HB-P1 |
| 1 phone brief | Telegram + routine fixture + deep links | HB-P1 (channel), HB-P2 (fixture) |
| 2 memory | seeded workspace + console access | HB-P1 (console route), HB-P2 |
| 3 delegation | OBO + scripted question + oracle | HB-P1, HB-P3 |
| 4 routines | create-from-chat + manual fire + Friday fixture | HB-P2, HB-P3 |
| 5 hand-back | AWAITING_AGENT choreography | HB-P3 |
| 6 governance | posture/receipts/chat-map + ⚑HB-4 | HB-P3 |
| close/pockets | all | HB-P4 (script, rehearsal) |
