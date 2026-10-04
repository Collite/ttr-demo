#!/usr/bin/env python3
"""IA-P4·S4.3·T6 — the five overview workbooks held to their references on the book (IA-C51).

    overview_fingerprint.py compare <template> <workbook.xlsx> <reference.csv> [--portfolio P] [--client C]
                                    [--months N] [--tolerance 0.01] [--decimal-tolerance 0.000001]

`<template>` is one of `portfolio-statement:v1`, `client-overview:v1`, `distributor-overview:v1`, `price-sheet:v1`,
`sync-run-changes:v1`. The workbook is read as a person's Excel reads it — each table by the headers it PRINTS (the
renderer's `OverviewTemplateAuthors`), a date as the serial it is — and every figure the reference computes is compared:
money ± `--tolerance` (IA-C51: 0.01), units and prices ± `--decimal-tolerance`, percents ± 0.0001 pp, counts and text
exactly. Exit 0 when they agree; 1 with every difference named; 2 when the inputs cannot be compared (a refusal, a
missing table). The statement's Evolution sheet is `evolution_fingerprint.py`'s (it is v2's Periods).

Pure standard library, like `fingerprint.py`, whose OOXML reading it reuses.
"""

from __future__ import annotations

import argparse
import csv
import sys
import zipfile
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fingerprint import EXCEL_EPOCH, NS, _cells, _sheet_path, _shared_strings  # noqa: E402

TEMPLATES = ("portfolio-statement:v1", "client-overview:v1", "distributor-overview:v1", "price-sheet:v1", "sync-run-changes:v1")
PCT_TOLERANCE = Decimal("0.0001")


