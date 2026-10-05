#!/usr/bin/env python3
"""IA-P4b·S4b.2 — `model/investment/income-labels.yaml` (IA-C55), read for the fingerprint references.

The report classifies each cash and external-flow movement by its provider label with this table (kantheon's renderer,
`IncomeLabels`); the references (`scripts/sql/evolution-reference.sql`) must classify the book with the SAME table, or a
fingerprint compares two classifications instead of two computations. The table is synced from kantheon with the model
(`just sync-investment-model`, `INVESTMENT_FILES`), so this reads the copy under `model/investment/` by default.

## Why a reader of its own

The drill runs in `postgres:16-alpine` with python3 and nothing else, and no YAML library is in the standard library.
The table has ONE shape — `version: N`, then `labels:` as a block list of flat mappings — so this reads exactly that
shape and REFUSES anything else, naming the line: a table it half-understood would classify silently wrong, which is the
one failure a fingerprint must not have. The rules the renderer enforces at boot are enforced here too (known keys only,
the class and leg vocabularies, `match: exact|prefix`, every label already normalised, one entry per label,
match kind and leg — an entry without `leg` covering both).

Subcommands:

    income_labels.py sql <income-labels.yaml>          → the table as a psql relation: `:labels` in the reference
    income_labels.py check <income-labels.yaml>        → `version N, M labels` or a refusal
    income_labels.py normalize <label>                 → the label as the table spells it

The relation's columns are (ord, label, leg, mtch, cls): `ord` is the entry's position in the file — the renderer takes
the FIRST exact entry that fits a movement's leg, so the order is part of the table.
"""

from __future__ import annotations

import json
import re
import sys

FIELDS = {"label", "class", "leg", "match", "note"}
CLASSES = {"dividend", "coupon", "interest", "fee", "tax", "other"}
LEGS = {"cash", "external-flow"}
MATCHES = {"exact", "prefix"}

#: Kotlin's `(?U)\s` — Unicode White_Space (the renderer's normalisation), spelled out: Python's `\s` on str is NOT
#: that set (it also matches U+001C…U+001F, which White_Space does not), and neither is `str.strip()`'s.
_WS_CHARS = "\t\n\x0b\x0c\r \x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000"
_WS = "".join(chr(c) for c in [9, 10, 11, 12, 13, 32, 0x85, 0xA0, 0x1680, *range(0x2000, 0x200B), 0x2028, 0x2029,
                               0x202F, 0x205F, 0x3000])
_WHITESPACE = re.compile(f"[{_WS_CHARS}]+")
_IDENT = re.compile(f"[{_WS_CHARS}]+ident\\..*$", re.DOTALL)


class Invalid(Exception):
    pass


def normalize(label: str) -> str:
    """The renderer's normalisation (kantheon `IncomeLabels.normalize`, pinned by `income-labels.cases.json`):
    whitespace runs one space, trimmed, lower case; only the text after the LAST ", "; no trailing ` ident. …`."""
    s = _WHITESPACE.sub(" ", label).strip(_WS).lower()
    comma = s.rfind(", ")
    if comma >= 0:
        s = s[comma + 2:]
    return _IDENT.sub("", s).strip(_WS)


def _scalar(text: str, where: str) -> str:
    """One value: a double-quoted string (JSON escapes) or a bare word; a trailing ` # comment` allowed after either."""
    text = text.strip()
    if text.startswith('"'):
        decoder = json.JSONDecoder()
        try:
            value, end = decoder.raw_decode(text)
        except json.JSONDecodeError as e:
            raise Invalid(f"{where}: a quoted value that does not close — {e.msg}")
        rest = text[end:].strip()
        if rest and not rest.startswith("#"):
            raise Invalid(f"{where}: text after the closing quote: {rest!r}")
        return value
    if text.startswith(("'", "{", "[", "|", ">", "&", "*", "!")):
        raise Invalid(f"{where}: {text[:1]!r} — this reader takes a double-quoted string or a bare word only")
    bare = text.split(" #", 1)[0].strip()
    if not bare:
        raise Invalid(f"{where}: no value")
    return bare


