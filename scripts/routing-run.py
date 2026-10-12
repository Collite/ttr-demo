#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27", "pyyaml>=6"]
# ///
"""LR P6 — the routing corpus runner (contracts C-9·3). Corpus: run-set/routing/ (README there).

    uv run scripts/routing-run.py check                       # corpus schema; no cluster (CI)
    uv run scripts/routing-run.py run --world cz [--shadow] [--only id,id] [--out DIR]
    uv run scripts/routing-run.py report results-cz.json [results-us.json] > report.md

`run` asks every case of the DELIVERED world (cz ⇒ the cs question, us ⇒ the en one) as the case's
persona, through the public iris-bff exactly as Iris does (sessions, so follow-ups and asks resume),
reads the turn's protocol (route, fall-through reason, LLM calls, executed SQL), then runs the case's
validation: its `core` SQL once against the world DB (psql) and the assertions over the answer rows.

`--shadow` re-asks every case that answered on the FAST path straight at golem with
`X-Golem-Force-Route: llm-compose` (honoured only where golem runs with GOLEM_EVAL_FORCE_ROUTE=true,
kantheon#181) and scores the LLM lane against the same validation: the shadow parity that LR-6 says
is the only way to widen the door's envelope.

Exit code: 0 = no FAIL/ERROR (XFAIL — a deviation with a filed issue — does not redden); 1 otherwise.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import math
import os
import pathlib
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

ROUTES = ("FAST", "LLM", "ASK", "REFUSE")
WORLD_LOCALE = {"cz": "cs", "us": "en"}
ROUTE_CLASS = {
    "ROUTE_FAST_PATH": "FAST",
    "ROUTE_LLM_COMPOSE": "LLM",
    "ROUTE_PATTERN": "LLM",  # the legacy (no-lattice) composer chain — still the LLM writing the query
    "ROUTE_ASK": "ASK",
    "ROUTE_REFUSAL": "REFUSE",
    "ROUTE_DELEGATED": "DELEGATED",
}
ASSERTIONS = {"row_count", "empty", "row_set", "scalar", "first_row", "text_contains", "columns"}
CASE_KEYS = {
    "id", "title", "act", "shape", "question", "persona", "expected_route", "expected_reason",
    "validation", "session", "resume", "xfail", "notes", "tags",
}
HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_CORPUS = HERE.parent / "run-set" / "routing"


# ── the corpus ───────────────────────────────────────────────────────────────────────────────────


def load_yaml(path: pathlib.Path) -> Any:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8"))


@dataclass
class Case:
    id: str
    raw: dict
    path: pathlib.Path

    @property
    def session(self) -> str | None:
        return self.raw.get("session")

    def question(self, locale: str) -> str | None:
        q = self.raw.get("question") or {}
        return q.get(locale)

    def xfail(self, locale: str) -> str | None:
        return (self.raw.get("xfail") or {}).get(locale)


def load_corpus(root: pathlib.Path) -> tuple[list[Case], dict, list[str]]:
    """(cases sorted by id, personas, schema problems). Problems never raise: `check` lists them all."""
    problems: list[str] = []
    personas = load_yaml(root / "personas.yaml") or {}
    cases: list[Case] = []
    seen: set[str] = set()
    for p in sorted((root / "cases").glob("*.case.yaml")):
        raw = load_yaml(p) or {}
        cid = raw.get("id")
        stem = p.name.removesuffix(".case.yaml")
        where = f"cases/{p.name}"
        if cid != stem:
            problems.append(f"{where}: id {cid!r} != filename stem {stem!r}")
        if cid in seen:
            problems.append(f"{where}: duplicate id {cid!r}")
        seen.add(cid)
        unknown = set(raw) - CASE_KEYS
        if unknown:
            problems.append(f"{where}: unknown keys {sorted(unknown)}")
        q = raw.get("question")
        if not raw.get("resume"):
            if not isinstance(q, dict) or not all(isinstance(q.get(l), str) and q.get(l).strip() for l in ("cs", "en")):
                problems.append(f"{where}: question needs non-empty cs AND en (C-9·2: every question in both languages)")
        else:
            if not raw.get("session"):
                problems.append(f"{where}: a `resume` case must name the `session` it answers in")
        if raw.get("expected_route") not in ROUTES:
            problems.append(f"{where}: expected_route {raw.get('expected_route')!r} not in {ROUTES}")
        if raw.get("expected_reason") and raw.get("expected_route") != "LLM":
            problems.append(f"{where}: expected_reason is for LLM cases only")
        if raw.get("persona", "analyst") not in personas:
            problems.append(f"{where}: persona {raw.get('persona')!r} not in personas.yaml")
        for loc in (raw.get("xfail") or {}):
            if loc not in ("cs", "en"):
                problems.append(f"{where}: xfail key {loc!r} must be cs or en")
        if not raw.get("shape"):
            problems.append(f"{where}: shape is required (the shadow report groups by it)")
        v = raw.get("validation")
        if v:
            vp = root / "validation" / v
            if not vp.exists():
                problems.append(f"{where}: validation/{v} does not exist")
            else:
                doc = load_yaml(vp) or {}
                bad = set((doc.get("assert") or {})) - ASSERTIONS
                if bad:
                    problems.append(f"validation/{v}: unknown assertions {sorted(bad)}")
                if not doc.get("assert"):
                    problems.append(f"validation/{v}: no assertions")
                needs_core = {"row_set", "scalar", "first_row"} & set(doc.get("assert") or {})
                if needs_core and not doc.get("core"):
                    problems.append(f"validation/{v}: {sorted(needs_core)} need `core` SQL")
        cases.append(Case(cid or stem, raw, p))
    # a session's cases run in id order; the first must ask (a resume needs something to answer)
    sessions: dict[str, list[Case]] = {}
    for c in cases:
        if c.session:
            sessions.setdefault(c.session, []).append(c)
    for name, group in sessions.items():
        if group[0].raw.get("resume"):
            problems.append(f"session {name!r}: its first case ({group[0].id}) is a resume")
    return cases, personas, problems


# ── the assertions (pure; specs in test_routing_run.py) ────────────────────────────────────────────


def as_number(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace(" ", "").replace(" ", "")
        if re.fullmatch(r"-?\d+(\.\d+)?([eE]-?\d+)?", s):
            return float(s)
    return None


def norm(v: Any) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip().casefold()


def cell_matches_key(cell: Any, key: Any) -> bool:
    if norm(cell) == norm(key):
        return True
    a, b = as_number(cell), as_number(key)
    if a is not None and b is not None and a == b:
        return True
    # a month/quarter key against a date-shaped cell: 2025-03 / 2025-03-01 / 2025-03-01T00:00:00Z
    if b is not None and b.is_integer() and isinstance(cell, str):
        m = re.match(r"^\d{4}-(\d{2})(-\d{2})?", cell.strip())
        if m and int(m.group(1)) == int(b):
            return True
    return False


def close(a: float, b: float, tol: float) -> bool:
    if a == b:
        return True
    return abs(a - b) <= tol * max(abs(a), abs(b), 1e-12)


def row_numbers(row: dict, scale: list[float]) -> list[float]:
    out = []
    for v in row.values():
        n = as_number(v)
        if n is not None:
            out += [n / s for s in scale]
    return out


def find_row(rows: list[dict], keys: list[Any], value: float | None, tol: float, scale: list[float]) -> int | None:
    for i, r in enumerate(rows):
        cells = list(r.values())
        if not all(any(cell_matches_key(c, k) for c in cells) for k in keys):
            continue
        if value is None or any(close(n, value, tol) for n in row_numbers(r, scale)):
            return i
    return None


def evaluate(assertions: dict, rows: list[dict], text: str, core: list[dict] | None, locale: str) -> list[str]:
    """Every failed assertion as one line; [] = pass."""
    fails: list[str] = []
    # One all-NULL row is how the door answers an aggregate over nothing ("SUM over no rows"); for
    # every assertion it counts as no rows, which is what the user is told („žádná data“).
    rows = [r for r in (rows or []) if any(v is not None for v in r.values())]
    for name, spec in assertions.items():
        if name == "row_count":
            lo, hi = (spec, spec) if isinstance(spec, int) else (spec.get("min", 0), spec.get("max", math.inf))
            if not lo <= len(rows) <= hi:
                fails.append(f"row_count {len(rows)} not in [{lo}, {hi}]")
        elif name == "empty":
            if spec and rows:
                fails.append(f"empty: the answer has {len(rows)} rows")
        elif name == "columns":
            n = max((len(r) for r in rows), default=0)
            if n < spec.get("min", 0):
                fails.append(f"columns {n} < {spec['min']}")
        elif name == "text_contains":
            want = spec.get(locale) if isinstance(spec, dict) else spec
            if want and norm(want) not in norm(text):
                fails.append(f"text lacks {want!r}")
        elif name in ("row_set", "scalar", "first_row"):
            if core is None:
                fails.append(f"{name}: no core rows (core SQL failed)")
                continue
            tol = float(spec.get("tolerance", 0.001))
            scale = [float(s) for s in spec.get("scale", [1])]
            kcols = spec.get("keys", [])
            vcol = spec.get("value")
            if name == "scalar":
                if len(core) != 1:
                    fails.append(f"scalar: core returned {len(core)} rows, want 1")
                    continue
                want = as_number(core[0][vcol])
                if want is None:
                    fails.append(f"scalar: core {vcol} is not a number ({core[0][vcol]!r})")
                elif find_row(rows, [], want, tol, scale) is None and not any(
                    close(n / s, want, tol) for n in _numbers_in(text) for s in scale
                ):
                    fails.append(f"scalar: no answer cell ≈ {want:,.4f} (tol {tol}, scale {scale})")
            elif name == "first_row":
                if not rows:
                    fails.append("first_row: the answer has no rows")
                elif not core:
                    fails.append("first_row: core returned no rows")
                else:
                    keys = [core[0][k] for k in kcols]
                    if find_row(rows[:1], keys, None, tol, scale) is None:
                        fails.append(f"first_row: answer's first row {rows[0]} lacks {keys}")
            else:  # row_set
                misses = []
                pool = list(rows)
                for c in core:
                    keys = [c[k] for k in kcols]
                    want = as_number(c[vcol]) if vcol else None
                    i = find_row(pool, keys, want, tol, scale)
                    if i is None:
                        misses.append({**{k: c[k] for k in kcols}, **({vcol: c[vcol]} if vcol else {})})
                    elif spec.get("pop", True):
                        pool.pop(i)  # one answer row per core row — unless the answer is pivoted (pop: false)
                if misses:
                    fails.append(f"row_set: {len(misses)}/{len(core)} core rows missing, e.g. {misses[:3]}")
                if spec.get("exact") and len(rows) != len(core):
                    fails.append(f"row_set exact: answer {len(rows)} rows vs core {len(core)}")
    return fails


def _numbers_in(text: str) -> list[float]:
    """Numbers written in prose („492 883,66“ / "21,429.72") — for scalar answers given as text."""
    out = []
    for m in re.finditer(r"-?\d[\d  ,.]*\d|\d", text or ""):
        s = m.group(0).replace(" ", "").replace(" ", "")
        if "," in s and "." in s:
            s = s.replace(",", "")  # 21,429.72
        elif "," in s:
            head, _, tail = s.rpartition(",")
            s = f"{head.replace(',', '')}.{tail}" if len(tail) != 3 else s.replace(",", "")
        try:
            out.append(float(s))
        except ValueError:
            pass
    return out


def substitute(sql: str, reference_date: dt.date, params: dict | None = None) -> str:
    """`{reference_date}` (YYYY-MM-DD) and the validation's per-world `params` ({name} → value).

    Params are for the one thing a world-neutral query cannot say by key: a literal the user typed
    in that world's language („Televizor“ / "Television").
    """
    sql = sql.replace("{reference_date}", reference_date.isoformat())
    for k, v in (params or {}).items():
        sql = sql.replace("{" + k + "}", str(v).replace("'", "''"))
    return sql


def classify(route: str | None) -> str:
    return ROUTE_CLASS.get(route or "", "NONE")


def verdict(route_ok: bool, reason_ok: bool, fails: list[str], error: str | None, xfail: str | None) -> str:
    ok = route_ok and reason_ok and not fails and not error
    if xfail:
        return "XPASS" if ok else "XFAIL"
    if error and not route_ok:
        return "ERROR"
    return "PASS" if ok else "FAIL"


# ── the cluster side ──────────────────────────────────────────────────────────────────────────────


@dataclass
class Turn:
    status: int = 0
    route: str | None = None
    reason: str | None = None
    llm_calls: int | None = None
    rows: list[dict] = field(default_factory=list)
    text: str = ""
    sql: str | None = None
    source: str | None = None
    turn_id: str | None = None
    secs: float = 0.0
    error: str | None = None
    resume_token: str | None = None
    options: list[dict] = field(default_factory=list)
    error_code: str | None = None


def find_all(obj: Any, pred) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []

    def walk(o, path):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, f"{path}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{path}[{i}]")
        elif pred(path, o):
            out.append((path, o))

    walk(obj, "")
    return out


def rows_of(envelopes: list[dict]) -> list[dict]:
    for e in envelopes:
        if (e.get("format") or {}).get("kind") in ("TABLE", "CHART") or e.get("contentJson", "").startswith("["):
            try:
                parsed = json.loads(e.get("contentJson") or "null")
            except ValueError:
                continue
            if isinstance(parsed, list):
                return [r for r in parsed if isinstance(r, dict)]
            if isinstance(parsed, dict) and isinstance(parsed.get("rows"), list):
                return parsed["rows"]
    return []


class Cluster:
    def __init__(self, args):
        import httpx

        self.args = args
        self.http = httpx.Client(timeout=args.timeout, follow_redirects=True)
        self.tokens: dict[str, tuple[str, float]] = {}
        self.password = os.environ.get("HARTLAND_DEMO_PASSWORD") or self._realm_password()
        self._pf = None

    def _realm_password(self) -> str | None:
        p = pathlib.Path(self.args.realm_file or "")
        if not self.args.realm_file or not p.is_file():
            return None
        realm = json.loads(p.read_text())
        for u in realm.get("users", []):
            for c in u.get("credentials", []):
                if c.get("type") == "password":
                    return c["value"]
        return None

    def token(self, user: str) -> str:
        tok, exp = self.tokens.get(user, ("", 0.0))
        if tok and time.time() < exp - 30:
            return tok
        if not self.password:
            raise SystemExit("no persona password: set HARTLAND_DEMO_PASSWORD or --realm-file")
        r = self.http.post(
            f"{self.args.issuer}/protocol/openid-connect/token",
            data={"grant_type": "password", "client_id": "iris", "username": user, "password": self.password, "scope": "openid"},
        )
        r.raise_for_status()
        b = r.json()
        self.tokens[user] = (b["access_token"], time.time() + int(b.get("expires_in", 300)))
        return b["access_token"]

    # ·· through iris-bff (the primary run) ··

    def session(self, user: str) -> str:
        r = self.http.post(f"{self.args.bff}/v1/session", json={}, headers=self._auth(user))
        r.raise_for_status()
        b = r.json()
        return b.get("sessionId") or b.get("id")

    def _auth(self, user: str) -> dict:
        return {"Authorization": f"Bearer {self.token(user)}"}

    def ask_bff(self, user: str, sid: str, question: str | None, locale: str, resume: dict | None, pending: Turn | None) -> Turn:
        t0 = time.time()
        turn = Turn()
        try:
            if resume:
                if not pending or not pending.resume_token:
                    turn.error = "resume: the previous turn left no clarification to answer"
                    return turn
                body: dict[str, Any] = {"sessionId": sid, "resumeToken": pending.resume_token}
                if "pick" in resume:
                    want = norm(resume["pick"].get(locale) if isinstance(resume["pick"], dict) else resume["pick"])
                    opt = next((o for o in pending.options if want in norm(json.dumps(o, ensure_ascii=False))), None)
                    if not opt:
                        turn.error = f"resume: no option matches {want!r} in {[o.get('label') for o in pending.options]}"
                        return turn
                    body["selectedOptionId"] = opt.get("id") or opt.get("optionId")
                else:
                    free = resume["free"]
                    body["freeTextAnswer"] = free.get(locale) if isinstance(free, dict) else free
                r = self.http.post(f"{self.args.bff}/v1/chat/resume", json=body, headers=self._auth(user))
                frames = [json.loads(ln[5:]) for ln in r.text.splitlines() if ln.startswith("data:") and ln[5:].strip().startswith("{")]
                env = next((f.get("envelope") for f in reversed(frames) if f.get("envelope")), None) or (frames[-1] if frames else {})
            else:
                r = self.http.post(
                    f"{self.args.bff}/v1/chat/turn",
                    json={"sessionId": sid, "question": question, "locale": locale},
                    headers=self._auth(user),
                )
                env = r.json().get("envelope", r.json()) if r.status_code == 200 else {}
            turn.status = r.status_code
            if r.status_code != 200:
                turn.error = f"HTTP {r.status_code}: {r.text[:300]}"
                return turn
            self._read_envelope(env, turn)
            if turn.turn_id:
                self._read_protocol(user, turn)
        except Exception as e:  # noqa: BLE001 — a case error is a result, never a crash of the run
            turn.error = f"{type(e).__name__}: {e}"[:400]
        finally:
            turn.secs = round(time.time() - t0, 1)
        return turn

    def _read_envelope(self, env: dict, turn: Turn) -> None:
        turn.turn_id = env.get("turnId")
        if env.get("contentJson"):
            try:
                parsed = json.loads(env["contentJson"])
                turn.rows = parsed if isinstance(parsed, list) else (parsed.get("rows") or [])
            except ValueError:
                pass
        expl = env.get("explanation") or {}
        turn.text = " ".join(filter(None, [expl.get("headline"), env.get("text")]))
        tokens = [v for p, v in find_all(env, lambda p, v: p.split(".")[-1] == "resumeToken" and v)]
        if tokens:
            turn.resume_token = tokens[0]
            opts: list[dict] = []

            def walk(o):
                if isinstance(o, dict):
                    for k, v in o.items():
                        if k == "options" and isinstance(v, list):
                            opts.extend(x for x in v if isinstance(x, dict))
                        else:
                            walk(v)
                elif isinstance(o, list):
                    for v in o:
                        walk(v)
            walk(env)
            turn.options = opts
        # The envelope's errorCode names an OUTCOME (PLANNER_REFUSED, PLANNER_CLARIFICATION, …), not a
        # transport failure: recorded, and judged by the route and the assertions like any answer.
        turn.error_code = env.get("errorCode")

    def _read_protocol(self, user: str, turn: Turn) -> None:
        r = self.http.get(f"{self.args.bff}/v1/protocols/{turn.turn_id}", headers=self._auth(user))
        if r.status_code != 200:
            return
        proto = r.json()
        secs: dict = {}
        for sec in (proto.get("document", {}).get("turns") or [{}])[0].get("sections", []):
            secs.update({k: v for k, v in sec.items() if k not in ("key", "appliedVerbosity")})
        tr = (secs.get("resolution") or {}).get("turnResolution") or {}
        turn.route = tr.get("route") or next(
            (v for _, v in find_all(proto, lambda p, v: isinstance(v, str) and v.startswith("ROUTE_"))), None
        )
        turn.reason = tr.get("fallThroughReason")
        turn.llm_calls = (secs.get("header") or {}).get("llmCallCount")
        sqls = [v for _, v in find_all(secs.get("sql") or {}, lambda p, v: isinstance(v, str) and v.lstrip().upper().startswith(("SELECT", "WITH")))]
        turn.sql = sqls[0] if sqls else None
        srcs = [v for _, v in find_all(secs.get("sql") or {}, lambda p, v: isinstance(v, str) and v.startswith("STATEMENT_SOURCE_"))]
        turn.source = ",".join(dict.fromkeys(srcs)) or None

    # ·· straight at golem (the shadow) ··

    def golem_url(self) -> str:
        if self.args.golem:
            return self.args.golem
        if self._pf is None:
            self._pf = subprocess.Popen(
                ["kubectl", "--context", self.args.ctx, "-n", "kantheon", "port-forward", "svc/golem-hartland", ":7420"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            )
            line = self._pf.stdout.readline()
            m = re.search(r"127\.0\.0\.1:(\d+)", line)
            if not m:
                raise SystemExit(f"golem port-forward failed: {line!r}")
            self._golem = f"http://127.0.0.1:{m.group(1)}"
        return self._golem

    def ask_golem_forced(self, user: str, question: str, locale: str) -> Turn:
        t0 = time.time()
        turn = Turn()
        try:
            r = self.http.post(
                f"{self.golem_url()}/v1/answer/sync",
                json={"id": str(uuid.uuid4()), "golemId": "golem-hartland", "question": question, "context": {"locale": locale}},
                headers={**self._auth(user), "X-Golem-Force-Route": "llm-compose"},
            )
            turn.status = r.status_code
            if r.status_code != 200:
                turn.error = f"HTTP {r.status_code}: {r.text[:300]}"
                return turn
            b = r.json()
            tr = b.get("turnResolution") or {}
            turn.route, turn.reason = tr.get("route"), tr.get("fallThroughReason")
            turn.llm_calls = sum((b.get("protocolHints") or {}).get("llmCallsByPurpose", {}).values())
            turn.rows = rows_of(b.get("envelopes") or [])
            turn.text = " ".join(e.get("text") or "" for e in b.get("envelopes") or [])
            turn.sql = (b.get("executedStatement") or {}).get("sql")
            turn.source = (b.get("executedStatement") or {}).get("composedVia")
            turn.turn_id = b.get("requestId")
        except Exception as e:  # noqa: BLE001
            turn.error = f"{type(e).__name__}: {e}"[:400]
        finally:
            turn.secs = round(time.time() - t0, 1)
        return turn

    def close(self):
        if self._pf:
            self._pf.terminate()

    # ·· the world DB (validation `core`) ··

    def core(self, sql: str, world: str) -> list[dict]:
        db, role = f"hartland_{world}", f"hartland_{world}_readonly"
        script = f"SET ROLE {role};\n{sql.rstrip().rstrip(';')};\n" if self.args.pg == "kubectl" else f"{sql.rstrip().rstrip(';')};\n"
        if self.args.pg == "kubectl":
            cmd = ["kubectl", "--context", self.args.ctx, "-n", "data", "exec", "-i", self.args.pg_pod, "-c", "postgres", "--",
                   "psql", "-q", "--csv", "-v", "ON_ERROR_STOP=1", "-d", db, "-f", "-"]
            env = None
        else:  # env: libpq PG* variables (the in-cluster job); PGDATABASE follows the world unless set
            cmd = ["psql", "-q", "--csv", "-v", "ON_ERROR_STOP=1", "-f", "-"]
            env = {**os.environ, "PGDATABASE": os.environ.get("PGDATABASE") or db}
        r = subprocess.run(cmd, input=script, capture_output=True, text=True, env=env, timeout=300)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip()[:400])
        return list(csv.DictReader(io.StringIO(r.stdout)))


# ── run ───────────────────────────────────────────────────────────────────────────────────────────


def run(args) -> int:
    root = pathlib.Path(args.cases)
    cases, personas, problems = load_corpus(root)
    if problems:
        print("✗ the corpus has schema problems — `check` lists them", file=sys.stderr)
        return 2
    world, locale = args.world, WORLD_LOCALE[args.world]
    only = set(filter(None, (args.only or "").split(",")))
    if only:
        sessions = {c.session for c in cases if c.id in only and c.session}
        cases = [c for c in cases if c.id in only or (c.session and c.session in sessions)]
    ref = dt.date.fromisoformat(args.reference_date) if args.reference_date else dt.datetime.now(dt.timezone.utc).date()
    cluster = Cluster(args)
    out_dir = pathlib.Path(args.out) if args.out else None
    results: list[dict] = []
    sessions_open: dict[str, tuple[str, str, Turn | None]] = {}
    started = dt.datetime.now(dt.timezone.utc)
    try:
        for c in cases:
            user = personas[c.raw.get("persona", "analyst")][world]
            q = c.question(locale)
            resume = c.raw.get("resume")
            if c.session and c.session in sessions_open and sessions_open[c.session][0] == user:
                _, sid, pending = sessions_open[c.session]
            else:
                sid, pending = cluster.session(user), None
            turn = cluster.ask_bff(user, sid, q, locale, resume, pending)
            if c.session:
                sessions_open[c.session] = (user, sid, turn)
            res = score(c, turn, world, locale, user, ref, cluster, root)
            if args.shadow and res["observed_route"] == "FAST" and q and not resume:
                forced = cluster.ask_golem_forced(user, q, locale)
                res["shadow"] = shadow_score(c, forced, res, ref, cluster, root, world, locale)
            results.append(res)
            mark = {"PASS": "✓", "XFAIL": "○", "XPASS": "!", "FAIL": "✗", "ERROR": "✗"}[res["status"]]
            print(
                f"{mark} {res['status']:<5} {c.id:<44} want {res['expected_route']:<6} got {res['observed_route']:<6} "
                f"{(res['observed_reason'] or '')[:28]:<28} llm={res['llm_calls']} {res['secs']:>5}s "
                + ("; ".join(res["fails"])[:160] if res["fails"] else "")
                + (f" | shadow {res['shadow']['verdict']}" if res.get("shadow") else ""),
                flush=True,
            )
    finally:
        cluster.close()
    doc = {
        "$schema": "ttr-demo/routing-result/v1",
        "world": world,
        "locale": locale,
        "started": started.isoformat(timespec="seconds"),
        "reference_date": ref.isoformat(),
        "shadow": bool(args.shadow),
        "bff": args.bff,
        "cases": results,
        "summary": summarize(results),
    }
    s = doc["summary"]
    disagree = [r["id"] for r in results if (r.get("shadow") or {}).get("verdict") in ("DOOR_WRONG", "LLM_WRONG", "BOTH_WRONG")]
    red = bool(s["status"].get("FAIL") or s["status"].get("ERROR")) or (args.strict_shadow and bool(disagree))
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"results-{world}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
        (out_dir / "report.md").write_text(render_report([doc]))
        (out_dir / "result.json").write_text(json.dumps(nightly_result(doc, red, started, args.owner), ensure_ascii=False, indent=1) + "\n")
        print(f"→ {out_dir}/results-{world}.json, report.md, result.json")
    print("── " + " · ".join(f"{k} {v}" for k, v in s["status"].items()) + f" · {len(results)} cases"
          + (f" · shadow disagrees on {', '.join(disagree)}" if disagree else ""))
    return 1 if red else 0


def nightly_result(doc: dict, red: bool, started: dt.datetime, owner: str) -> dict:
    """The olymp nightly's result.json (nightly/design/contracts.md N-C2): one tier, one subject."""
    status_of = {"PASS": "green", "XFAIL": "green", "XPASS": "green", "FAIL": "red", "ERROR": "red"}
    cases = []
    for r in doc["cases"]:
        st = status_of[r["status"]]
        detail = "; ".join(r["fails"])[:300] if st == "red" else (f"{r['status']}: {r['xfail']}" if r.get("xfail") else "")
        sh = r.get("shadow") or {}
        if sh.get("verdict") in ("DOOR_WRONG", "LLM_WRONG", "BOTH_WRONG"):
            st, detail = "red", f"shadow {sh['verdict']}: {sh.get('detail', '')}"[:300]
        cases.append({"id": f"{r['id']}-{doc['world']}", "status": st, "owner": owner, "detail": detail})
    return {
        "$schema": "olymp.collite/nightly-result/v1",
        "date": started.date().isoformat(),
        "run_url": os.environ.get("NIGHTLY_RUN_URL", ""),
        "tier": "agent",
        "subject": f"golem-hartland-routing-{doc['world']}",
        "status": "red" if red else "green",
        "score": None,
        "duration_s": int((dt.datetime.now(dt.timezone.utc) - started).total_seconds()),
        "cases": cases,
        "env": {"world": doc["world"], "reference_date": doc["reference_date"], "shadow": doc["shadow"]},
    }


