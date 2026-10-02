#!/usr/bin/env python3
"""IA-P4·S4.2·T5 — the `investment-evolution:v2` fingerprint's comparison engine (IA-C51).

The shell (`scripts/fingerprint-evolution.sh`) does the I/O: it renders the workbook through studio-bff and runs the
reference (`scripts/sql/evolution-reference.sql`) on the book with psql. Everything that decides whether the two
AGREE lives here, where it can be tested without an estate (`scripts/tests/evolution-fingerprint.test.mjs`).

## The two sides

  * the WORKBOOK a client receives — kantheon's `PeriodEvolution`, assembled from door answers, written by POI;
  * the REFERENCE — the same period evolution computed on the tables with a recursive CTE.

They share no code and no query. Money agrees to ±0.01 (IA-C51), a percent to ±0.0001 pp, and the workbook's
`unexplained` is 0.00 on every row (IA-C47). The reference computes AVERAGE cost only: a workbook costed FIFO is not
compared. A window with an amount no rate converts is not compared either — the reference leaves those sums out where
the renderer leaves them empty, and two empties agreeing proves nothing.

Subcommands (each prints JSON on stdout, or exits non-zero naming what is wrong):

    evolution_fingerprint.py sheet <workbook.xlsx> <portfolio>   → {rows, summary, facts}
    evolution_fingerprint.py reference <psql.csv>                → {rows, summary, refused}
    evolution_fingerprint.py compare <workbook.json> <reference.json> [--tolerance 0.01] [--return-tolerance 0.0001]
    evolution_fingerprint.py expect <reference.json> <expected.csv> <scope-key> <grain> [--tolerance 0.005]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import zipfile
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from fingerprint import EXCEL_EPOCH, _cells, _shared_strings, _sheet_path

#: The Periods sheet's columns, in the workbook's order (kantheon `PeriodColumns.ALL`), each with the header the
#: template prints for it. Read by POSITION and checked by header: several headers repeat (Invested, Cash, "of which
#: FX" — once under Opening, once under Closing), so a header alone does not name a column.
PERIODS = [
    ("period", "Period"),
    ("period_start", "From"),
    ("period_end", "To"),
    ("portfolio_id", "Portfolio"),
    ("currency", "Currency"),
    ("invested_open", "Invested"),
    ("market_value_open", "Market value"),
    ("cash_open", "Cash"),
    ("unrealized_open", "Unrealized"),
    ("fx_unrealized_open", "of which FX"),
    ("deposits", "Deposits"),
    ("withdrawals", "Withdrawals *"),
    ("flows_net", "Net flows"),
    ("purchases_at_cost", "Purchases"),
    ("transfers_in_at_cost", "Transfers in"),
    ("sales_at_cost", "Sales at cost"),
    ("transfers_out_at_cost", "Transfers out"),
    ("sales_proceeds", "Sale proceeds"),
    ("realized_sales", "Realized on sales"),
    ("fx_realized", "of which FX"),
    ("income", "Income *"),
    ("realized_total", "Realized total"),
    ("fees", "Fees *"),
    ("fx_costs", "FX costs *"),
    ("costs_total", "Costs total"),
    ("cash_movements", "Cash movements"),
    ("fx_cash", "FX on cash"),
    ("invested_close", "Invested"),
    ("market_value_close", "Market value"),
    ("cash_close", "Cash"),
    ("unrealized_close", "Unrealized"),
    ("fx_unrealized_close", "of which FX"),
    ("unexplained", "Unexplained"),
    ("priced_instruments", "Priced"),
    ("unpriced_instruments", "Unpriced"),
    ("unconverted", "No rate"),
    ("missing_rate", "Missing rate"),
]

SUMMARY = [
    ("portfolio_id", "Portfolio"),
    ("currency", "Currency"),
    ("net_contributions", "Net contributions"),
    ("realized_sales_total", "Realized on sales"),
    ("fx_realized_total", "of which FX"),
    ("income_total", "Income *"),
    ("realized_total", "Realized total"),
    ("costs_total", "Costs total *"),
    ("fx_cash_total", "FX on cash"),
    ("unrealized_start", "Unrealized, start"),
    ("unrealized_end", "Unrealized, end"),
    ("fx_unrealized_end", "of which FX"),
    ("performance", "Performance"),
    ("plain_return_pct", "Plain return %"),
]

TEXT = {"period", "period_start", "period_end", "portfolio_id", "currency", "missing_rate"}
DATES = {"period_start", "period_end"}
COUNTS = {"priced_instruments", "unpriced_instruments", "unconverted"}
#: What the reference computes and the workbook is held to; `unconverted` / `missing_rate` are checked to be empty.
COMPARED = [k for k, _ in PERIODS if k not in ("unconverted", "missing_rate")]
MONEY = [k for k in COMPARED if k not in TEXT and k not in COUNTS]
SUMMARY_MONEY = [k for k, _ in SUMMARY if k not in ("portfolio_id", "currency", "plain_return_pct")]

TOTAL = "Total"


def dec(value: str | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def cents(value: Decimal | None) -> Decimal | None:
    return None if value is None else value.quantize(Decimal("0.01"))


# ── the workbook ─────────────────────────────────────────────────────────────────────────────────────────────────


def _letters(n: int) -> str:
    out = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def _table(rows: list[dict[str, str]], columns: list[tuple[str, str]], sheet: str, first: str) -> list[dict[str, str]]:
    """The table whose header row prints exactly [columns]' headers from column A; its rows until the first whose
    [first] column is not a number (the notes under a table are text)."""
    letters = [_letters(i) for i in range(len(columns))]
    want = [h for _, h in columns]
    at = next((i for i, r in enumerate(rows) if [r.get(c, "") for c in letters] == want), None)
    if at is None:
        heads = next((list(r.values()) for r in rows if r.get("A") == want[0]), None)
        raise SystemExit(f"the {sheet} sheet has no table headed {want} — the workbook has {heads}")
    probe = letters[[k for k, _ in columns].index(first)]
    out = []
    for r in rows[at + 1:]:
        if dec(r.get(probe)) is None:
            break
        out.append({k: r.get(c, "") for (k, _), c in zip(columns, letters)})
    return out


def read_workbook(path: str, portfolio: str) -> dict:
    with zipfile.ZipFile(path) as zf:
        strings = _shared_strings(zf)
        periods = _cells(zf, _sheet_path(zf, "Periods"), strings)
        summary = _cells(zf, _sheet_path(zf, "Summary"), strings)
        notes = _cells(zf, _sheet_path(zf, "Notes"), strings)

    rows = []
    for r in _table(periods, PERIODS, "Periods", "period_start"):
        if r["portfolio_id"] != portfolio:
            continue
        for k in DATES:
            # a date is a serial in the file; its display format is a style, not a value
            r[k] = (EXCEL_EPOCH + timedelta(days=int(Decimal(r[k])))).isoformat()
        rows.append(r)
    if not rows:
        raise SystemExit(f"the Periods sheet holds no row of {portfolio}")

    mine = [r for r in _table(summary, SUMMARY, "Summary", "net_contributions") if r["portfolio_id"] == portfolio]
    if len(mine) != 1:
        raise SystemExit(f"the Summary sheet holds {len(mine)} rows of {portfolio}, not one")

    # the Notes' facts: Item | Value, under their header, until the first row that is not a pair
    facts: dict[str, str] = {}
    start = next((i for i, r in enumerate(notes) if r.get("A") == "Item" and r.get("B") == "Value"), None)
    if start is not None:
        for r in notes[start + 1:]:
            if "A" not in r or "B" not in r:
                break
            facts[r["A"]] = r["B"]
    return {"rows": rows, "summary": mine[0], "facts": facts}


# ── the reference ────────────────────────────────────────────────────────────────────────────────────────────────


def read_reference(path: str) -> dict:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit("the reference answered no rows")
    missing = [k for k in COMPARED if k not in rows[0]]
    if missing:
        raise SystemExit(f"the reference answered no {', '.join(missing)}")
    refused = rows[0].get("refused", "")
    return {"rows": [{k: r[k] for k in COMPARED} for r in rows], "summary": summarize(rows), "refused": refused}


def summarize(rows: list[dict[str, str]]) -> dict[str, str]:
    """IA-C48's Summary from the reference's rows — the renderer's rules (kantheon `SummaryModel`), written again."""

    def total(k: str) -> Decimal:
        return sum((dec(r[k]) or Decimal(0)) for r in rows)

    start = dec(rows[0]["unrealized_open"]) or Decimal(0)
    end = dec(rows[-1]["unrealized_close"]) or Decimal(0)
    realized = total("realized_total")
    costs = total("costs_total")
    fx_cash = total("fx_cash")
    performance = realized + (end - start) - costs + fx_cash
    average = total("invested_open") / len(rows)
    out = {
        "net_contributions": total("deposits") - total("withdrawals"),
        "realized_sales_total": total("realized_sales"),
        "fx_realized_total": total("fx_realized"),
        "income_total": total("income"),
        "realized_total": realized,
        "costs_total": costs,
        "fx_cash_total": fx_cash,
        "unrealized_start": start,
        "unrealized_end": end,
        "fx_unrealized_end": dec(rows[-1]["fx_unrealized_close"]) or Decimal(0),
        "performance": performance,
        "plain_return_pct": (performance * 100 / average) if average > 0 else None,
    }
    return {k: ("" if v is None else str(v)) for k, v in out.items()}


