#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27", "pyyaml>=6"]
# ///
"""AU-hartland — the demo day's event driver (contracts §6, D-143, AU-hartland P4·S4.1): replays the timeline the
generator planted (data/automation/60-events.sql → data/automation/events/<world>.csv) as **engine messages** to the
process engine of the world's deployment set (processes/sets.json). No webhooks: the Server has no intake (D-143).

    uv run scripts/automation-events.py check  --world cz [--day 2026-10-26 | --demo] [--dry] [--engine-url URL]
    uv run scripts/automation-events.py replay --world cz --engine-url https://…/engine-rest \\
        [--day D | --from TS --to TS | --demo] [--speed 60] [--token-env HARTLAND_DRIVER_TOKEN] [--db-url URL]
        [--approval-due PT2M] [--loop-period PT1M] [--dry-run]

The rows behind every event — the order, the return line, its receipts, credit notes, payments and shipments — are
already in the world's database: `just automation-data` writes the whole planted timeline (contracts §5/§6). replay
therefore writes no business rows; with --db-url it first checks (read-only, psql) that each event's key exists, so a
message never runs ahead of its data.

Each event is one `POST <engine>/message` as `hartland-driver` (the bearer from --token-env; never printed):
  order_placed      → message `order_placed`      starts release_order      (businessKey = the order number)
  line_received     → message `return_requested`  starts return_request     (businessKey = the line id)
  receipt_posted    → message `receipt_posted`    wakes that line's inbound wait
  settlement_posted → message `settlement_posted` wakes that line's settlement wait
A start carries `ttrInput {key: {<column>: <key>}, at: <the event's time>}` (a JSON Object variable — the skeleton's
Open reads it as a Map); a wake carries `ttrEventAt` (the round's clock). A wake no instance is waiting for (the line
is in another loop, or already closed) answers 400 MismatchingMessageCorrelation: printed as `no waiting instance`, not
a failure — the daily timers pick the line up. A START that correlates nothing (no deployed definition subscribes the
message) started no instance that any timer could recover: it stops the run (exit 1), like 401/403 and any other 4xx.
5xx and transport errors retry three times. --dry-run prints the messages and sends nothing.

`check` validates the timeline (seq 1..n in time order, the four kinds, one integer key each); --dry lists the messages
it would send in order; --engine-url also asks the engine that every started key has its instance
(`GET /history/process-instance?processDefinitionKey=…&businessKey=…`).
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

KINDS = ("order_placed", "line_received", "receipt_posted", "settlement_posted")
KEY_OF = {"order_placed": "order_number", "line_received": "line_id", "receipt_posted": "line_id",
          "settlement_posted": "line_id"}
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data" / "automation"
CONF = DATA / "automation.conf"
SETS = ROOT / "processes" / "sets.json"
PRAGUE = dt.timezone(dt.timedelta(hours=1))  # only a fallback for naive --from/--to; the CSV carries offsets
RETRIES = 3
# the process a start message starts (processes/<set>/*.bpmn); wakes start nothing
STARTS = {"order_placed": "release_order", "return_requested": "return_request"}


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


def messages_from_conf(path: pathlib.Path) -> dict[str, str]:
    """automation.conf's `\\set events_message_<kind> '<message>'` — the engine message of each timeline kind."""
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\\set\s+events_message_(\w+)\s+'?([\w.-]+)'?\s*$", line.strip())
        if m:
            found[m.group(1)] = m.group(2)
    missing = [k for k in KINDS if k not in found]
    if missing:
        raise SystemExit(f"automation.conf names no engine message for {', '.join(missing)} (events_message_<kind>)")
    return found


def message(e: Event, names: dict[str, str], approval_due: str | None = None, loop_period: str | None = None) -> dict:
    """The `POST /message` body of one event (Camunda 7 REST)."""
    name = names[e.kind]
    variables: dict[str, Any] = {}
    if name in STARTS:
        ttr_input = {"key": {KEY_OF[e.kind]: e.key}, "at": e.at.isoformat()}
        variables["ttrInput"] = {"value": json.dumps(ttr_input), "type": "Object",
                                 "valueInfo": {"objectTypeName": "java.util.LinkedHashMap",
                                               "serializationDataFormat": "application/json"}}
        if approval_due and name == "order_placed":
            variables["ttrApprovalDueOverride"] = {"value": approval_due, "type": "String"}
        if loop_period and name == "return_requested":
            variables["ttrLoopPeriod"] = {"value": loop_period, "type": "String"}
    else:
        variables["ttrEventAt"] = {"value": e.at.isoformat(), "type": "String"}
    return {"messageName": name, "businessKey": str(e.key), "processVariables": variables, "resultEnabled": True}


