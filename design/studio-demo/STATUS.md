---
effort: SD — Tatrman Studio demo on Hartland (FO-A1 Designer + FO-A2 Planner)
repo_home: Collite/ttr-demo/design/studio-demo
code_home: [Collite/ttr-demo (model delta, data/plan, rig/), tatrman + tatrman-platform (consumed read-only at pinned SHAs)]
state: ready
phase: corpus authored 2026-07-23 + **⚑SD-1…5 ALL RULED same day** (A on Bora's machine / Rancher Desktop docker → C graduation; identity relaxed for A; ⚑3 per P0 probe; Satellite R out for A); nothing executed
next: "SD-P0 (pre-flight probes T3–T5 on Rancher Desktop docker). Nothing blocks it; waits only on Bora's go."
blocked_on: []
gates: ["SD-D2: demo consumes closed arcs — product defects route to owning repos", "P4b (cluster graduation) opens only after the P5 dry-run + freeze-calendar check (⚑5)", "real Keycloak/SSO + Satellite-R reconsideration ride P4b, not A"]
updated: "2026-09-28 (Cowork refresh: blocked_on cleared)"
stream: dev
lane: unassigned (suggestion: one senior lane; P2 ∥ P3 fork if two)
---

The demo of the closed FO-A1 (Studio Modeler + Studio Designer) and FO-A2 (Studio Planner)
arcs on the Hartland world: February-2026 sequel to the January Kantheon demo — *"you
watched agents find the meltdown; now watch people plan the recovery"*. Deterministic
end-to-end (PF P-2), Studio vocabulary only (FO-33/FO-30), demo assets in this repo (BM-9).

Corpus: [`00-demo-narrative.md`](./00-demo-narrative.md) (Beats 0/1/M/D/P + satellites) ·
[`architecture.md`](./architecture.md) (estate, SD-D1…7, ⚑1…5) · [`contracts.md`](./contracts.md)
(plan-model delta, `hartland_plan`, seed oracle vs R0, form, rig, SD-R1/R2 reset, SD-B bar)
· [`plan.md`](./plan.md) (SD-P0…P5) · [`tasks/00-task-management.md`](./tasks/00-task-management.md).

## 2026-09-28 status refresh (git-verified, Cowork)

The frontmatter was stale; this section is the evidence. Checked against git in ttr-core, ttr-server, kantheon, olymp, ttr-demo and the legacy repos (git evidence reaches 2026-09-25, ai-platform 2026-09-28; `gh` unavailable, PR state read from merge commits and tags). The older sections below/above are history.

- The listed blockers are done: tatrman#104 merged 2026-07-22, platform#23 (fo-a2) merged 2026-07-24. No SD execution commits exist yet; ~5%.
