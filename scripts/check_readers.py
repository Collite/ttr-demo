#!/usr/bin/env python3
"""Regenerate and check the metadata reader fixtures with the repository CLI pin."""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
CASES = (
    ("om/generated", "import-schema", "file:", "om/snapshot", "om-tables/1"),
    ("glossary/generated", "import-glossary", "", "glossary/trade.ttl", "skos/1",
     "--package", "glossary", "--overlay", "glossary/overlay.yaml"),
    ("glossary/generated-om", "import-glossary", "", "glossary/trade.csv", "om-glossary/1", "--package", "glossary"),
    ("xmi/generated/carried-world", "import-xmi", "", "xmi/carried-world.xmi", "ttr-mdg/1", "--package", "shop"),
    ("xmi/generated/ea-before", "import-xmi", "", "xmi/ea/orders.xmi", "ea-erd/1", "--package", "orders"),
    ("xmi/generated/ea-after", "import-xmi", "", "xmi/ea/orders-renamed.xmi", "ea-erd/1", "--package", "orders"),
    ("pdm/generated", "import-pdm", "", "pdm/input", "pdm/16"),
)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def cli(*args, expected=0):
    result = subprocess.run(["just", "reader-cli", *args], cwd=ROOT, capture_output=True, text=True)
    require(result.returncode == expected,
            f"{' '.join(map(str, args))}: expected exit {expected}, got {result.returncode}\n"
            f"{result.stderr}{result.stdout}")
    return result


def files(root):
    return {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def check_equal(expected, actual, label):
    paths = expected.keys() | actual.keys()
    changed = sorted(str(path) for path in paths if expected.get(path) != actual.get(path))
    require(not changed, f"{label} differs: {', '.join(changed)}")


def read_json(path):
    return json.loads(path.read_bytes())


def generate(work):
    sources = work / "sources"
    shutil.copytree(ROOT / "sources", sources, ignore=shutil.ignore_patterns("generated", "generated-om"))
    for output, command, prefix, source, profile, *options in CASES:
        options = [sources / arg if arg.endswith(".yaml") else arg for arg in options]
        cli(command, "--from", prefix + str(sources / source), "--profile", profile,
            "--out", sources / output, "--format", "json", *options)
    return sources


def check_round_trip(work, sources):
    original = sources / "xmi/carried-world"
    restored = work / "restored"
    shutil.copytree(original, restored, ignore=shutil.ignore_patterns("shop"))
    shutil.copytree(sources / "xmi/generated/carried-world/shop", restored / "model/shop")

    xmi = work / "xmi"
    cli("export", "--format", "xmi", "--profile", "ttr-mdg/1", "--out", xmi, original)
    require((xmi / "model.xmi").read_bytes() == (sources / "xmi/carried-world.xmi").read_bytes(),
            "The committed XMI differs from the export of the carried world")

    dumps = []
    for name, checkout in (("original", original), ("restored", restored)):
        out = work / name
        cli("export", "--format", "defs.json", "--out", out, checkout)
        dump = read_json(out / "defs.json")
        del dump["snapshot"]  # The fingerprint includes the physical source files.
        dumps.append(dump)
    require(dumps[0] == dumps[1], "The carried world's semantic dump changed after XMI import")
    print("XMI carried-world export and semantic round trip passed")


def check_ea_rename(work, sources):
    ea = sources / "xmi/ea"
    active = work / "orders.xmi"
    out = work / "ea"
    first = ea / "orders.xmi"
    second = ea / "orders-renamed.xmi"
    options = ("--profile", "ea-erd/1", "--package", "orders", "--out", out)

    shutil.copyfile(first, active)
    cli("import-xmi", "--from", active, *options, "--overlay", ea / "overlay.yaml")
    shutil.copyfile(second, active)  # Delta only compares generations from the same input path.
    report = cli("import-xmi", "--from", active, *options).stdout
    renamed = read_json(out / "report.json")["delta"]["renamed"]
    old = "orders.er.entity.Order"
    new = "orders.er.entity.PurchaseOrder"
    suffixes = ("", ".order_no", ".placed")
    require([(row["from"], row["to"]) for row in renamed] ==
            [(old + suffix, new + suffix) for suffix in suffixes], "Unexpected EA rename delta")
    require(f"`{old}` | `{new}`" in report and "renames.yaml" in report, "Missing EA rename guidance")

    checkout = work / "ea-checkout"
    (checkout / "model").mkdir(parents=True)
    shutil.copyfile(ea / "renames.yaml", checkout / "model/renames.yaml")
    rejected = cli("import-xmi", "--from", second, *options, "--root", checkout,
                   "--overlay", ea / "overlay.yaml", expected=1)
    require(f"error xm/overlay-orphan /{old}:" in rejected.stderr, "Expected the stale EA overlay to be refused")
    print(f"EA rename passed ({len(renamed)} entries and one stale overlay refusal)")


def check_generated_guard(sources):
    out = sources / "om/generated"
    model = out / "om/db.ttrm"
    options = ("--strict", "--root", out, "--format", "github")
    cli("lint", *options)
    original = model.read_bytes()
    changed = original.replace(b"People and companies who place orders.", b"Edited customer description.", 1)
    require(changed != original, "The guard fixture is missing its customer description")
    model.write_bytes(changed)
    rejected = cli("lint", *options, expected=1)
    require("xm/generated-edited" in rejected.stdout + rejected.stderr, "Missing generated-edit diagnostic")
    committed = files(ROOT / "sources/om/generated")
    regenerated = files(out)
    try:
        check_equal(committed, regenerated, "Edited package")
    except RuntimeError as error:
        require(str(error) == "Edited package differs: om/db.ttrm", str(error))
    else:
        raise RuntimeError("The byte comparison accepted an edited package")
    print("Generated-package guard passed (clean accepted, edited refused by lint and byte comparison)")


def main():
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="readers-", dir=build) as directory:
        work = Path(directory)
        first = generate(work / "first")
        second = generate(work / "second")
        count = 0
        for output, *_ in CASES:
            golden = files(ROOT / "sources" / output)
            require(golden, f"Missing golden for {output}")
            check_equal(golden, files(first / output), output)
            check_equal(files(first / output), files(second / output), f"{output} repeat")
            ignored = read_json(first / output / "report.json")["ignored"]
            require(ignored and all(row.get("reason") for row in ignored), f"Missing ignore reasons in {output}")
            count += len(golden)
            print(f"{output}: {len(golden)} files, {len(ignored)} ignored entries")
        check_round_trip(work, first)
        check_ea_rename(work, first)
        check_generated_guard(first)
        bad_pd = cli("import-pdm", "--from", first / "pdm/pd15.pdm", "--profile", "pdm/16",
                     "--out", work / "pd15", expected=1)
        require("xm/pdm-version" in bad_pd.stderr, "Missing PD 15 version diagnostic")
        print(f"Readers passed: {len(CASES)} cases run twice, {count} golden files, PD 15 refused")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        sys.exit(str(exc))
