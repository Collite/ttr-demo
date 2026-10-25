# Verify n8n on hartland

After the reviewed olymp P1 deployment is merged and Ready, claim the owner immediately with
`just n8n-seed-users --mailpit none` (see [runbook-identity.md](runbook-identity.md)), then run:

```sh
just n8n-verify
```

By default, the rig reads cluster status, public n8n endpoints, and `DB_TYPE` inside the n8n container. It does not
set up users, sign in, read Secrets, or change cluster resources. It needs `kubectl`, Python 3 and access
to context `hartland`; no Azure login or password is needed for verification.

| Row | Evidence required |
|---|---|
| V1 | middleware Application Synced and Healthy |
| V2 | current Deployment rollout and main pod Ready, pinned image, persistence PVC mounted and Bound |
| V3 | both public health endpoints return HTTP 200, without redirects |
| V4 | public settings explicitly say owner setup is complete |
| V5 | full WebSocket handshake returns validated HTTP 101, or HTTP 401 reaches authentication |
| V6 | runtime DB_TYPE=postgresdb and CNPG has a password Secret resourceVersion for the n8n role |

Every selected row runs even when an earlier row fails. Exit 0 means all selected rows passed; exit 1 means
at least one failed; exit 2 means invalid command arguments or base URL. By default V7–V11 explicitly print
`not yet` for P2/P3/P4 and do not count as certified. `--help` makes no requests.

After Mailpit is deployed and the members have been seeded:

```sh
just n8n-verify --phase 2
```

This selects V1–V9, leaving V10/V11 pending. V7 runs `seed-n8n-users.sh --verify`: it signs in as Markéta,
Tomáš and Petr, checking each current-session identity and role. It never creates accounts or sends invitations.
The wrapper reads the two vault passwords into private temporary files and deletes them afterwards; Azure CLI
access is required unless you supply `--owner-password-file PATH` and `--member-password-file PATH` (0600).
`--realm PATH` or `OLYMP_DIR` selects the realm roster, exactly as for the seed script. Credential values never
enter argv, environment or rig output. V7 fails if the verifier exits nonzero or exceeds 150 seconds; the other
rows still run. For safe per-persona diagnostics, run `just n8n-seed-users --verify` directly.

| Row | Evidence required |
|---|---|
| V7 | owner and Czech members authenticate with the correct email and global role |
| V8 | Mailpit returns 302 to the exact configured Keycloak authorization endpoint; SMTP Service DNS resolves inside n8n-main |
| V9 | Mailpit API Service-proxy search for Tomáš's realm email returns at least one message |

V8 follows no redirects. Override `MAILPIT_URL` and `KEYCLOAK_URL` for a different deployment or local fakes;
they default to `https://mail.hartland.collite.cz` and `https://keycloak.hartland.collite.cz`. URLs with credentials,
fragments or queries are refused before any check or vault read. V9 reads search metadata only and prints a
count; no message body or invitation link is displayed. It proves mail exists for the recipient, not that an
old invitation token remains usable. V8 does not certify role denial or NetworkPolicy enforcement; those
remain separate checks. DNS discovery does not replace the stage's actual SMTP-delivery check.

Override defaults with `KUBE_CONTEXT`, `N8N_URL` (default `https://n8n.hartland.collite.cz`) and `N8N_IMAGE`
(default `docker.n8n.io/n8nio/n8n:2.44.6`). TLS validation stays on; redirects are not followed. Failed
HTTP/command bodies are withheld from output.

V5 sends the complete upgrade headers, a random key, a pushRef and the public Origin. The
[pinned n8n push server](https://github.com/n8n-io/n8n/blob/n8n%402.44.6/packages/cli/src/push/index.ts)
upgrades before Express authentication, so an unauthenticated request can return 101 and then close.
A 401 proves only that authentication was reached. A 426 or 504 fails. The rig does not prove a lasting,
authenticated editor connection: sign in as Markéta in a browser and check that the editor stays
connected for more than 15 seconds, without the “Connection lost” banner. Record that observation in
the shared P1 live checklist. If the push probe fails, inspect the `n8n-push-timeout` BackendTrafficPolicy
status in namespace `middleware`.

Local checks use a fake kubectl and loopback HTTP n8n/Mailpit servers, with no real cluster or credentials:

```sh
just n8n-test
```