def select(events: list[Event], frm: dt.datetime | None, to: dt.datetime | None, demo: bool,
           day: dt.date | None = None) -> list[Event]:
    def prague_day(e: Event) -> dt.date:
        # the timeline is on the Prague clock: the CSV's own offset is the event's local time
        return e.at.date()
    return [e for e in events
            if (frm is None or e.at >= frm) and (to is None or e.at <= to) and (not demo or e.demo)
            and (day is None or prague_day(e) == day)]


def wall_delays(events: list[Event], speed: float) -> list[float]:
    """The wait before each event: the timeline's gap to the previous one ÷ speed (0 = no waiting)."""
    if not speed:
        return [0.0] * len(events)
    return [0.0] + [(b.at - a.at).total_seconds() / speed for a, b in zip(events, events[1:])]


def send(client: httpx.Client, url: str, body: dict, token: str | None,
         sleep: Callable[[float], None] = time.sleep) -> tuple[int, str]:
    """POST once, again up to three times on a 5xx or a transport error (1 s, 2 s, 4 s apart).
    Returns (status, the started/woken instance id or the engine's message)."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    status, detail = 0, "no answer"
    for attempt in range(RETRIES + 1):
        try:
            r = client.post(url, json=body, headers=headers)
            status = r.status_code
            if status < 500:
                try:
                    answer = r.json()
                except ValueError:
                    answer = None
                if 200 <= status < 300 and isinstance(answer, list) and answer:
                    first = answer[0]
                    pi = (first.get("processInstance") or {}).get("id") or (first.get("execution") or {}).get("processInstanceId")
                    detail = pi or "-"
                elif isinstance(answer, dict):
                    detail = str(answer.get("message", ""))[:200]
                else:
                    detail = "-"
                return status, detail
        except httpx.TransportError as exc:
            status, detail = 0, type(exc).__name__
        if attempt < RETRIES:
            sleep(float(2 ** attempt))
    return status, detail


def unmatched(status: int, detail: str) -> bool:
    return status == 400 and ("MismatchingMessageCorrelation" in detail or "No process definition or execution" in detail)


def replay_events(events: list[Event], names: dict[str, str], url: str, token: str | None, speed: float,
                  client: httpx.Client, sleep: Callable[[float], None] = time.sleep, **knobs) -> int:
    for e, wait in zip(events, wall_delays(events, speed)):
        if wait > 0:
            sleep(wait)
        body = message(e, names, **knobs)
        status, detail = send(client, url, body, token, sleep=sleep)
        label = f"{e.seq} {e.at.isoformat()} {body['messageName']} {e.key}"
        if 200 <= status < 300:
            print(f"{label} → {detail}")
        elif unmatched(status, detail) and body["messageName"] not in STARTS:
            # a wake nobody waits for: the line is in another loop or closed, and its daily timer picks it up
            print(f"{label} → no waiting instance")
        elif unmatched(status, detail):
            # a start that started nothing: no definition subscribes the message — nothing would ever recover it
            print(f"{label} → {status} no process definition starts on {body['messageName']} — stopping")
            return 1
        else:
            print(f"{label} → {status or 'no answer'} {detail} — stopping")
            return 1
    return 0


def check_instances(events: list[Event], names: dict[str, str], engine: str, token: str | None,
                    client: httpx.Client) -> list[str]:
    """Every start of the selection has its instance on the engine (running or ended)."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    problems = []
    for e in events:
        process = STARTS.get(names[e.kind])
        if not process:
            continue
        r = client.get(f"{engine}/history/process-instance",
                       params={"processDefinitionKey": process, "processInstanceBusinessKey": str(e.key)}, headers=headers)
        if r.status_code != 200:
            problems.append(f"seq {e.seq}: the engine answered {r.status_code} for {process} {e.key}")
        elif not r.json():
            problems.append(f"seq {e.seq}: no {process} instance for {e.key}")
    return problems