def score(c: Case, turn: Turn, world: str, locale: str, user: str, ref: dt.date, cluster: Cluster, root: pathlib.Path) -> dict:
    expected = c.raw["expected_route"]
    observed = classify(turn.route)
    if observed == "NONE" and turn.resume_token:
        observed = "ASK"
    route_ok = observed == expected
    want_reason = c.raw.get("expected_reason") or ""
    reason_ok = not want_reason or (turn.reason or "").startswith(want_reason)
    fails: list[str] = []
    core_rows = None
    v = c.raw.get("validation")
    if v and not turn.error:
        doc = load_yaml(root / "validation" / v)
        if doc.get("core"):
            try:
                core_rows = cluster.core(substitute(doc["core"], ref, (doc.get("params") or {}).get(world)), world)
            except Exception as e:  # noqa: BLE001
                fails.append(f"core SQL failed: {e}"[:300])
        fails += evaluate(doc["assert"], turn.rows, turn.text, core_rows, locale)
    if not route_ok:
        fails.insert(0, f"route {observed} ≠ {expected}")
    if not reason_ok:
        fails.insert(0, f"reason {turn.reason!r} ≠ {want_reason}…")
    if turn.error:
        fails.insert(0, turn.error)
    return {
        "id": c.id,
        "act": c.raw.get("act"),
        "shape": c.raw.get("shape"),
        "persona": user,
        "question": c.question(locale) or f"(resume: {json.dumps(c.raw.get('resume'), ensure_ascii=False)})",
        "expected_route": expected,
        "expected_reason": want_reason or None,
        "observed_route": observed,
        "observed_reason": turn.reason,
        "llm_calls": turn.llm_calls,
        "secs": turn.secs,
        "rows": len(turn.rows),
        "statement_source": turn.source,
        "error_code": turn.error_code,
        "sql": (turn.sql or "")[:2000] or None,
        "turn_id": turn.turn_id,
        "xfail": c.xfail(locale),
        "fails": fails,
        "status": verdict(route_ok, reason_ok, [f for f in fails if not f.startswith(("route ", "reason "))], turn.error, c.xfail(locale)),
    }


