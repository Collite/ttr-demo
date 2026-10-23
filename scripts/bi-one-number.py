#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27", "pyyaml>=6", "ttr-sqlalchemy==0.11.0"]
# ///
"""BI-4 · S4.1 T5 — one number, read on every path (contracts C-25). Cases: run-set/bi-one-number/ (README there).

    uv run scripts/bi-one-number.py check                     # the cases' schema; no cluster
    uv run scripts/bi-one-number.py run --world cz [--only id] [--out DIR]

`run` reads each case's number on every leg: through the Flight edge as the persona (the read a Superset dataset
makes), through the public iris-bff as the persona (the routing runner's client: sessions, the turn's protocol),
and later on the Superset tile. The oracle is a routing validation's `core` on the world DB, as the read-only role.
Every leg and the oracle must give the case's `expect`.

Exit code: 0 = every leg that ran gave `expect` (a `pending` leg does not redden); 1 otherwise; 2 = schema problems.
"""

from __future__ import annotations

import argparse
import datetime as dt
import decimal
import importlib.util
import json
import os
import pathlib
import sys
import time
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_CASES = HERE.parent / "run-set" / "bi-one-number"
ROUTING = HERE.parent / "run-set" / "routing"
CASE_KEYS = {"id", "title", "expect", "dc", "oracle", "legs"}
LEG_KEYS = {"id", "via", "persona", "sql", "question", "pattern", "value", "dcs", "pending"}
VIAS = {"edge", "iris", "superset"}

# The routing runner's client and helpers (iris-bff turns, protocols, the world DB) — one copy of that code.
_spec = importlib.util.spec_from_file_location("routing_run", HERE / "routing-run.py")
rr = importlib.util.module_from_spec(_spec)
sys.modules["routing_run"] = rr  # dataclasses resolve annotations through sys.modules
_spec.loader.exec_module(rr)


# ── the cases ─────────────────────────────────────────────────────────────────────────────────────


def load_cases(root: pathlib.Path) -> tuple[list[dict], list[str]]:
    personas = rr.load_yaml(ROUTING / "personas.yaml") or {}
    cases, problems = [], []
    for path in sorted(root.glob("*.yaml")):
        c = rr.load_yaml(path) or {}
        where = path.name
        problems += [f"{where}: unknown key {k!r}" for k in sorted(set(c) - CASE_KEYS)]
        if c.get("id") != path.stem:
            problems.append(f"{where}: id {c.get('id')!r} ≠ the filename stem")
        if rr.as_number(c.get("expect")) is None:
            problems.append(f"{where}: expect must be a number")
        if rr.as_number(c.get("dc")) is None:
            problems.append(f"{where}: dc must be the DC key")
        oracle = root / str(c.get("oracle") or "")
        if not c.get("oracle") or not oracle.is_file():
            problems.append(f"{where}: oracle {c.get('oracle')!r} is not a file")
        else:
            v = rr.load_yaml(oracle) or {}
            if not v.get("core") or not ((v.get("assert") or {}).get("scalar") or {}).get("value"):
                problems.append(f"{where}: oracle {c['oracle']} needs a `core` and an `assert.scalar.value`")
        legs = c.get("legs") or []
        if not legs:
            problems.append(f"{where}: no legs")
        ids = [leg.get("id") for leg in legs]
        problems += [f"{where}: leg id {i!r} twice" for i in sorted({i for i in ids if ids.count(i) > 1}, key=str)]
        for leg in legs:
            problems += [f"{where}: {p}" for p in leg_problems(leg, personas)]
        cases.append(c)
    if not cases:
        problems.append(f"{root}: no cases")
    return cases, problems


def leg_problems(leg: dict, personas: dict) -> list[str]:
    lid = leg.get("id") or "?"
    out = [f"leg {lid}: unknown key {k!r}" for k in sorted(set(leg) - LEG_KEYS)]
    if not leg.get("id"):
        out.append("a leg has no id")
    if leg.get("via") not in VIAS:
        out.append(f"leg {lid}: via {leg.get('via')!r} is not one of {sorted(VIAS)}")
    if "pending" in leg:
        if not isinstance(leg["pending"], str) or not leg["pending"].strip():
            out.append(f"leg {lid}: pending must say what it waits for")
        return out
    if leg.get("via") == "superset":
        out.append(f"leg {lid}: a superset leg is S4.2 T5's — declare it pending until then")
    if leg.get("persona") not in personas:
        out.append(f"leg {lid}: persona {leg.get('persona')!r} is not in routing/personas.yaml")
    if not isinstance(leg.get("value"), str) or not leg["value"]:
        out.append(f"leg {lid}: value must name the number's column")
    if leg.get("via") == "edge":
        if not leg.get("sql"):
            out.append(f"leg {lid}: an edge leg needs its sql")
        dcs = leg.get("dcs")
        if not (isinstance(dcs, int) and not isinstance(dcs, bool)) and not (isinstance(dcs, list) and dcs):
            out.append(f"leg {lid}: dcs must be a count or a list of DC keys")
    if leg.get("via") == "iris":
        q = leg.get("question")
        if not isinstance(q, dict) or set(q) != set(rr.WORLD_LOCALE.values()) or not all(q.values()):
            out.append(f"leg {lid}: question needs both languages ({', '.join(sorted(rr.WORLD_LOCALE.values()))})")
    return out


