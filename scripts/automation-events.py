#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27", "pyyaml>=6"]
# ///
"""AU-hartland — the demo day's event driver (contracts §6, ⚑AU-P-8): replays the timeline the generator wrote
(data/automation/60-events.sql → data/automation/events/<world>.csv) as webhooks to the Server's HTTP connector.

    uv run scripts/automation-events.py check --world us [--csv PATH] [--db-url URL]
    uv run scripts/automation-events.py replay --world us --url https://…/automation/webhooks/events \\
        [--from TS] [--to TS] [--speed 60] [--demo] [--dry-run] [--token-env AUTOMATION_EVENTS_TOKEN] [--config FILE]
    uv run scripts/automation-events.py init-config [--out FILE]

`check` validates the timeline without a cluster: seq runs 1..n in time order, every kind is one of the four,
every payload names exactly its kind's key. With --db-url it also asks the world (psql) that every key exists.
`replay` POSTs one body per event — `{deployment, event, payload, idempotencyKey: "events:<world>:<seq>"}`, the
connector's inbound event shape (ttr-server contracts §1.4) — waiting the timeline's gaps divided by --speed
(0 = no waiting); a 5xx is retried three times with backoff; a 409 is an event already posted (idempotent, so a
replay of a replay is fine); any other 4xx stops the run (exit 1). --dry-run prints the bodies and posts nothing,
so it works before the Server exists. The deployment of each kind is automation.conf's
`events_deployment_<kind>`; `init-config` writes them as the YAML --config reads.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx
import yaml

KINDS = ("order_placed", "line_received", "receipt_posted", "settlement_posted")
KEY_OF = {"order_placed": "order_number", "line_received": "line_id", "receipt_posted": "line_id",
          "settlement_posted": "line_id"}
HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE.parent / "data" / "automation"
CONF = DATA / "automation.conf"
RETRIES = 3


@dataclass(frozen=True)
class Event:
    seq: int
    kind: str
    at: dt.datetime
    payload: dict
    demo: bool

    @property
    def key(self) -> Any:
        return self.payload.get(KEY_OF.get(self.kind, ""))


def parse_at(text: str) -> dt.datetime:
    # Postgres prints an offset as +01 when it has no minutes; fromisoformat wants +01:00 on every 3.11
    text = text.strip()
    if re.search(r"[+-]\d\d$", text):
        text += ":00"
    return dt.datetime.fromisoformat(text)


def load(path: pathlib.Path) -> list[Event]:
    with open(path, newline="", encoding="utf-8") as f:
        return [Event(int(r["seq"]), r["kind"], parse_at(r["at"]), json.loads(r["payload"]),
                      r["demo"].strip().lower() in ("t", "true", "1"))
                for r in csv.DictReader(f)]


def check(events: list[Event]) -> list[str]:
    problems = []
    for i, e in enumerate(events):
        if e.seq != i + 1:
            problems.append(f"seq {e.seq} at position {i + 1}: seq must run 1..n")
        if i and e.at < events[i - 1].at:
            problems.append(f"seq {e.seq} at {e.at.isoformat()} is before seq {events[i - 1].seq}")
        if e.kind not in KINDS:
            problems.append(f"seq {e.seq}: unknown kind {e.kind!r}")
            continue
        if set(e.payload) != {KEY_OF[e.kind]} or not isinstance(e.key, int):
            problems.append(f"seq {e.seq}: a {e.kind} payload is {{{KEY_OF[e.kind]}: <int>}}, got {e.payload}")
    return problems


def check_world(events: list[Event], db_url: str) -> list[str]:
    """Every key exists in the world: an open order, or a return line (psql; read-only)."""
    def ids(sql: str) -> set[int]:
        out = subprocess.run(["psql", "-X", "-tA", "-v", "ON_ERROR_STOP=1", db_url, "-c", sql],
                             check=True, capture_output=True, text=True).stdout
        return {int(x) for x in out.split()}
    orders = ids("SELECT so_order_number FROM sales_order WHERE so_state IN ('placed', 'held')")
    lines = ids("SELECT rl_line_id FROM return_request_line")
    return [f"seq {e.seq}: {e.kind} {e.key} is not in the world"
            for e in events if e.key not in (orders if e.kind == "order_placed" else lines)]


def body(e: Event, world: str, deployments: dict[str, str]) -> dict:
    return {"deployment": deployments[e.kind], "event": e.kind, "payload": e.payload,
            "idempotencyKey": f"events:{world}:{e.seq}"}


def select(events: list[Event], frm: dt.datetime | None, to: dt.datetime | None, demo: bool) -> list[Event]:
    return [e for e in events
            if (frm is None or e.at >= frm) and (to is None or e.at <= to) and (not demo or e.demo)]


def wall_delays(events: list[Event], speed: float) -> list[float]:
    """The wait before each event: the timeline's gap to the previous one ÷ speed (0 = no waiting)."""
    if not speed:
        return [0.0] * len(events)
    return [0.0] + [(b.at - a.at).total_seconds() / speed for a, b in zip(events, events[1:])]


