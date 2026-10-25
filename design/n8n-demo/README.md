# n8n demo

Designed and planned in `project/common/n8n/` (the sibling private planning checkout).
The identity bootstrap is ready before the deployment so the owner can be claimed
immediately. See [the identity runbook](runbook-identity.md).

After the P1 platform deployment and owner claim, run the [verification rig](verify.md)
with `just n8n-verify`. Mailpit and demo workflows follow in P2/P3. `just n8n-test`
exercises the seed and rig locally with fake commands and loopback HTTP servers.

P3 content: [the workflows](../../n8n/demo/README.md) and [the Czech rehearsal runbook](runbook.md).
Use `just n8n-seed-content` only after review/merge; `just n8n-verify --phase 3` selects V1–V10.