def shadow_score(c: Case, forced: Turn, primary: dict, ref, cluster, root, world, locale) -> dict:
    honoured = (forced.reason or "").startswith("EVAL_FORCED")
    out = {"route": classify(forced.route), "reason": forced.reason, "llm_calls": forced.llm_calls, "secs": forced.secs,
           "rows": len(forced.rows), "sql": (forced.sql or "")[:2000] or None, "turn_id": forced.turn_id}
    if forced.error:
        return {**out, "verdict": "ERROR", "detail": forced.error}
    if not honoured:
        return {**out, "verdict": "NOT_HONOURED", "detail": "golem did not force the LLM lane (GOLEM_EVAL_FORCE_ROUTE off, or a golem older than kantheon#181)"}
    v = c.raw.get("validation")
    if not v:
        return {**out, "verdict": "UNSCORED", "detail": "no validation: the case asserts the route only"}
    doc = load_yaml(root / "validation" / v)
    try:
        core_rows = cluster.core(substitute(doc["core"], ref, (doc.get("params") or {}).get(world)), world) if doc.get("core") else None
    except Exception as e:  # noqa: BLE001
        return {**out, "verdict": "ERROR", "detail": f"core SQL failed: {e}"[:300]}
    fails = evaluate(doc["assert"], forced.rows, forced.text, core_rows, locale)
    door_ok = not [f for f in primary["fails"] if not f.startswith(("route ", "reason "))]
    llm_ok = not fails
    verdict_ = "AGREE" if door_ok and llm_ok else ("LLM_WRONG" if door_ok else ("DOOR_WRONG" if llm_ok else "BOTH_WRONG"))
    return {**out, "verdict": verdict_, "detail": "; ".join(fails)[:400]}


