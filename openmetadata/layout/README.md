# OpenMetadata layout pack

LD P1·S1.1, OpenMetadata 2.0.6. Stdlib Python only. The allow-list in `targets.json`
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

The pack owns theme values, three named personas, two persona documents, and the
four relation types with their inverses. It adds the admin to all three personas
and leaves the account on Stock view, so there is a route back to the stock UI.
Unrelated settings, relation types and persona memberships are retained.
`remove` deletes those named objects and clears the owned theme values; it never
deletes projected content. No state file is kept. Later LD stages supply content,
Home/Table/Metric layouts and export; the empty LD-C12 steps do nothing here.
Working output lives under ignored `build/` directories.

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
