"""The rig's `brief` row (HE review-152 R9): a routine's last scheduled run reached the inbox and both channels, once.

    python3 -I brief_check.py <console-host> <iris-host> <user> <routine>      ($HEBE_VERIFY_PASSWORD, never argv)

Three reads, all GETs:
  1. the console's GET /api/routines (the edge sign-in): the routine's lastTurnRef and lastRunAt;
  2. iris-bff's GET /bff/v1/inbox as the user (an `iris` client token, the persona recipe): an item of kind `brief` for
     that turn, status DONE, and no second brief of the same session within the retry window (a fire asked twice);
  3. the console's GET /api/receipts: that run's `kantheon.question` receipt delivered to every channel (n/n).
It prints one JSON line: {"verdict": "PASS" | "FAIL", "detail": "..."}. Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import edge_login  # noqa: E402

KEYCLOAK = os.environ.get("HEBE_VERIFY_KEYCLOAK", "https://keycloak.hartland.collite.cz/realms/kantheon")
BODY = 1_000_000
# A fire's retries run within the policy's backoff (60 + 300 + 900 s by default): another brief of the routine's session
# that close is the same fire answered twice. The live case of 2026-10-25 landed 2 minutes apart.
WINDOW = timedelta(minutes=15)


def routine_last_run(routines: dict, name: str) -> tuple[str, str] | None:
    """(lastTurnRef, lastRunAt) of the routine called [name], or None when it never ran (or is not installed)."""
    for r in routines.get("routines", []):
        if r.get("name") == name and r.get("lastTurnRef") and r.get("lastRunAt"):
            return r["lastTurnRef"], r["lastRunAt"]
    return None


def inbox_brief(inbox: dict, turn_id: str) -> dict | None:
    """The inbox's brief item for [turn_id], or None."""
    return next((i for i in inbox.get("items", []) if i.get("kind") == "brief" and i.get("turnId") == turn_id), None)


def _at(ts: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def duplicates(inbox: dict, brief: dict) -> list[dict]:
    """Other briefs of [brief]'s session within [WINDOW]: one fire that reached iris-bff twice (review-152 R2)."""
    at = _at(brief.get("updatedAt"))
    if at is None:
        return []
    return [
        i
        for i in inbox.get("items", [])
        if i.get("kind") == "brief"
        and i is not brief
        and i.get("sessionId") == brief.get("sessionId")
        and (other := _at(i.get("updatedAt"))) is not None
        and abs(other - at) <= WINDOW
    ]


def receipt_deliveries(receipts: dict, turn_id: str) -> tuple[int, int] | None:
    """(delivered, channels) of the run's `kantheon.question` receipt for [turn_id], or None when there is none."""
    rows = receipts.get("receipts", [])
    if isinstance(rows, str):  # Hebe's /api/receipts carries the list as a JSON string
        rows = json.loads(rows)
    for r in rows:
        if r.get("tool") == "kantheon.question" and r.get("turnId") == turn_id:
            m = re.search(r'"deliveries":\s*"?(\d+)/(\d+)', r.get("argsRedacted", ""))
            if m:
                return int(m.group(1)), int(m.group(2))
    return None


def verdict(routines: dict, inbox: dict, receipts: dict, name: str) -> tuple[str, str]:
    last = routine_last_run(routines, name)
    if not last:
        # a hand fire records the turn but not lastRunAt: only a scheduled run counts here
        row = next((r for r in routines.get("routines", []) if r.get("name") == name), None)
        if row is None:
            return "FAIL", f"{name} is not installed"
        return "SKIP", f"{name} has no scheduled run yet (next {row.get('nextRunAt')})"
    turn, at = last
    brief = inbox_brief(inbox, turn)
    if not brief:
        return "FAIL", f"{name}'s last run ({at}, turn {turn}) is not a brief in the inbox"
    if brief.get("status") != "DONE":
        return "FAIL", f"the brief of turn {turn} is {brief.get('status')}, not DONE"
    twice = duplicates(inbox, brief)
    if twice:
        turns = [i.get("turnId") for i in twice]
        return "FAIL", f"the fire is in the inbox {len(twice) + 1}× within {WINDOW.seconds // 60} min (also turns {turns})"
    sent = receipt_deliveries(receipts, turn)
    if not sent:
        return "FAIL", f"no kantheon.question receipt for turn {turn} among the recent receipts"
    if sent[0] != sent[1] or sent[1] == 0:
        return "FAIL", f"the run delivered {sent[0]}/{sent[1]}"
    return "PASS", f"{name} at {at}: one brief (turn {turn[:8]}…) DONE in the inbox, delivered {sent[0]}/{sent[1]}"


def iris_token(user: str, password: str) -> str:
    form = urllib.parse.urlencode(
        {"grant_type": "password", "client_id": "iris", "username": user, "password": password, "scope": "openid"}
    ).encode()
    with urllib.request.urlopen(urllib.request.Request(f"{KEYCLOAK}/protocol/openid-connect/token", data=form), timeout=30) as r:
        return json.load(r)["access_token"]


def console_json(host: str, user: str, password: str, path: str) -> dict:
    res = edge_login.sign_in(host, user, password, path, None, BODY)
    if res.get("status") != 200:
        raise RuntimeError(f"GET {path} → {res.get('status')}: {res.get('error') or res.get('body', '')[:120]}")
    return json.loads(res["body"])


def main() -> int:
    console_host, iris_host, user, routine = sys.argv[1:5]
    password = os.environ.get("HEBE_VERIFY_PASSWORD", "")
    if not password:
        print(json.dumps({"verdict": "SKIP", "detail": "HEBE_VERIFY_PASSWORD is not set"}))
        return 0
    try:
        routines = console_json(console_host, user, password, "/api/routines")
        receipts = console_json(console_host, user, password, "/api/receipts?limit=20")
        req = urllib.request.Request(
            f"https://{iris_host}/bff/v1/inbox", headers={"Authorization": f"Bearer {iris_token(user, password)}"}
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            inbox = json.load(r)
    except Exception as e:  # noqa: BLE001 — any read that fails is the row's failure, said
        print(json.dumps({"verdict": "FAIL", "detail": f"read failed: {e}"}))
        return 0
    v, detail = verdict(routines, inbox, receipts, routine)
    print(json.dumps({"verdict": v, "detail": detail}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