def summarize(results: list[dict]) -> dict:
    status: dict[str, int] = {}
    for r in results:
        status[r["status"]] = status.get(r["status"], 0) + 1
    shapes: dict[str, dict[str, int]] = {}
    for r in results:
        s = r.get("shadow")
        if s:
            row = shapes.setdefault(r["shape"], {})
            row[s["verdict"]] = row.get(s["verdict"], 0) + 1
    fast = [r for r in results if r["expected_route"] == "FAST"]
    return {
        "status": dict(sorted(status.items())),
        "fast_scripted": len(fast),
        "fast_fell_through": [r["id"] for r in fast if r["observed_route"] != "FAST"],
        "unhonoured_on_fast": [r["id"] for r in fast if (r["observed_reason"] or "").startswith("UNHONOURED_")],
        "shadow_by_shape": shapes,
    }


# ── report ────────────────────────────────────────────────────────────────────────────────────────


def render_report(docs: list[dict]) -> str:
    by_world = {d["world"]: d for d in docs}
    worlds = [w for w in ("cz", "us") if w in by_world]
    ids: list[str] = []
    meta: dict[str, dict] = {}
    for d in docs:
        for r in d["cases"]:
            if r["id"] not in meta:
                ids.append(r["id"])
                meta[r["id"]] = r
    lines = ["# Routing corpus — report", ""]
    for w in worlds:
        d = by_world[w]
        s = d["summary"]
        lines.append(
            f"- **{w} / {d['locale']}** — run {d['started']} (reference date {d['reference_date']}, shadow {'on' if d['shadow'] else 'off'}): "
            + " · ".join(f"{k} {v}" for k, v in s["status"].items())
            + f" · scripted FAST {s['fast_scripted']}, fell through {len(s['fast_fell_through'])}"
            + (f" ({', '.join(s['fast_fell_through'])})" if s["fast_fell_through"] else "")
        )
    lines += ["", "| case | shape | want | " + " | ".join(f"{w}/{WORLD_LOCALE[w]}: route · reason · llm · s · verdict" for w in worlds) + " |",
              "|---|---|---|" + "---|" * len(worlds)]
    for cid in ids:
        m = meta[cid]
        cells = []
        for w in worlds:
            r = next((x for x in by_world[w]["cases"] if x["id"] == cid), None)
            if not r:
                cells.append("—")
                continue
            reason = (r["observed_reason"] or "").replace("|", "/")[:30]
            v = r["status"] + (f" ({r['xfail']})" if r.get("xfail") and r["status"] in ("XFAIL", "XPASS") else "")
            sh = f" · shadow {r['shadow']['verdict']}" if r.get("shadow") else ""
            cells.append(f"{r['observed_route']} · {reason or '—'} · {r['llm_calls'] if r['llm_calls'] is not None else '—'} · {r['secs']} · **{v}**{sh}")
        want = m["expected_route"] + (f" ({m['expected_reason']})" if m.get("expected_reason") else "")
        lines.append(f"| `{cid}` | {m['shape']} | {want} | " + " | ".join(cells) + " |")
    shadow = [d for d in docs if d["shadow"]]
    if shadow:
        lines += ["", "## Shadow parity per shape (FAST answers re-asked on the LLM lane)", "",
                  "| world | shape | AGREE | DOOR_WRONG | LLM_WRONG | BOTH_WRONG | other |", "|---|---|---|---|---|---|---|"]
        for d in shadow:
            for shape, counts in sorted(d["summary"]["shadow_by_shape"].items()):
                other = sum(v for k, v in counts.items() if k not in ("AGREE", "DOOR_WRONG", "LLM_WRONG", "BOTH_WRONG"))
                lines.append(f"| {d['world']} | {shape} | {counts.get('AGREE', 0)} | {counts.get('DOOR_WRONG', 0)} | "
                             f"{counts.get('LLM_WRONG', 0)} | {counts.get('BOTH_WRONG', 0)} | {other} |")
    bad = [(d["world"], r) for d in docs for r in d["cases"] if r["status"] in ("FAIL", "ERROR", "XPASS")]
    if bad:
        lines += ["", "## Findings", ""]
        for w, r in bad:
            lines.append(f"- **{w} `{r['id']}`** {r['status']} — „{r['question']}“: " + "; ".join(r["fails"])[:500])
    return "\n".join(lines) + "\n"