def ts(text: str | None) -> dt.datetime | None:
    if not text:
        return None
    t = parse_at(text)
    return t if t.tzinfo else t.replace(tzinfo=PRAGUE)


def default_csv(world: str) -> pathlib.Path:
    return DATA / "events" / f"{world}.csv"


def engine_of() -> str | None:
    """The engine REST url the world's deployment set targets (the world file's `def executor engine { url }`)."""
    text = (ROOT / "automation" / "worlds" / "demo.ttrm").read_text(encoding="utf-8")
    m = re.search(r'def executor engine \{[^}]*url:\s*"([^"]+)"', text)
    return m.group(1) if m else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AU-hartland demo-day event driver: engine messages (contracts §6, D-143)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--world", required=True, choices=("us", "cz"))
    common.add_argument("--csv", help="default: data/automation/events/<world>.csv")
    common.add_argument("--day", help="only the events of this Prague day (YYYY-MM-DD)")
    common.add_argument("--from", dest="frm", help="first event time (ISO 8601)")
    common.add_argument("--to", help="last event time (ISO 8601)")
    common.add_argument("--demo", action="store_true", help="only the runbook's demo subset")
    common.add_argument("--token-env", default="HARTLAND_DRIVER_TOKEN", help="env var holding the hartland-driver bearer")
    common.add_argument("--engine-url", help="the engine's /engine-rest (default: the world's executor url)")
    c = sub.add_parser("check", parents=[common], help="validate the timeline; --dry lists the messages; "
                                                      "--engine-url checks the started instances")
    c.add_argument("--db-url", help="also check every key exists in this database (psql)")
    c.add_argument("--dry", action="store_true", help="list the messages that replay would send, in order")
    r = sub.add_parser("replay", parents=[common], help="send the timeline as engine messages")
    r.add_argument("--speed", type=float, default=0, help="timeline seconds per wall second (0 = no waiting)")
    r.add_argument("--db-url", help="first check every key exists in this database (psql, read-only)")
    r.add_argument("--approval-due", help="ISO duration replacing a confirmation's due date (a certification walk)")
    r.add_argument("--loop-period", help="ISO duration replacing the return loops' daily timer")
    r.add_argument("--dry-run", action="store_true", help="print the messages, send nothing")
    args = ap.parse_args(argv)

    names = messages_from_conf(CONF)
    events = load(pathlib.Path(args.csv) if args.csv else default_csv(args.world))
    problems = check(events)
    chosen = select(events, ts(args.frm), ts(args.to), args.demo,
                    dt.date.fromisoformat(args.day) if args.day else None)
    if args.db_url and not problems:
        problems += check_world(chosen, args.db_url)
    token = os.environ.get(args.token_env)

    if args.cmd == "check":
        if args.dry:
            for e in chosen:
                print(json.dumps(message(e, names), ensure_ascii=False))
        if args.engine_url and not problems:
            with httpx.Client(timeout=30) as client:
                problems += check_instances(chosen, names, args.engine_url.rstrip("/"), token, client)
        for p in problems:
            print(p)
        print(f"{len(events)} events, {sum(e.demo for e in events)} demo, {len(chosen)} selected, {len(problems)} problems")
        return 1 if problems else 0

    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    knobs = {"approval_due": args.approval_due, "loop_period": args.loop_period}
    if args.dry_run:
        for e in chosen:
            print(json.dumps(message(e, names, **knobs), ensure_ascii=False))
        return 0
    engine = (args.engine_url or engine_of() or "").rstrip("/")
    if not engine:
        ap.error("replay needs --engine-url (or --dry-run)")
    if not token:
        ap.error(f"replay needs the hartland-driver bearer in ${args.token_env}")
    with httpx.Client(timeout=30) as client:
        return replay_events(chosen, names, f"{engine}/message", token, args.speed, client, **knobs)


if __name__ == "__main__":
    sys.exit(main())