# ── reading the number ────────────────────────────────────────────────────────────────────────────


def number(v: Any) -> float | None:
    return float(v) if isinstance(v, decimal.Decimal) else rr.as_number(v)


def value_column(rows: list[dict], part: str) -> tuple[str | None, str | None]:
    """The number's column: the one named `part`, else the one column whose name contains it (case-insensitive)."""
    cols = list(dict.fromkeys(k for r in rows for k in r))
    want = part.casefold()
    exact = [c for c in cols if c.casefold() == want]
    if exact:
        return exact[0], None
    like = [c for c in cols if want in c.casefold()]
    if len(like) == 1:
        return like[0], None
    return None, (f"no column named like {part!r} in {cols}" if not like else f"{part!r} names {len(like)} columns: {like}")


def summed(rows: list[dict], part: str) -> tuple[float | None, str | None]:
    if not rows:
        return None, "no rows"
    col, err = value_column(rows, part)
    if err:
        return None, err
    cells = [number(r.get(col)) for r in rows]
    if any(c is None for c in cells):
        return None, f"{col} is not a number in every row: {[r.get(col) for r in rows][:6]}"
    return sum(cells), None


def per_dc(rows: list[dict], part: str, dc: Any, dcs: int | list) -> tuple[float | None, list[int], str | None]:
    """An edge leg's rows, one per DC: the `dc` row's number, the DCs seen, and whether they are the persona's."""
    if not rows:
        return None, [], "no rows"
    col, err = value_column(rows, part)
    if err:
        return None, [], err
    key = next((c for c in rows[0] if c != col), None)
    if key is None:
        return None, [], "no DC column beside the number"
    seen = sorted(int(number(r[key])) for r in rows if number(r.get(key)) is not None)
    want = int(number(dc))
    if isinstance(dcs, list):
        if seen != sorted(int(d) for d in dcs):
            return None, seen, f"sees DCs {seen}, should see {sorted(dcs)}"
    elif len(seen) != dcs:
        return None, seen, f"sees {len(seen)} DCs {seen}, should see {dcs}"
    row = next((r for r in rows if number(r.get(key)) == want), None)
    if row is None:
        return None, seen, f"DC {want} is not in the rows"
    got = number(row.get(col))
    return got, seen, None if got is not None else f"{col} of DC {want} is not a number: {row.get(col)!r}"


def judge(got: float | None, err: str | None, expect: float) -> tuple[bool, str | None]:
    if err:
        return False, err
    if got != expect:
        return False, f"{fmt(got)} ≠ {fmt(expect)}"
    return True, None


def fmt(v: float | None) -> str:
    return "—" if v is None else (str(int(v)) if float(v).is_integer() else f"{v:g}")


# ── run ───────────────────────────────────────────────────────────────────────────────────────────


def edge_rows(args, world: str, user: str, password: str, sql: str) -> list[dict]:
    from ttr_sqlalchemy.dbapi import connect

    host, _, port = args.edge.rpartition(":")
    conn = connect(host=host, port=int(port), world=f"hartland_{world}", user=user, password=password)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()


def run_leg(leg: dict, case: dict, world: str, personas: dict, cluster, args) -> dict:
    res: dict[str, Any] = {"id": leg["id"], "via": leg["via"]}
    if "pending" in leg:
        return {**res, "status": "PENDING", "detail": leg["pending"]}
    user = personas[leg["persona"]][world]
    locale = rr.WORLD_LOCALE[world]
    expect = number(case["expect"])
    t0 = time.time()
    got, err = None, None
    try:
        if leg["via"] == "edge":
            rows = edge_rows(args, world, user, cluster.password, leg["sql"])
            got, seen, err = per_dc(rows, leg["value"], case["dc"], leg["dcs"])
            res["dcs"] = seen
        else:  # iris
            sid = cluster.session(user)
            turn = cluster.ask_bff(user, sid, leg["question"][locale], locale, None, None)
            res.update(route=rr.classify(turn.route), pattern=turn.pattern, rows=len(turn.rows), turn_id=turn.turn_id)
            if turn.error:
                err = turn.error
            elif leg.get("pattern") and turn.pattern != leg["pattern"]:
                err = f"answered by {turn.pattern or 'a composed query'}, not the saved query {leg['pattern']}"
            else:
                got, err = summed(turn.rows, leg["value"])
    except Exception as e:  # noqa: BLE001 — a leg's failure is a result, never a crash of the run
        err = f"{type(e).__name__}: {e}"[:400]
    ok, detail = judge(got, err, expect)
    return {**res, "persona": user, "number": got, "status": "PASS" if ok else "FAIL", "detail": detail,
            "secs": round(time.time() - t0, 1)}