def report(args) -> int:
    docs = [json.loads(pathlib.Path(p).read_text()) for p in args.results]
    sys.stdout.write(render_report(docs))
    return 0


def check(args) -> int:
    cases, personas, problems = load_corpus(pathlib.Path(args.cases))
    for p in problems:
        print(f"✗ {p}")
    by_route: dict[str, int] = {}
    for c in cases:
        by_route[c.raw.get("expected_route")] = by_route.get(c.raw.get("expected_route"), 0) + 1
    print(f"{'✗' if problems else '✓'} {len(cases)} cases ({', '.join(f'{k} {v}' for k, v in sorted(by_route.items(), key=str))}), "
          f"{len({c.raw.get('validation') for c in cases if c.raw.get('validation')})} validations, {len(problems)} problems")
    bad_core = 0
    for world in args.core:
        # --core <world>: run every validation's `core` against that world DB — the SQL half of the
        # corpus, checked without asking a single question.
        cluster = Cluster(args)
        ref = dt.date.fromisoformat(args.reference_date) if args.reference_date else dt.datetime.now(dt.timezone.utc).date()
        for vp in sorted((pathlib.Path(args.cases) / "validation").glob("*.yaml")):
            doc = load_yaml(vp) or {}
            if not doc.get("core"):
                continue
            try:
                rows = cluster.core(substitute(doc["core"], ref, (doc.get("params") or {}).get(world)), world)
                first = ", ".join(f"{k}={v}" for k, v in (rows[0].items() if rows else []))[:110]
                print(f"  ✓ {world} {vp.stem:<40} {len(rows):>3} rows  {first}")
            except Exception as e:  # noqa: BLE001
                bad_core += 1
                print(f"  ✗ {world} {vp.stem:<40} {e}"[:300])
    return 1 if problems or bad_core else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="LR P6 routing corpus runner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--cases", default=str(DEFAULT_CORPUS))
    c.add_argument("--core", action="append", default=[], choices=sorted(WORLD_LOCALE), help="also run every core SQL on this world")
    c.add_argument("--ctx", default="hartland")
    c.add_argument("--pg", default=os.environ.get("ROUTING_PG", "kubectl"), choices=["kubectl", "env"])
    c.add_argument("--pg-pod", default="hartland-pg-1")
    c.add_argument("--reference-date", default=os.environ.get("ROUTING_REFERENCE_DATE", ""))
    c.add_argument("--realm-file", default="")
    c.add_argument("--timeout", type=float, default=60.0)
    c.add_argument("--issuer", default="")
    r = sub.add_parser("run")
    r.add_argument("--world", required=True, choices=sorted(WORLD_LOCALE))
    r.add_argument("--cases", default=str(DEFAULT_CORPUS))
    r.add_argument("--only", default="")
    r.add_argument("--shadow", action="store_true")
    r.add_argument("--out", default="")
    r.add_argument("--ctx", default="hartland")
    r.add_argument("--bff", default=os.environ.get("ROUTING_BFF", "https://iris.hartland.collite.cz/bff"))
    r.add_argument("--issuer", default=os.environ.get("ROUTING_ISSUER", "https://keycloak.hartland.collite.cz/realms/kantheon"))
    r.add_argument("--golem", default=os.environ.get("ROUTING_GOLEM", ""), help="golem-hartland base URL; default: a port-forward on --ctx")
    r.add_argument("--pg", default=os.environ.get("ROUTING_PG", "kubectl"), choices=["kubectl", "env"])
    r.add_argument("--pg-pod", default="hartland-pg-1")
    r.add_argument("--realm-file", default=str(HERE.parent.parent / "olymp/platform/auth/keycloak/overlays/hartland/realm/kantheon.json"))
    r.add_argument("--reference-date", default=os.environ.get("ROUTING_REFERENCE_DATE", ""))
    r.add_argument("--timeout", type=float, default=240.0)
    r.add_argument("--strict-shadow", action="store_true", help="exit 1 when a shadow answer disagrees (the nightly)")
    r.add_argument("--owner", default=os.environ.get("ROUTING_OWNER", "@boraperusic"), help="N-C2 case owner")
    p = sub.add_parser("report")
    p.add_argument("results", nargs="+")
    args = ap.parse_args(argv)
    return {"check": check, "run": run, "report": report}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