# ── agreement ────────────────────────────────────────────────────────────────────────────────────────────────────


def compare(workbook: dict, reference: dict, tolerance: Decimal, return_tolerance: Decimal) -> list[str]:
    problems: list[str] = []
    if reference.get("refused"):
        return [f"the reference cannot compare this book: {reference['refused']}"]
    method = workbook["facts"].get("Cost basis", "")
    if method != "average":
        return [f"the workbook is costed `{method}`; the reference computes average cost only"]

    w, r = workbook["rows"], reference["rows"]
    for row in w:
        u = dec(row["unexplained"])
        if u is None or abs(u) >= Decimal("0.005"):
            problems.append(f"{row['period']}: the workbook's unexplained is {row['unexplained'] or 'empty'}, not 0.00")
        if (dec(row["unconverted"]) or 0) != 0 or row["missing_rate"]:
            problems.append(
                f"{row['period']}: {row['unconverted']} amounts had no rate ({row['missing_rate']}) — a window the rates "
                f"cannot convert is not fingerprinted"
            )
    if len(w) != len(r):
        problems.append(f"the workbook has {len(w)} periods, the reference {len(r)}")
    for a, b in zip(w, r):
        for k in COMPARED:
            if k in TEXT:
                if a[k] != b[k]:
                    problems.append(f"{a['period']} {k}: workbook {a[k]!r}, reference {b[k]!r}")
            elif k in COUNTS:
                if int(Decimal(a[k] or "0")) != int(Decimal(b[k] or "0")):
                    problems.append(f"{a['period']} {k}: workbook {a[k]}, reference {b[k]}")
            else:
                x, y = cents(dec(a[k])), cents(dec(b[k]))
                if x is None or y is None or abs(x - y) > tolerance:
                    problems.append(f"{a['period']} {k}: workbook {x}, reference {y}")

    ws, rs = workbook["summary"], reference["summary"]
    for k in SUMMARY_MONEY:
        x, y = cents(dec(ws.get(k))), cents(dec(rs.get(k)))
        if x is None or y is None or abs(x - y) > tolerance:
            problems.append(f"Summary {k}: workbook {x}, reference {y}")
    x, y = dec(ws.get("plain_return_pct")), dec(rs.get("plain_return_pct"))
    if (x is None) != (y is None) or (x is not None and abs(x - y) > return_tolerance):
        problems.append(f"Summary plain_return_pct: workbook {x}, reference {y}")
    return problems