def post(client: httpx.Client, url: str, payload: dict, token: str | None,
         sleep: Callable[[float], None] = time.sleep) -> tuple[int, str | None]:
    """POST once, and again up to three times on a 5xx or a transport error (1 s, 2 s, 4 s apart)."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    status, run = 0, None
    for attempt in range(RETRIES + 1):
        try:
            r = client.post(url, json=payload, headers=headers)
            status = r.status_code
            if status < 500:
                try:
                    run = r.json().get("runId")
                except (ValueError, AttributeError):
                    run = None
                return status, run
        except httpx.TransportError:
            status = 0
        if attempt < RETRIES:
            sleep(float(2 ** attempt))
    return status, run


def replay_events(events: list[Event], world: str, url: str, deployments: dict[str, str], token: str | None,
                  speed: float, client: httpx.Client, sleep: Callable[[float], None] = time.sleep) -> int:
    for e, wait in zip(events, wall_delays(events, speed)):
        if wait > 0:
            sleep(wait)
        status, run = post(client, url, body(e, world, deployments), token, sleep=sleep)
        if status == 409:
            print(f"{e.seq} {e.kind} {e.key} → 409 (already posted)")
        elif 200 <= status < 300:
            print(f"{e.seq} {e.kind} {e.key} → {status} {run or '-'}")
        else:
            print(f"{e.seq} {e.kind} {e.key} → {status or 'no answer'} — stopping")
            return 1
    return 0


def deployments_from_conf(path: pathlib.Path) -> dict[str, str]:
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\\set\s+events_deployment_(\w+)\s+'?([\w.-]+)'?\s*$", line.strip())
        if m:
            found[m.group(1)] = m.group(2)
    return found


def load_deployments(config: str | None) -> dict[str, str]:
    deployments = (yaml.safe_load(pathlib.Path(config).read_text(encoding="utf-8")) or {}).get("deployments", {}) \
        if config else deployments_from_conf(CONF)
    missing = [k for k in KINDS if k not in deployments]
    if missing:
        raise SystemExit(f"no deployment for {', '.join(missing)} — automation.conf events_deployment_* / --config")
    return deployments


def ts(text: str | None) -> dt.datetime | None:
    if not text:
        return None
    t = parse_at(text)
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def default_csv(world: str) -> pathlib.Path:
    return DATA / "events" / f"{world}.csv"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AU-hartland demo-day event driver (contracts §6)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="validate a world's timeline (no cluster)")
    c.add_argument("--world", required=True, choices=("us", "cz"))
    c.add_argument("--csv", help="default: data/automation/events/<world>.csv")
    c.add_argument("--db-url", help="also check every key exists in this database (psql)")
    r = sub.add_parser("replay", help="post the timeline as webhooks")
    r.add_argument("--world", required=True, choices=("us", "cz"))
    r.add_argument("--url", help="the connector's event endpoint (required unless --dry-run)")
    r.add_argument("--csv", help="default: data/automation/events/<world>.csv")
    r.add_argument("--config", help="YAML {deployments: {kind: name}} — default: automation.conf")
    r.add_argument("--from", dest="frm", help="first event time (ISO 8601)")
    r.add_argument("--to", help="last event time (ISO 8601)")
    r.add_argument("--speed", type=float, default=0, help="timeline seconds per wall second (0 = no waiting)")
    r.add_argument("--demo", action="store_true", help="only the demo-speed subset")
    r.add_argument("--dry-run", action="store_true", help="print the bodies, post nothing")
    r.add_argument("--token-env", default="AUTOMATION_EVENTS_TOKEN", help="env var holding the bearer token")
    i = sub.add_parser("init-config", help="write automation.conf's deployments as YAML")
    i.add_argument("--out", help="default: stdout")
    args = ap.parse_args(argv)

    if args.cmd == "init-config":
        text = yaml.safe_dump({"deployments": load_deployments(None)}, sort_keys=False)
        if args.out:
            pathlib.Path(args.out).write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
        return 0

    events = load(pathlib.Path(args.csv) if args.csv else default_csv(args.world))
    if args.cmd == "check":
        problems = check(events) + (check_world(events, args.db_url) if args.db_url else [])
        for p in problems:
            print(p)
        print(f"{len(events)} events, {sum(e.demo for e in events)} demo, {len(problems)} problems")
        return 1 if problems else 0

    problems = check(events)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    deployments = load_deployments(args.config)
    chosen = select(events, ts(args.frm), ts(args.to), args.demo)
    if args.dry_run:
        for e in chosen:
            print(json.dumps(body(e, args.world, deployments), ensure_ascii=False))
        return 0
    if not args.url:
        ap.error("replay needs --url (or --dry-run)")
    with httpx.Client(timeout=30) as client:
        return replay_events(chosen, args.world, args.url, deployments, os.environ.get(args.token_env), args.speed, client)


if __name__ == "__main__":
    sys.exit(main())
