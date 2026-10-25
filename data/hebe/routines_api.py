"""Install, list and fire Hebe routines over her console's /api/routines (HE contracts §5a; HE-P1 · S1.3 T5).

    python3 -I routines_api.py --url http://127.0.0.1:18765 install routines/*.json
    python3 -I routines_api.py --edge hebe.hartland.collite.cz install routines/*.json   # signs in as marketa
    python3 -I routines_api.py --url … fire monday-brief
    python3 -I routines_api.py --url … list

--url talks to the instance directly: over a port-forward Hebe sees a loopback caller and admits it as `local`.
--edge goes through the public console edge instead, signed in as --user (default marketa) with the persona password
from $HEBE_VERIFY_PASSWORD (the rig's edge_login.py flow; the password never rides argv). This is the same call
`hebe routines install|list|fire` makes, without needing the hebe binary on this machine. Install is idempotent by
name (201 created · 200 updated, same id). Standard library only.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "design" / "hebe-demo" / "rig-hb"))
from edge_login import login_form_action  # noqa: E402  (the rig's Keycloak form parser)


class Console:
    def __init__(self, base: str, opener: urllib.request.OpenerDirector) -> None:
        self.base = base.rstrip("/")
        self.opener = opener

    def call(self, method: str, path: str, body: bytes | None = None) -> tuple[int, dict | str]:
        req = urllib.request.Request(self.base + path, data=body, method=method)
        req.add_header("Content-Type", "application/json")  # every console write must say so (else 415)
        try:
            with self.opener.open(req, timeout=60) as r:
                raw = r.read().decode("utf-8", "replace")
                status = r.status
        except urllib.error.HTTPError as e:
            raw, status = e.read().decode("utf-8", "replace"), e.code
        try:
            return status, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return status, raw[:300]


def direct(url: str) -> Console:
    return Console(url, urllib.request.build_opener())


def through_edge(host: str, user: str, password: str) -> Console:
    """The browser flow edge_login.py drives, keeping the edge's cookies for the calls that follow."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    with opener.open(f"https://{host}/api/status", timeout=30) as r:
        page = r.read().decode("utf-8", "replace")
    action = login_form_action(page)
    if not action:
        raise SystemExit(f"no Keycloak login form behind https://{host}/api/status")
    form = urllib.parse.urlencode({"username": user, "password": password, "credentialId": ""}).encode()
    with opener.open(urllib.request.Request(action, data=form, method="POST"), timeout=30) as r:
        if urllib.parse.urlparse(r.geturl()).hostname != host:
            raise SystemExit(f"the sign-in as {user} did not come back to the console (ended at {r.geturl()})")
    return Console(f"https://{host}", opener)


def install(console: Console, files: list[str]) -> int:
    failed = 0
    for f in files:
        status, body = console.call("POST", "/api/routines", pathlib.Path(f).read_bytes())
        if status in (200, 201) and isinstance(body, dict):
            verb = "installed" if status == 201 else "updated"
            on = "on" if body.get("enabled") else "off"
            print(f"{verb:9} {body.get('name')} ({body.get('id')}) cron '{body.get('cron')}' {on}, next {body.get('nextRunAt')}")
        else:
            failed += 1
            print(f"FAILED    {f}: HTTP {status} {body}", file=sys.stderr)
    return 1 if failed else 0


def fire(console: Console, name: str) -> int:
    status, body = console.call("POST", f"/api/routines/{urllib.parse.quote(name, safe='')}/fire")
    if status == 202 and isinstance(body, dict):
        print(f"fired {name} → job {body.get('jobId')}")
        return 0
    print(f"FAILED    fire {name}: HTTP {status} {body}", file=sys.stderr)
    return 1


def list_routines(console: Console) -> int:
    status, body = console.call("GET", "/api/routines")
    if status != 200 or not isinstance(body, dict):
        print(f"FAILED    list: HTTP {status} {body}", file=sys.stderr)
        return 1
    for r in body.get("routines", []):
        on = "on " if r.get("enabled") else "off"
        print(f"{r.get('name'):16} {on} {r.get('cron'):14} next {r.get('nextRunAt')}  last {r.get('lastRunAt')}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    where = p.add_mutually_exclusive_group(required=True)
    where.add_argument("--url", help="the instance's console base URL (a port-forward)")
    where.add_argument("--edge", metavar="HOST", help="the public console host, signed in as --user")
    p.add_argument("--user", default="marketa")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("install").add_argument("files", nargs="+")
    sub.add_parser("fire").add_argument("name")
    sub.add_parser("list")
    a = p.parse_args()

    if a.edge:
        password = os.environ.get("HEBE_VERIFY_PASSWORD", "")
        if not password:
            raise SystemExit("--edge signs in as a persona: set HEBE_VERIFY_PASSWORD")
        console = through_edge(a.edge, a.user, password)
    else:
        console = direct(a.url)

    if a.cmd == "install":
        return install(console, a.files)
    if a.cmd == "fire":
        return fire(console, a.name)
    return list_routines(console)


if __name__ == "__main__":
    sys.exit(main())