def expect(reference: dict, expected_csv: str, key: str, grain: str, tolerance: Decimal) -> list[str]:
    """The reference against kantheon's HAND answers (the S4.1 fixture) — the third side, on the fixture alone."""
    with open(expected_csv, newline="") as f:
        want = [r for r in csv.DictReader(f) if r["scope"] == key and r["grain"] == grain and r["portfolio_id"] != TOTAL]
    problems = []
    if reference.get("refused"):
        problems.append(f"refused: {reference['refused']}")
    if len(want) != len(reference["rows"]):
        return problems + [f"{len(want)} expected rows, {len(reference['rows'])} computed"]
    for a, b in zip(reference["rows"], want):
        for k in COMPARED:
            if k in TEXT or k in COUNTS:
                if str(a[k]) != str(b[k]) and not (k in COUNTS and int(Decimal(a[k] or 0)) == int(Decimal(b[k] or 0))):
                    problems.append(f"{a['period']} {k}: computed {a[k]!r}, expected {b[k]!r}")
            else:
                x, y = dec(a[k]), dec(b[k])
                if x is None or y is None or abs(x - y) > tolerance:
                    problems.append(f"{a['period']} {k}: computed {cents(x)}, expected {y}")
    return problems


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="evolution_fingerprint.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sheet")
    s.add_argument("workbook")
    s.add_argument("portfolio")
    s = sub.add_parser("reference")
    s.add_argument("csv")
    s = sub.add_parser("compare")
    s.add_argument("workbook")
    s.add_argument("reference")
    s.add_argument("--tolerance", default="0.01")
    s.add_argument("--return-tolerance", default="0.0001")
    s = sub.add_parser("expect")
    s.add_argument("reference")
    s.add_argument("expected")
    s.add_argument("key")
    s.add_argument("grain")
    s.add_argument("--tolerance", default="0.005")
    a = ap.parse_args(argv)

    if a.cmd == "sheet":
        json.dump(read_workbook(a.workbook, a.portfolio), sys.stdout, indent=1)
        return 0
    if a.cmd == "reference":
        json.dump(read_reference(a.csv), sys.stdout, indent=1)
        return 0
    if a.cmd == "compare":
        with open(a.workbook) as f:
            w = json.load(f)
        with open(a.reference) as f:
            r = json.load(f)
        problems = compare(w, r, Decimal(a.tolerance), Decimal(a.return_tolerance))
        label = f"{len(w['rows'])} periods × {len(COMPARED)} columns + the Summary"
    else:
        with open(a.reference) as f:
            r = json.load(f)
        problems = expect(r, a.expected, a.key, a.grain, Decimal(a.tolerance))
        label = f"{len(r['rows'])} periods against the hand answers ({a.key}, {a.grain})"
    for p in problems:
        print(f"  ✗ {p}")
    if problems:
        print(f"{len(problems)} difference(s) — {label}")
        return 1
    print(f"agree — {label}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
