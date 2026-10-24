"""Sign in through the hebe console's OIDC edge as one persona and report what the console answered.

    python3 -I edge_login.py <host> <user> [--forge-identity <name>] [--path /api/status]

The persona's password comes from $HEBE_VERIFY_PASSWORD, never argv. It follows the real browser flow: GET the console
→ 302 to Keycloak → POST the login form → 302 to the edge's /oauth2/callback → the edge sets its cookies → 302 back to
the path → the console's answer. It prints one JSON line: {"status": <the console's HTTP status>, "body": <first 300
chars>}. The status is 0 when the flow broke before the console answered, with "error" saying where.

--forge-identity sends `x-forwarded-user: <name>` on every request, as a client trying to name someone else would. The
edge must strip it (ClientTrafficPolicy earlyRequestHeaders), so the console still sees the signed-in user.

Standard library only (HE-P1 · S1.2 T1, rig-hb/verify.sh).
"""

from __future__ import annotations

import argparse
import html
import http.cookiejar
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


def login_form_action(page: str) -> str | None:
    """The Keycloak login form's action URL (HTML-unescaped), or None when the page has no login form."""
    m = re.search(r'<form[^>]*\bid="kc-form-login"[^>]*\baction="([^"]+)"', page) or re.search(
        r'<form[^>]*\baction="([^"]+)"[^>]*\bid="kc-form-login"', page
    )
    return html.unescape(m.group(1)) if m else None


class _Forge(urllib.request.BaseHandler):
    """Adds the forged identity header to every request, redirects included."""

    def __init__(self, name: str) -> None:
        self.name = name

    def http_request(self, req: urllib.request.Request) -> urllib.request.Request:
        req.add_unredirected_header("x-forwarded-user", self.name)
        return req

    https_request = http_request


def sign_in(host: str, user: str, password: str, path: str, forge: str | None) -> dict:
    jar = http.cookiejar.CookieJar()
    handlers: list[urllib.request.BaseHandler] = [urllib.request.HTTPCookieProcessor(jar)]
    if forge:
        handlers.append(_Forge(forge))
    opener = urllib.request.build_opener(*handlers)
    target = f"https://{host}{path}"

    def fetch(req: urllib.request.Request | str) -> tuple[int, str, str]:
        try:
            with opener.open(req, timeout=30) as resp:
                return resp.status, resp.geturl(), resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.geturl(), e.read().decode("utf-8", "replace")

    status, url, page = fetch(target)
    if urllib.parse.urlparse(url).hostname == host:
        return {"status": 0, "error": f"no redirect to the sign-in: the console answered {status} directly", "body": page[:300]}
    action = login_form_action(page)
    if not action:
        return {"status": 0, "error": f"no Keycloak login form at {url} (HTTP {status})", "body": page[:300]}
    form = urllib.parse.urlencode({"username": user, "password": password, "credentialId": ""}).encode()
    status, url, page = fetch(urllib.request.Request(action, data=form, method="POST"))
    if urllib.parse.urlparse(url).hostname != host:
        return {"status": 0, "error": f"the sign-in did not come back to the console (ended at {url}, HTTP {status})", "body": page[:300]}
    return {"status": status, "body": page[:300]}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("host")
    p.add_argument("user")
    p.add_argument("--forge-identity")
    p.add_argument("--path", default="/api/status")
    a = p.parse_args()
    password = os.environ.get("HEBE_VERIFY_PASSWORD", "")
    if not password:
        print(json.dumps({"status": 0, "error": "HEBE_VERIFY_PASSWORD is not set"}))
        return 2
    print(json.dumps(sign_in(a.host, a.user, password, a.path, a.forge_identity)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
