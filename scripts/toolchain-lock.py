#!/usr/bin/env python3
"""Print toolchain.lock's pins as env lines (KEY=value) — the one reader of the lock that the workflows'
toolchain action, `just load-model` and scripts/regenerate-local.sh share (SO-demo P0, ⚑SO-P-4).

    python3 scripts/toolchain-lock.py [<lock>]      # default: toolchain.lock beside scripts/

Fails on a missing table or key and never prints an empty pin: an empty TTR_CORE_REF would check out
ttr-core's default branch — the unpinned toolchain the lock exists to prevent.
"""
import sys
import tomllib
from pathlib import Path

PINS = {
    "TTR_CORE_REF": ("ttr-core", "ref"),
    "VELES_TTR_METADATA": ("veles", "ttr-metadata"),
}


def main(argv: list[str]) -> None:
    path = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent / "toolchain.lock"
    lock = tomllib.loads(path.read_text(encoding="utf-8"))
    lines = []
    for env, (table, key) in PINS.items():
        value = lock.get(table, {}).get(key)
        if not isinstance(value, str) or not value.strip():
            sys.exit(f"{path}: [{table}].{key} is missing or empty")
        lines.append(f"{env}={value}")
    # All or nothing: a caller appending to $GITHUB_ENV must not get half the pins.
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv)