def parse(text: str, source: str = "income-labels.yaml") -> tuple[int, list[dict]]:
    version: int | None = None
    labels: list[dict] | None = None
    current: dict | None = None
    for n, raw in enumerate(text.splitlines(), 1):
        where = f"{source}:{n}"
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "\t" in line[: len(line) - len(line.lstrip())]:
            raise Invalid(f"{where}: a tab in the indentation")
        if not line.startswith(" "):
            key, sep, value = line.partition(":")
            if not sep:
                raise Invalid(f"{where}: expected `key: value` at the top level, got {line!r}")
            if key == "version":
                v = _scalar(value, where)
                if not v.isdigit() or int(v) < 1:
                    raise Invalid(f"{where}: `version` must be a whole number ≥ 1, got {v!r}")
                version = int(v)
            elif key == "labels":
                if value.strip() == "[]":
                    labels = []
                elif value.strip():
                    raise Invalid(f"{where}: `labels:` must start a block list (or be `[]`)")
                else:
                    labels = []
            else:
                raise Invalid(f"{where}: unknown top-level key {key!r} (version, labels)")
            current = None
            continue
        if labels is None:
            raise Invalid(f"{where}: an indented line outside `labels:`")
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if stripped.startswith("- "):
            if indent != 2:
                raise Invalid(f"{where}: a list item must be indented two spaces")
            current = {}
            labels.append(current)
            stripped = stripped[2:]
        elif indent != 4 or current is None:
            raise Invalid(f"{where}: a mapping key must be indented four spaces, under a `- ` item")
        key, sep, value = stripped.partition(":")
        if not sep or not re.fullmatch(r"[a-z]+", key):
            raise Invalid(f"{where}: expected `key: value`, got {stripped!r}")
        if key in current:
            raise Invalid(f"{where}: `{key}` given twice")
        current[key] = _scalar(value, where)
    if version is None:
        raise Invalid(f"{source}: no `version`")
    if labels is None:
        raise Invalid(f"{source}: no `labels`")

    seen: dict[tuple[str, str], list[str | None]] = {}
    entries = []
    for i, e in enumerate(labels):
        at = f"{source}: labels[{i}]"
        unknown = sorted(set(e) - FIELDS)
        if unknown:
            raise Invalid(f"{at} has unknown keys {unknown} (allowed: {sorted(FIELDS)})")
        label = e.get("label", "")
        if not label.strip():
            raise Invalid(f"{at} has no `label`")
        if normalize(label) != label:
            raise Invalid(f"{at} label {label!r} is not normalised — it could never match; write {normalize(label)!r}")
        cls = e.get("class")
        if cls not in CLASSES:
            raise Invalid(f"{at} ({label!r}) has class {cls!r} — one of {'|'.join(sorted(CLASSES))}")
        leg = e.get("leg")
        if leg is not None and leg not in LEGS:
            raise Invalid(f"{at} ({label!r}) has leg {leg!r} — cash or external-flow")
        match = e.get("match", "exact")
        if match not in MATCHES:
            raise Invalid(f"{at} ({label!r}) has match {match!r} — exact or prefix")
        # one entry per label, match kind and leg — an entry without `leg` is on both legs, so any second entry of its
        # label and kind overlaps it and the file's order would pick between them (the renderer refuses it too, R16)
        for other_leg in seen.get((label, match), []):
            if other_leg is None or leg is None or other_leg == leg:
                raise Invalid(
                    f"{source}: {label!r} listed twice — one entry per label and leg; an entry without `leg` covers both"
                )
        seen.setdefault((label, match), []).append(leg)
        entries.append({"ord": i + 1, "label": label, "leg": leg, "match": match, "class": cls})
    return version, entries


def _lit(v: str | None) -> str:
    return "CAST(NULL AS TEXT)" if v is None else "'" + v.replace("'", "''") + "'"


def relation(entries: list[dict]) -> str:
    """The table as a psql relation for `lbl (ord, label, leg, mtch, cls) AS (:labels)` — ONE line, every value a
    literal (the labels are the file's, never a person's input at run time); an empty table is an empty relation."""
    if not entries:
        return "SELECT 0, CAST(NULL AS TEXT), CAST(NULL AS TEXT), CAST(NULL AS TEXT), CAST(NULL AS TEXT) WHERE FALSE"
    rows = ", ".join(
        f"({e['ord']}, {_lit(e['label'])}, {_lit(e['leg'])}, {_lit(e['match'])}, {_lit(e['class'])})" for e in entries
    )
    return f"VALUES {rows}"


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in ("sql", "check", "normalize"):
        print(__doc__.split("Subcommands:")[1].split("The relation")[0].strip(), file=sys.stderr)
        return 2
    cmd, arg = argv
    if cmd == "normalize":
        print(normalize(arg))
        return 0
    try:
        with open(arg, encoding="utf-8") as f:
            version, entries = parse(f.read(), arg)
    except OSError as e:
        print(f"income-labels: cannot read {arg}: {e.strerror}", file=sys.stderr)
        return 1
    except Invalid as e:
        print(f"income-labels: {e}", file=sys.stderr)
        return 1
    if cmd == "sql":
        print(relation(entries))
    else:
        print(f"version {version}, {len(entries)} labels")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
