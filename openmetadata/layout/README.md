# OpenMetadata layout pack

LD P1·S1.3, OpenMetadata 2.0.6. Stdlib Python only. The allow-list in `targets.json`
enables bp-dsk; hartland is disabled until a showing is explicitly requested.
Neither a pin nor an image is changed by this pack.

Set `OM_TOKEN` or `OM_TOKEN_FILE` (the latter names a readable token file).
Use `OM_CA_FILE` for a custom CA bundle if needed. Credentials and response bodies
are never printed; redirects are refused. All five verbs require an admin.

```
just om-layout plan bp-dsk       # read-only; plan is also the Python default
just om-layout apply bp-dsk      # execute LD-C12, then verify
just om-layout verify bp-dsk     # read-only; exit code is the failed check count
python3 scripts/om_layout.py export --target bp-dsk --persona ttr-model-steward
python3 scripts/om_layout.py export --target bp-dsk --persona ttr-model-reader
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
unchanged on a second run. `verify` checks 1–16, including Table, Metric and Home
in both documents and the exact four Table tabs (Columns first).

Set `OM_DEMO_PASSWORD` to create and sign in as the two people. It never resets an
existing person's password. Without it, new people receive separate random
passwords that are discarded, and all task actions use the admin. `plan` says so.
When provided, person sign-in and the bot JWT are kept only in memory; a failed
sign-in or HTTP 401/403 action falls back to the admin with a diagnostic. No actor attribution is forged.
New bots get an hour-long JWT; the owned bot token is renewed if it is near expiry.
An unavailable bot token uses the same fallback. Reference lists compare as sets,
so server ordering does not cause repeated updates.

The HTML chat source is copied unchanged from the frozen planning asset. Apply
writes `build/change-1-golem-chat.html` with the odběratel task URL and number;
open that file locally. The supported Customer Changes/tasks address opens its
newest open task, odběratel (raised last); check 15 confirms that it is still first.
Nothing on the page loads from the network. Plans do not
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

`persona-ui/` contains the bp-dsk documents authored in Customize UI and exported
on 2026-11-19: navigation, GlossaryTerm, Table, Metric and Home. The reader has the
same pages with its own Home. `export --persona` strips document/customization
server ids, versions, timestamps, hrefs and change history and writes sorted JSON;
tab/navigation ids and widget keys remain because they identify UI elements.
Only the two owned layout personas may be exported.

The Metric editor keeps its nested Dimensions and Measures panels (amended LD-C7);
Related Metrics is placed below them on the left. Owners/Domain are not separate
widgets on Table/Metric and remain in the header. The Home picker offers no
separate Recently Viewed widget, so LD-C7's omission rule applies; recent-item
shortcuts remain in the stock welcome panel. The sheet records these differences.

For a showing from a clean, already projected bp-dsk catalog: set an admin token
that lasts through setup and `OM_DEMO_PASSWORD`, run `just om-layout apply bp-dsk`,
then `just om-layout verify bp-dsk` (16/16). Open [SCREENS.md](SCREENS.md), sign in
as Petr, and open the generated chat file in a second tab. Apply after any
projection run. The sheet gives all ten addresses, the named account and what to
point at; it does not perform task actions. A completely empty catalog first
needs the existing scan/projection rig in `design/demo-openmetadata.md`. The pack
never creates projected objects. Hartland remains disabled until P2 is called.
