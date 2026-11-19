# OpenMetadata layout pack

LD P1·S1.2, OpenMetadata 2.0.6. Stdlib Python only. The allow-list in `targets.json`
enables bp-dsk; hartland is disabled until a showing is explicitly requested.
Neither a pin nor an image is changed by this pack.

Set `OM_TOKEN` or `OM_TOKEN_FILE` (the latter names a readable token file).
Use `OM_CA_FILE` for a custom CA bundle if needed. Credentials and response bodies
are never printed; redirects are refused. All four verbs require an admin.

```
just om-layout plan bp-dsk       # read-only; plan is also the Python default
just om-layout apply bp-dsk      # execute LD-C12, then verify
just om-layout verify bp-dsk     # read-only; exit code is the failed check count
just om-layout remove bp-dsk     # read-only deletion preview
python3 scripts/om_layout.py remove --target bp-dsk --execute
just om-layout-test              # offline fake catalog
```

The pack owns theme values, the three named personas and their two documents,
relation types with inverses, three accounts, Sales team, four domains, the
suggestion workflow/form, three frozen tasks and the Model published announcement.
It edits only the named projected terms, CZ customer table and revenue metric in
`content.json`. Unrelated fields, custom properties and relation edges are retained.
The admin belongs to all three personas and stays on Stock view.

`apply` follows LD-C12: fields before tasks; reviewers afterwards, so the terms
are approved through their own OpenMetadata approval task after reviewers are set.
Customer found In Review on a later run is repaired through that task. No status is
written directly. If Petr and admin both receive a refusal, the reviewer is removed
and the reason is reported as a skip. Tasks are found by Customer and New value, checked against the
owned form, and resumed to their frozen stages without repeating comments or
transitions. It renews the announcement's 90-day end time; other operations are
unchanged on a second run. `verify` checks 1–15. Table, Metric and Home layouts,
`export` and the show sheet belong to S1.3.

Set `OM_DEMO_PASSWORD` to create and sign in as the two people. It never resets an
existing person's password. Without it, new people receive separate random
passwords that are discarded, and all task actions use the admin. `plan` says so.
When provided, person sign-in and the bot JWT are kept only in memory; a failed
sign-in falls back to the admin with a diagnostic. No actor attribution is forged.
New bots get an hour-long JWT; the owned bot token is renewed if it is near expiry.
An unavailable bot token uses the same fallback. Reference lists compare as sets,
so server ordering does not cause repeated updates.

The HTML chat source is copied unchanged from the frozen planning asset. Apply
writes `build/change-1-golem-chat.html` with the odběratel task URL and number;
open that file locally. Nothing on the page loads from the network. Plans do not
write it. All generated output is ignored by Git.

`remove` previews deletion of owned objects and requires `--execute` to perform
it. It never deletes or reverses projected terms, tables or metrics. It prints
the fresh-state projection Job command for the selected cluster, following
`design/demo-openmetadata.md`; it does not run that command. Apply the pack after
any projection run. No local state file is kept.

The API shapes follow OpenMetadata's official `2.0.6-release` schemas:
[theme](https://github.com/open-metadata/OpenMetadata/blob/2.0.6-release/openmetadata-spec/src/main/resources/json/schema/configuration/uiThemePreference.json),
[relations](https://github.com/open-metadata/OpenMetadata/blob/2.0.6-release/openmetadata-spec/src/main/resources/json/schema/configuration/glossaryTermRelationSettings.json),
[personas](https://github.com/open-metadata/OpenMetadata/blob/2.0.6-release/openmetadata-spec/src/main/resources/json/schema/api/teams/createPersona.json).

Brand SVGs are copied verbatim from `Collite/kantheon`,
`frontends/iris/src/assets/brand/`, source commit
`3b9245e8f7ef16e130fbbd0bf78c8b0106716439`. They are encoded as SVG data URLs.
Only primary/panel/warning/selected/hover colors and the three image fields are
owned; error, success and info are preserved. If a field fails the browser check,
its path is emptied in `theme.json` and `imageSkips` records the reason, printed
by `plan`. No image hosting is required.

`persona-ui/` is the bp-dsk document snapshot read on 2026-11-19, before any pack
write: navigation and GlossaryTerm only, as authored on 2026-11-17. Server ids,
versions, timestamps, hrefs and change history are omitted. Tab `id`, navigation
`id` and widget `i` remain: these are UI keys, not server entity identities.
The stored navigation titles are retained even though OM ignores their text;
Settings is the stock bottom menu. Table, Metric and Home are left for S1.3.
