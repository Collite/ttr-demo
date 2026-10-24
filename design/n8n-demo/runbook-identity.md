# n8n identities

## 1. Bootstrap and verify

The Czech users come from the sibling olymp checkout's realm file:
`platform/auth/keycloak/overlays/hartland/realm/kantheon.json`. Only users with
`attributes.world == ["cz"]` are selected. Markéta (`marketa`) is the instance
owner; Tomáš (`tomas`) and Petr (`petr`) are members. n8n Community Edition uses
its own login. Members see their own workflows; the owner presents the demo.

Passwords live in vault `hartland`: `n8n-owner-password` for Markéta and
`n8n-member-password` shared by the two members. Use your authorized vault access
to obtain the presenter's password. The scripts never display it. The public
realm demo password is refused because n8n accounts can execute workflows in
the cluster.

Before exposing the first n8n pod, have this script ready on the machine with
Azure CLI access. Immediately after that pod becomes Ready, run:

```sh
just n8n-seed-users --mailpit none
just n8n-seed-users --mailpit none --verify
```

`none` claims only the owner, confirms the setup page is closed through
`/rest/settings`, and defers members. It reads only the owner vault key. A repeat
run authenticates the existing owner. An existing owner with another password
must be supplied with that password; the script never resets or replaces users.

After Mailpit and SMTP are ready:

```sh
just n8n-seed-users
just n8n-seed-users --verify
```

The default Mailpit mode is `proxy`: each search/message read uses
`kubectl --context hartland get --raw` through `mailpit-http:80` in namespace
`middleware`. No port forward is required. The bootstrap invites missing members,
reads each new invitation from Mailpit, accepts it, and confirms the new login.
Existing active accounts are reported `present`. A pending invitation is left
alone and exits 1; use `just n8n-seed-users --reinvite` to explicitly resend and
accept it. Existing mail is ignored when looking for the new invitation.

`--verify` signs in as each selected persona and checks the current-session email
and role. It never claims the owner or sends invitations. With `--mailpit none`,
it checks only the owner. Exit codes are 0 for success, 1 for failed checks or
pending users, and 2 for invalid arguments or realm configuration.

`just n8n-seed-users --dry-run` prints the selected actions without reading the
vault or making HTTP requests. Override the defaults with `N8N_URL`,
`KUBE_CONTEXT`, `VAULT`, `OLYMP_DIR`, `--realm PATH`, `--owner USER`, or
`--mailpit http://127.0.0.1:8025`. A different owner must be a Czech realm user.

For machines without Azure CLI, supply `--owner-password-file PATH` and
`--member-password-file PATH`. Each file must have mode 0600; pass paths only.
The shell wrapper reads unspecified passwords into mode-0600 temporary files
and removes its temporary directory on success, failure, or interruption.
Cookies and signup tokens stay in memory. Do not enable HTTP tracing.

To reset a member password, sign in as the owner and use **Settings → Users → …**
to obtain the user's password-reset link. Complete the reset with the intended
vault password, then run `--verify`. Updating a vault value alone does not change
an existing n8n account's password.

**Break glass:** `n8n user-management:reset` drops ALL users and reopens owner setup.
Use it only as a deliberate recovery operation, with immediate owner claiming
arranged. It is never part of this script or a routine re-seed.

## REST compatibility

This flow is pinned to n8n **2.44.6**. Its internal API can change on an upgrade.
The tests follow the tagged [owner controller](https://github.com/n8n-io/n8n/blob/n8n%402.44.6/packages/cli/src/controllers/owner.controller.ts),
[authentication controller](https://github.com/n8n-io/n8n/blob/n8n%402.44.6/packages/cli/src/controllers/auth.controller.ts),
[users controller](https://github.com/n8n-io/n8n/blob/n8n%402.44.6/packages/cli/src/controllers/users.controller.ts),
[invitation controller](https://github.com/n8n-io/n8n/blob/n8n%402.44.6/packages/cli/src/controllers/invitation.controller.ts),
and [user service](https://github.com/n8n-io/n8n/blob/n8n%402.44.6/packages/cli/src/services/user.service.ts).
In particular, the roster is `{data: {count, items}}`; invitation results are an
array under `data`, and public-user roles are string slugs. Mailpit uses its
[v1 search and message API](https://mailpit.axllent.org/docs/api-v1/).

Unknown responses fail with the endpoint and HTTP status. Settings errors include
at most 200 response bytes; authentication, roster, invitation, and mail bodies
are withheld because they can contain passwords or usable signup tokens.
