# Hartland's first n8n demo

Run [the Czech rehearsal](../../design/n8n-demo/runbook.md) after the reviewed content seed has been merged.

- `cz-denni-prehled.json`: every day at 07:00 Europe/Prague, read the 2025 channel totals from `hartland_cz`,
  format one Czech table and send it to Markéta through Mailpit. This is a fixed reference dataset, **not today's
  sales**. SQL is the exact `core` of `run-set/routing/validation/channel-2025.yaml`, exercised by case
  `a1-2-revenue-by-channel`; its id is in `meta.ttrDemo.runSet`. Three aggregate rows, read-only database role.
- `webhook-echo.json`: `POST /webhook/echo`, authenticated by `X-Demo-Key`, returns only the incoming JSON body.
  It never returns the request headers or the key. The key is generated once by the importer and preserved.

The node shapes were loaded into the n8n 2.44.6 editor and exported on 2026-10-25. Source tag `n8n@2.44.6`:
Schedule 1.4, Postgres 2.7, Code 2, Send Email 2.1, Webhook 2.2, Respond to Webhook 1.5.
Draft authoring does not publish or execute them. Portable files deliberately restore `active: true`, the
Europe/Prague timezone and symbolic credential **names**: editor export strips unresolved credentials.
The importer replaces those names with destination IDs. No instance/workflow/credential id or secret is portable;
node ids and the Webhook node's routing id are retained to keep the graph stable. Keep only the traceable
`meta.ttrDemo` metadata, never the instance metadata, pin data, execution data or exported credentials.

To re-export: open the draft in the pinned editor, edit the nodes, **More actions → Export JSON**, then strip
root `id`, `versionId`, `meta.instanceId`, tags and pin data. Restore the symbolic credential references,
`settings.timezone`, publication intent and run-set metadata above. On the echo file also restore
`meta.ttrDemo.probe: "webhook-echo"`: this portable-only marker requires the keyed echo node even if a
re-export dropped its credential reference. Other Webhook → Respond to Webhook workflows need no demo key.
Never publish a credential-less authoring copy. Review the diff before replacing these files.

```sh
just n8n-seed-content
just n8n-seed-content --verify
just n8n-verify --phase 3
```

The first command restores the reviewed content and publishes its exact draft version; it can replace edits to
these two named workflows. It leaves other workflows alone. `--dir n8n` can import future AU workflows from that
directory; only immediate `*.json` children are selected, so it does not also import `n8n/demo/` recursively.
See the runbook for passwords, the private webhook-key file and reset/rehearsal steps. Never commit credential exports.

Reset is scoped to the signed-in owner’s personal project. Close the demo editors first; reset clears pinned
data and resettable settings, preserves runtime history/state, and verify rejects unsupported setting drift.
See the runbook’s reset section for exact limits.