def dec(value: str | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def iso(serial: str) -> str:
    """A date cell is a serial in the file; its display format is a style, not a value."""
    return (EXCEL_EPOCH + timedelta(days=int(Decimal(serial)))).isoformat() if dec(serial) is not None else serial


def _letters(n: int) -> str:
    out = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


class Workbook:
    def __init__(self, path: str):
        with zipfile.ZipFile(path) as zf:
            strings = _shared_strings(zf)
            book = ElementTree.fromstring(zf.read("xl/workbook.xml"))
            names = [s.attrib["name"] for s in book.find("m:sheets", NS).findall("m:sheet", NS)]
            self._sheets = {name: _cells(zf, _sheet_path(zf, name), strings) for name in names}

    def table(self, sheet: str, first: str) -> list[dict[str, str]]:
        """The table whose header row starts with [first] in column A: its headers across, its rows until column A is
        empty. Each row as {printed header: cell text}."""
        rows = self._sheets.get(sheet)
        if rows is None:
            raise Refused(f"the workbook has no sheet {sheet!r}")
        at = next((i for i, r in enumerate(rows) if r.get("A") == first), None)
        if at is None:
            raise Refused(f"the {sheet} sheet has no table headed {first!r}")
        headers = []
        for i in range(0, 200):
            h = rows[at].get(_letters(i), "")
            if h == "":
                break
            headers.append(h)
        out = []
        for r in rows[at + 1:]:
            if r.get("A", "") == "":
                break
            out.append({h: r.get(_letters(i), "") for i, h in enumerate(headers)})
        return out

    def facts(self, sheet: str, first: str = "Item") -> dict[str, str]:
        """An Item · Value table (or Item · Count · …) as {item: the row}."""
        return {r[first]: r for r in self.table(sheet, first)}


class Refused(Exception):
    pass


def read_reference(path: str) -> list[dict[str, str]]:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    refused = next((r.get("refused", "") for r in rows if r.get("refused")), "")
    if refused:
        raise Refused(f"the book cannot be compared: {refused}")
    return rows


class Diff:
    def __init__(self, money: Decimal, decimal: Decimal):
        self.money, self.decimal, self.lines = money, decimal, []

    def num(self, where: str, got: str | None, want: str | None, kind: str = "money") -> None:
        g, w = dec(got), dec(want)
        if g is None and w is None:
            return
        if g is None or w is None:
            self.lines.append(f"{where}: workbook {got or '∅'} · book {want or '∅'}")
            return
        tol = {"money": self.money, "decimal": self.decimal, "pct": PCT_TOLERANCE, "count": Decimal(0)}[kind]
        if abs(g - w) > tol:
            if kind == "count":
                # a count is a whole number; the cell keeps Excel's float spelling of it (`2.0`)
                g, w = g.to_integral_value(), w.to_integral_value()
            self.lines.append(f"{where}: workbook {g} · book {w} (Δ {g - w})")

    def text(self, where: str, got: str | None, want: str | None) -> None:
        if (got or "") != (want or ""):
            self.lines.append(f"{where}: workbook {got!r} · book {want!r}")

    def keys(self, what: str, got: set[str], want: set[str]) -> None:
        for k in sorted(want - got):
            self.lines.append(f"{what} {k}: on the book, not in the workbook")
        for k in sorted(got - want):
            self.lines.append(f"{what} {k}: in the workbook, not on the book")


# ── the five ─────────────────────────────────────────────────────────────────────────────────────────────────────


def statement(wb: Workbook, ref: list[dict[str, str]], d: Diff) -> str:
    tx = {r["Transaction"]: r for r in wb.table("Transactions", "Trade date")}
    want = {r["transaction_id"]: r for r in ref if r["kind"] == "transaction"}
    d.keys("transaction", set(tx), set(want))
    for k in sorted(set(tx) & set(want)):
        g, w = tx[k], want[k]
        d.text(f"{k} trade date", iso(g["Trade date"]), w["trade_date"])
        d.text(f"{k} leg", g["Leg"], w["leg"])
        d.text(f"{k} operation", g["Operation"], w["operation"])
        d.text(f"{k} ISIN", g["ISIN"], w["asset_id"])
        d.num(f"{k} quantity", g["Quantity"], w["quantity"], "decimal")
        d.num(f"{k} amount", g["Amount"], w["amount"])
        d.text(f"{k} currency", g["Currency"], w["currency"])
    cash = {r["Currency"]: r for r in wb.table("Cash", "Currency")}
    cash_want = {r["currency"]: r for r in ref if r["kind"] == "cash"}
    d.keys("cash in", set(cash), set(cash_want))
    for c in sorted(set(cash) & set(cash_want)):
        d.num(f"cash {c}", cash[c]["Balance"], cash_want[c]["balance"])
    return f"{len(tx)} transactions, cash in {len(cash)} {'currency' if len(cash) == 1 else 'currencies'}"


OVERVIEW_COLUMNS = [
    ("Market value", "market_value_rc", "money"),
    ("Cash", "cash_rc", "money"),
    ("Value", "value_rc", "money"),
    ("Value, previous quarter end", "value_prev_quarter_end", "money"),
    ("Change q/q %", "chg_qoq_pct", "pct"),
]


def client_overview(wb: Workbook, ref: list[dict[str, str]], d: Diff) -> str:
    got = {r["Portfolio"]: r for r in wb.table("Portfolios", "Portfolio")}
    want = {r["portfolio_id"]: r for r in ref}
    d.keys("portfolio", set(got), set(want))
    for p in sorted(set(got) & set(want)):
        for header, key, kind in OVERVIEW_COLUMNS:
            d.num(f"{p} {key}", got[p][header], want[p][key], kind)
    return f"{len(got)} portfolios"


def distributor_overview(wb: Workbook, ref: list[dict[str, str]], d: Diff) -> str:
    got = {r["Portfolio"]: r for r in wb.table("Portfolios", "Client id")}
    want = {r["portfolio_id"]: r for r in ref}
    d.keys("portfolio", set(got), set(want))
    for p in sorted(set(got) & set(want)):
        d.text(f"{p} client", got[p]["Client id"], want[p]["client_id"])
        for header, key, kind in OVERVIEW_COLUMNS:
            if header in ("Market value", "Cash"):
                continue  # the book's Portfolios sheet prints the value and its quarter-on-quarter change
            d.num(f"{p} {key}", got[p][header], want[p][key], kind)
    book = wb.facts("Book")
    d.num("Book: clients", book.get("Clients", {}).get("Count"), str(len({r["client_id"] for r in ref})), "count")
    d.num("Book: open portfolios", book.get("Open portfolios", {}).get("Count"), str(len(ref)), "count")
    return f"{len(got)} portfolios of {len({r['client_id'] for r in ref})} clients"


def price_sheet(wb: Workbook, ref: list[dict[str, str]], d: Diff, months: int | None) -> str:
    rows = wb.table("Prices", "ISIN")
    want: dict[tuple[str, str], str] = {(r["asset_id"], r["day"]): r["price"] for r in ref}
    days = sorted({r["day"] for r in ref})
    got_days = [h for h in (rows[0].keys() if rows else []) if len(h) == 10 and h[4] == "-"]
    if months is not None and len(got_days) != min(months, 24):
        d.lines.append(f"the Prices sheet has {len(got_days)} month columns, not min({months}, 24)")
    d.keys("month column", set(got_days), set(days))
    d.keys("instrument", {r["ISIN"] for r in rows}, {r["asset_id"] for r in ref})
    for r in rows:
        for day in got_days:
            if (r["ISIN"], day) in want:
                d.num(f"{r['ISIN']} on {day}", r[day], want[(r["ISIN"], day)], "decimal")
    return f"{len(rows)} instruments × {len(got_days)} month-ends"


# A listed movement that changed the book: the outcomes `Effects.from` counts as written (IA-C13 v1.2) — a ledger
# correction (`reversed`) and an SCD2 `closed` row each count one `inserted` in the journal's effects, so they are
# changed movements here too (IA-P4 review R5). `rejected` rows are listed and change nothing.
CHANGED_OUTCOMES = ("inserted", "updated", "closed", "reversed")
COUNTS_ONLY = "Batches committed with counts only"


def sync_run_changes(wb: Workbook, ref: list[dict[str, str]], d: Diff) -> str:
    # a batch committed with counts only is counted in the workbook but none of its rows is listed: the listing is a
    # part, and holding a part to the journal's whole proves nothing either way — refused, as the reference refuses it
    run = wb.facts("Run")
    if COUNTS_ONLY not in run:
        raise Refused(f"the Run sheet has no {COUNTS_ONLY!r} fact — not the change log this reads")
    undetailed = int(dec(run[COUNTS_ONLY].get("Value")) or 0)
    if undetailed > 0:
        raise Refused(f"{undetailed} batch(es) of the run were committed with counts only — the change log cannot list their rows; pick a run committed with rows")
    by_target = {r["target"]: r for r in ref if r.get("target")}
    tx = wb.table("Transactions", "Portfolio")
    changed = sum(1 for r in tx if r["Outcome"] in CHANGED_OUTCOMES)
    prices = wb.table("Prices", "Count")
    count = int(dec(prices[0]["Count"]) or 0) if prices else 0
    book_tx = by_target.get("investment.transaction", {}).get("changed", "0")
    book_prices = by_target.get("investment.asset_price", {}).get("changed", "0")
    # 0 = 0 on both counts holds nothing: a run that changed no movement and no price (an hourly run of unchanged rows)
    # would "pass" while proving no figure — refused, so the evidence is never an empty agreement (R13)
    if changed == 0 and count == 0 and (dec(book_tx) or 0) == 0 and (dec(book_prices) or 0) == 0:
        raise Refused("the run changed no movement and no price, in the workbook and in the journal — there is nothing to hold; pick a run that changed something")
    d.num("movements changed (investment.transaction)", str(changed), book_tx, "count")
    d.num("prices changed (investment.asset_price)", prices[0]["Count"] if prices else "0", book_prices, "count")
    return f"{changed} movements, {count} prices"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="overview_fingerprint.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compare")
    c.add_argument("template", choices=TEMPLATES)
    c.add_argument("workbook")
    c.add_argument("reference")
    c.add_argument("--months", type=int)
    c.add_argument("--tolerance", default="0.01")
    c.add_argument("--decimal-tolerance", default="0.000001")
    a = ap.parse_args(argv)
    d = Diff(Decimal(a.tolerance), Decimal(a.decimal_tolerance))
    try:
        wb = Workbook(a.workbook)
        ref = read_reference(a.reference)
        what = {
            "portfolio-statement:v1": lambda: statement(wb, ref, d),
            "client-overview:v1": lambda: client_overview(wb, ref, d),
            "distributor-overview:v1": lambda: distributor_overview(wb, ref, d),
            "price-sheet:v1": lambda: price_sheet(wb, ref, d, a.months),
            "sync-run-changes:v1": lambda: sync_run_changes(wb, ref, d),
        }[a.template]()
    except Refused as e:
        print(f"✗ {e}", file=sys.stderr)
        return 2
    if d.lines:
        print(f"✗ {a.template}: {len(d.lines)} difference(s) between the workbook and the book:")
        for line in d.lines:
            print(f"  {line}")
        return 1
    print(f"✓ {a.template}: the workbook equals the book — {what}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