def run(args) -> int:
    root = pathlib.Path(args.cases)
    cases, problems = load_cases(root)
    if problems:
        print("✗ the cases have schema problems — `check` lists them", file=sys.stderr)
        return 2
    only = set(filter(None, (args.only or "").split(",")))
    cases = [c for c in cases if not only or c["id"] in only]
    world = args.world
    personas = rr.load_yaml(ROUTING / "personas.yaml")
    ref = dt.date.fromisoformat(args.reference_date) if args.reference_date else dt.datetime.now(dt.timezone.utc).date()
    cluster = rr.Cluster(args)
    started = dt.datetime.now(dt.timezone.utc)
    docs, red = [], False
    try:
        for c in cases:
            expect = number(c["expect"])
            print(f"── {c['id']} ({world}): every leg must give {fmt(expect)}")
            v = rr.load_yaml(root / c["oracle"])
            try:
                rows = cluster.core(rr.substitute(v["core"], ref, (v.get("params") or {}).get(world)), world)
                o_got, o_err = summed(rows, v["assert"]["scalar"]["value"])
            except Exception as e:  # noqa: BLE001
                o_got, o_err = None, f"core SQL failed: {e}"[:400]
            o_ok, o_detail = judge(o_got, o_err, expect)
            oracle = {"status": "PASS" if o_ok else "FAIL", "number": o_got, "detail": o_detail}
            print(f"{'✓' if o_ok else '✗'} {'oracle':<16} {'db':<8} {f'hartland_{world}_readonly':<26} {fmt(o_got):>6}"
                  + (f"  {o_detail}" if o_detail else ""))
            legs = []
            for leg in c["legs"]:
                r = run_leg(leg, c, world, personas, cluster, args)
                legs.append(r)
                mark = {"PASS": "✓", "FAIL": "✗", "PENDING": "○"}[r["status"]]
                if r["status"] == "PENDING":
                    print(f"{mark} {r['id']:<16} {r['via']:<8} pending: {r['detail']}")
                    continue
                extra = (f"DCs {r['dcs']}" if r["via"] == "edge" else f"{r.get('route')} {r.get('pattern') or ''}".strip())
                print(f"{mark} {r['id']:<16} {r['via']:<8} {r['persona']:<26} {fmt(r['number']):>6}  {extra}  {r['secs']}s"
                      + (f"  {r['detail']}" if r["detail"] else ""), flush=True)
            failed = [r["id"] for r in legs if r["status"] == "FAIL"] + ([] if o_ok else ["oracle"])
            red = red or bool(failed)
            pending = sum(r["status"] == "PENDING" for r in legs)
            ran = len(legs) - pending
            print(f"── {fmt(expect)}: " + (f"FAIL on {', '.join(failed)}" if failed else f"the oracle and {ran} legs agree")
                  + (f" · {pending} pending" if pending else ""))
            docs.append({"id": c["id"], "expect": expect, "oracle": oracle, "legs": legs, "status": "red" if failed else "green"})
    finally:
        cluster.close()
    if args.out:
        out = pathlib.Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        doc = {"$schema": "ttr-demo/bi-one-number/v1", "world": world, "started": started.isoformat(timespec="seconds"),
               "edge": args.edge, "bff": args.bff, "cases": docs}
        (out / f"one-number-{world}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
        print(f"→ {out}/one-number-{world}.json")
    return 1 if red else 0


def check(args) -> int:
    cases, problems = load_cases(pathlib.Path(args.cases))
    for p in problems:
        print(f"  ✗ {p}")
    legs = sum(len(c.get("legs") or []) for c in cases)
    print(f"{'✗' if problems else '✓'} {len(cases)} cases, {legs} legs" + (f", {len(problems)} problems" if problems else ""))
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="BI-4 one-number check")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--cases", default=str(DEFAULT_CASES))
    r = sub.add_parser("run")
    r.add_argument("--world", required=True, choices=sorted(rr.WORLD_LOCALE))
    r.add_argument("--cases", default=str(DEFAULT_CASES))
    r.add_argument("--only", default="")
    r.add_argument("--out", default="")
    r.add_argument("--ctx", default="hartland")
    r.add_argument("--edge", default=os.environ.get("BI_EDGE", "flight.hartland.collite.cz:443"), help="the Flight edge, host:port")
    r.add_argument("--bff", default=os.environ.get("ROUTING_BFF", "https://iris.hartland.collite.cz/bff"))
    r.add_argument("--issuer", default=os.environ.get("ROUTING_ISSUER", "https://keycloak.hartland.collite.cz/realms/kantheon"))
    r.add_argument("--pg", default=os.environ.get("ROUTING_PG", "kubectl"), choices=["kubectl", "env"])
    r.add_argument("--pg-pod", default="hartland-pg-1")
    r.add_argument("--realm-file", default=str(HERE.parent.parent / "olymp/platform/auth/keycloak/overlays/hartland/realm/kantheon.json"))
    r.add_argument("--reference-date", default=os.environ.get("ROUTING_REFERENCE_DATE", ""))
    r.add_argument("--timeout", type=float, default=240.0)
    args = ap.parse_args(argv)
    args.golem = ""  # the routing client's shadow lane; not used here
    return {"check": check, "run": run}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
