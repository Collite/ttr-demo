#!/usr/bin/env python3
"""Check every mounted `intent.yaml` against the GX placeholder contract.

Hartland has no CI lane, and that is exactly why this exists as a file rather than as a
one-off command in a task list: the same check on the kantheon side found that five of six
shipped shem prompts were pre-v2 files naming placeholders `PlanComposer.buildVars` has never
supplied — every one of them rendering EMPTY, with nothing anywhere saying so. These prompts
are mounted into a live estate and can drift the same way.

The kantheon sibling is `IntentPromptContractSpec`; the contract is
`project/kantheon/features/golem-prompt-context/contracts.md` §2 (placeholders) and §8 (header).

Usage:  python3 scripts/verify-intent-prompts.py        # from the repo root
Exit:   0 = every file conforms, 1 = at least one finding (printed).
"""
from __future__ import annotations

import pathlib
import re
import sys

# GX contracts §2 — the eight a prompt author may name.
CONTRACT_KEYS = {
    "question",
    "locale",
    "prior_view",
    "annotated_question",
    "lexicon_hints",
    "normalized_question",
    "queries",
    "entities",
}

# LR C-4·4 — slots a prompt MAY name and need not document: supplied on every compose
# (`PlanComposer.OPTIONAL_SLOTS`), never reported unused. `history` is the conversation so far.
OPTIONAL_KEYS = {"history"}

# What the `user:` half must name. The three GX-5 slots are what make a file actually GX-shaped
# — and `question` is here because it is the failure this check exists for: the pre-v2 prompts the
# kantheon sibling found were handing the composer a prompt WITH NO QUESTION IN IT, and every other
# check here would have passed a file that still did that. `annotated_question` and
# `normalized_question` both render the question, but both are EMPTY on the legacy route, so
# `question` is the only slot that is never blank.
GX_SLOTS = {"annotated_question", "lexicon_hints", "normalized_question", "question"}

# ⚑GXP-D3 — supplied for one deprecation window, WARNed by the composer. Legal in a mounted
# estate prompt, and a finding here anyway: these files are edited alongside the contract.
DEPRECATED_ALIASES = {"patterns", "schema", "bindings"}

PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*}}")
HEADER_FIRST_LINE = re.compile(r"^# intent — .+")


def halves(text: str) -> tuple[str, str]:
    """`system:` and `user:` as raw text. A dumb split, deliberately: pulling in a YAML parser
    for two top-level block scalars would add a dependency to a check that has none."""
    system_at = text.index("\nsystem:")
    user_at = text.index("\nuser:")
    return text[system_at:user_at], text[user_at:]


def check(path: pathlib.Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    findings: list[str] = []

    lines = text.splitlines()
    if not lines:
        return ["structure: the file is empty"]
    if not HEADER_FIRST_LINE.match(lines[0]):
        findings.append(f"header: first line is not `# intent — …` (got: {lines[0]!r})")

    # ⛑ Match `{{ name }}`, not the bare word. A substring test passes `annotated_question` off
    # as documentation for `question` — so a header that never mentioned `question` at all would
    # look complete, which is the one thing this check exists to notice.
    header = "\n".join(line for line in lines if line.startswith("#"))
    documented = set(PLACEHOLDER.findall(header))
    undocumented = sorted(CONTRACT_KEYS - documented)
    if undocumented:
        findings.append(f"header: does not document {undocumented} (S-3: it is the only docs)")

    try:
        system, user = halves(text)
    except ValueError:
        return findings + ["structure: no `system:` / `user:` halves"]

    named = set(PLACEHOLDER.findall(system + user))
    uncontracted = sorted(named - CONTRACT_KEYS - OPTIONAL_KEYS - DEPRECATED_ALIASES)
    if uncontracted:
        findings.append(f"placeholders: {uncontracted} are filled by nothing — they render EMPTY")

    deprecated = sorted(named & DEPRECATED_ALIASES)
    if deprecated:
        findings.append(f"placeholders: {deprecated} are deprecated (⚑GXP-D3) and log a WARN")

    missing = sorted(GX_SLOTS - set(PLACEHOLDER.findall(user)))
    if missing:
        findings.append(f"user half: missing the GX slots {missing}")

    return findings


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent.parent
    files = sorted(root.glob("agents/golem/shems/*/prompts/*/intent.yaml"))
    if not files:
        print("no intent.yaml found under agents/golem/shems — wrong working directory?")
        return 1

    failed = 0
    for path in files:
        rel = path.relative_to(root)
        findings = check(path)
        if findings:
            failed += 1
            print(f"✗ {rel}")
            for finding in findings:
                print(f"    {finding}")
        else:
            print(f"✓ {rel}")

    print(f"\n{len(files) - failed}/{len(files)} conform to the GX placeholder contract")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
