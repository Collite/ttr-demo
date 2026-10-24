# n8n demo

Designed and planned in `project/common/n8n/` (the sibling private planning checkout).
The identity bootstrap is ready before the deployment so the owner can be claimed
immediately. See [the identity runbook](runbook-identity.md).

The platform deployment, health verification rig, mail sink, and demo workflows
are delivered by subsequent stages. `just n8n-test` exercises the bootstrap locally;
it contacts only fake n8n and Mailpit servers on loopback.
