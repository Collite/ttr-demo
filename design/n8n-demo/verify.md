# Verify n8n on hartland

After the reviewed olymp P1 deployment is merged and Ready, claim the owner immediately with
`just n8n-seed-users --mailpit none` (see [runbook-identity.md](runbook-identity.md)), then run:

```sh
just n8n-verify
```

The rig reads cluster status, public n8n endpoints, and `DB_TYPE` inside the n8n container. It does not
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

Every row runs even when an earlier row fails. Exit 0 means V1–V6 passed; exit 1 means at least one failed;
exit 2 means invalid command arguments or base URL. V7–V11 explicitly print `not yet` for P2/P3/P4 and do
not count as certified. `--help` makes no requests.

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
