#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""BI-4 · S4.2 — the Superset dashboards as content (contract C-23). Bundles: dashboards/ (README there).

    uv run scripts/dashboards.py check                       # every bundle against the rules below; no cluster
    uv run scripts/dashboards.py kustomize [--check]         # dashboards/kustomization.yaml from the bundles
    uv run scripts/dashboards.py unpack EXPORT.zip ID WORLD  # a Superset export → dashboards/ID/bundle/WORLD/

A bundle is Superset's own export of one dashboard in one world (`dashboards/<id>/bundle/<world>/`), less the two
things olymp owns: the database files and `metadata.yaml` (platform/bi/superset, imported by superset-init-db). The
import Job (olymp platform/bi/superset-dashboards) mounts every bundle file from one ConfigMap and puts them back
together. `kustomize` writes that ConfigMap's file list, and `check` refuses, before the merge, what the import would
refuse or get wrong after it: it skips a dashboard whose charts it cannot resolve, renames a legacy chart type, and
fails on a second dataset over one model object.

Exit code: 0 = clean; 1 = problems (listed); 2 = usage.
"""

from __future__ import annotations

import argparse
import io
import json
import pathlib
import re
import sys
import unicodedata
import zipfile

import yaml

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
ROOT = REPO / "dashboards"
KINDS = ("datasets", "charts", "dashboards")
# What a dataset may read: the model's logical layer, by its catalog names (C-23). `db.dbo` is the physical layer.
SCHEMAS = {"obj.query": "query", "er.entity": "entity"}
KEY = re.compile(r"^[a-z0-9-]+\.[a-z]+\.(datasets|charts|dashboards)\.[A-Za-z0-9_-]+\.yaml$")
# The chart types Superset 6.1's import renames (commands/chart/importers/v1/utils.py `migrate_chart`, the
# `source_viz_type`s of migrations/shared/migrate_viz/processors.py). The row then has another type than its file,
# and olymp's check.py fails every sync over it.
LEGACY_VIZ = {"bar": "echarts_timeseries_bar", "dist_bar": "echarts_timeseries_bar", "line": "echarts_timeseries_line",
              "area": "echarts_area", "pivot_table": "pivot_table_v2", "treemap": "treemap_v2",
              "sunburst": "sunburst_v2", "bubble": "bubble_v2", "heatmap": "heatmap_v2", "histogram": "histogram_v2",
              "sankey": "sankey_v2", "dual_line": "mixed_timeseries"}


def load_yaml(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def slug(text: str) -> str:
    """A file name from a title, the way a person would type it: `Týdny s výpadkem` → `tydny-s-vypadkem`."""
    ascii_ = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-") or "unnamed"


# ── the bundles ───────────────────────────────────────────────────────────────────────────────────


def manifest(root: pathlib.Path = ROOT) -> dict:
    return load_yaml(root / "import.yaml")


def bundle_files(root: pathlib.Path = ROOT) -> dict[str, pathlib.Path]:
    """ConfigMap key → file, for every file of every bundle import.yaml lists, in a stable order."""
    files: dict[str, pathlib.Path] = {}
    for d in manifest(root).get("dashboards") or []:
        for world in d.get("worlds") or []:
            base = root / d["id"] / "bundle" / world
            for kind in KINDS:
                for path in sorted((base / kind).glob("*.yaml")):
                    files[f"{d['id']}.{world}.{kind}.{path.name}"] = path
    return files


def problems(root: pathlib.Path = ROOT, model: pathlib.Path = REPO / "model") -> list[str]:
    m = manifest(root)
    out: list[str] = []
    worlds = m.get("worlds") or {}
    listed = {d.get("id") for d in m.get("dashboards") or []}
    for d in sorted(p.name for p in root.iterdir() if p.is_dir()):
        if d not in listed:
            out.append(f"{d}/: not listed in import.yaml — the import would never see it")
    model_text = "\n".join(p.read_text(encoding="utf-8") for p in sorted(model.rglob("*.ttrm")))
    # Across every bundle: uuid → (where, the object); (world, schema, table) → (dataset uuid, where);
    # dashboard slug → (dashboard uuid, where).
    seen: dict[str, dict] = {"uuid": {}, "table": {}, "slug": {}}
    for d in m.get("dashboards") or []:
        did = d.get("id", "")
        if not re.fullmatch(r"[a-z0-9-]+", did):
            out.append(f"import.yaml: dashboard id {did!r} must be lower-case words joined by '-'")
            continue
        if not (root / did / "README.md").is_file():
            out.append(f"{did}/README.md: missing (purpose, datasets, personas, expected numbers)")
        for world in d.get("worlds") or []:
            if world not in worlds:
                out.append(f"import.yaml: {did} names world {world!r}, which `worlds` does not define")
                continue
            out += bundle_problems(root / did / "bundle" / world, f"{did}/bundle/{world}", world, worlds[world],
                                   model_text, seen)
    return out


def chart_nodes(position: dict) -> list[dict]:
    return [n for n in (position or {}).values() if isinstance(n, dict) and n.get("type") == "CHART"]


def bundle_problems(base: pathlib.Path, where: str, world_name: str, world: dict, model_text: str,
                    seen: dict) -> list[str]:
    out: list[str] = []
    if not base.is_dir():
        return [f"{where}/: no such bundle"]
    for extra in ("databases", "metadata.yaml"):
        if (base / extra).exists():
            out.append(f"{where}/{extra}: olymp owns it (platform/bi/superset) — drop it from the bundle")
    for path in sorted(base.iterdir()):
        if path.name not in KINDS and path.name not in ("databases", "metadata.yaml"):
            out.append(f"{where}/{path.name}: not a bundle directory ({', '.join(KINDS)})")
    objs = {kind: {p.name: load_yaml(p) for p in sorted((base / kind).glob("*.yaml"))} for kind in KINDS}
    for kind, files in objs.items():
        for name, obj in files.items():
            if not KEY.match(f"x.y.{kind}.{name}"):
                out.append(f"{where}/{kind}/{name}: file names are letters, digits, '-' and '_' (a ConfigMap key)")
            u = obj.get("uuid")
            if not u:
                out.append(f"{where}/{kind}/{name}: no uuid")
                continue
            if u in seen["uuid"] and seen["uuid"][u][1] != obj:
                out.append(f"{where}/{kind}/{name}: uuid {u} is also {seen['uuid'][u][0]}, with other content — "
                           "one would overwrite the other")
            seen["uuid"].setdefault(u, (f"{where}/{kind}/{name}", obj))
    datasets = {o.get("uuid"): (n, o) for n, o in objs["datasets"].items()}
    charts = {o.get("uuid"): (n, o) for n, o in objs["charts"].items()}
    for name, ds in objs["datasets"].items():
        at = f"{where}/datasets/{name}"
        if ds.get("database_uuid") != world.get("database_uuid"):
            out.append(f"{at}: database_uuid {ds.get('database_uuid')} is not {world.get('database')}'s "
                       f"({world.get('database_uuid')})")
        if ds.get("sql"):
            out.append(f"{at}: a virtual dataset (sql) — the import rewrites its SQL through sqlglot; "
                       "datasets read model objects as they are")
        kind = SCHEMAS.get(ds.get("schema"))
        if kind is None:
            out.append(f"{at}: schema {ds.get('schema')!r} — a dataset reads {' or '.join(SCHEMAS)}")
        elif not re.search(rf"^\s*def {kind} {re.escape(str(ds.get('table_name')))}\b", model_text, re.M):
            out.append(f"{at}: {ds.get('schema')}.{ds.get('table_name')} is not a `def {kind}` of the model")
        # Superset keeps one dataset per (database, schema, table_name) (a UNIQUE constraint on Postgres): a second
        # uuid over the same object in the same world fails the import, after the merge.
        table = (world_name, ds.get("schema"), ds.get("table_name"))
        other = seen["table"].setdefault(table, (ds.get("uuid"), at))
        if other[0] != ds.get("uuid"):
            out.append(f"{at}: {table[1]}.{table[2]} in {world_name} is already dataset {other[0]} ({other[1]}) — "
                       "Superset holds one dataset per object and database: reuse that uuid")
    on_a_dashboard: set[str] = set()
    for name, ch in objs["charts"].items():
        at = f"{where}/charts/{name}"
        if ch.get("dataset_uuid") not in datasets:
            out.append(f"{at}: its dataset {ch.get('dataset_uuid')} is not in the bundle")
        try:
            context = json.loads(ch.get("query_context") or "null")
        except json.JSONDecodeError:
            context = None
        if not isinstance(context, dict):
            out.append(f"{at}: no query_context — GET /api/v1/chart/<id>/data (the one-number check) needs it")
        elif (context.get("form_data") or {}).get("viz_type") != ch.get("viz_type"):
            out.append(f"{at}: its query_context was saved for another viz type than {ch.get('viz_type')!r}")
        if ch.get("viz_type") in LEGACY_VIZ:
            out.append(f"{at}: viz type {ch.get('viz_type')!r} is legacy — the import turns it into "
                       f"{LEGACY_VIZ[ch['viz_type']]!r}; re-save the chart in Superset 6.1 and export again")
    for name, db in objs["dashboards"].items():
        at = f"{where}/dashboards/{name}"
        nodes = chart_nodes(db.get("position"))
        for n in nodes:
            if "uuid" not in (n.get("meta") or {}):
                out.append(f"{at}: a CHART node without meta.uuid ({n.get('id', '?')}) — the import skips it")
        placed = {n["meta"]["uuid"] for n in nodes if "uuid" in (n.get("meta") or {})}
        for u in sorted(placed - set(charts)):
            out.append(f"{at}: places chart {u}, which is not in the bundle — the import would skip the dashboard")
        on_a_dashboard |= placed
        if db.get("published") is not True:
            out.append(f"{at}: published must be true — a BI Viewer sees published dashboards only")
        # And one dashboard per slug: a second uuid with the same slug fails the import, after the merge.
        if s := db.get("slug"):
            other = seen["slug"].setdefault(s, (db.get("uuid"), at))
            if other[0] != db.get("uuid"):
                out.append(f"{at}: slug {s!r} is already dashboard {other[0]} ({other[1]}) — slugs are unique")
    for u, (name, _) in charts.items():
        if u not in on_a_dashboard:
            out.append(f"{where}/charts/{name}: on no dashboard of the bundle")
    if not objs["dashboards"]:
        out.append(f"{where}/: no dashboard")
    return out


# ── kustomization.yaml ────────────────────────────────────────────────────────────────────────────

HEADER = """\
# GENERATED by `just dashboards-kustomize` from import.yaml and the bundles; `just dashboards-check` fails on drift.
#
# Renders every bundle file into the `superset-dashboards` ConfigMap. olymp's `superset-dashboards` Application applies
# it beside the import Job (platform/bi/superset-dashboards). The Job is a PostSync hook, so a merge that changes a
# bundle changes this ConfigMap and the import runs (contract C-23). ConfigMap keys cannot hold `/`: a key is
# `<dashboard>.<world>.<kind>.<file>`, and the Job re-nests it by `<kind>`.
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

configMapGenerator:
  - name: superset-dashboards
    files:
"""
FOOTER = """\
generatorOptions:
  # Stable name — the import Job mounts `superset-dashboards`.
  disableNameSuffixHash: true
"""


def kustomization(root: pathlib.Path = ROOT) -> str:
    lines = [f"      - {key}={path.relative_to(root).as_posix()}" for key, path in bundle_files(root).items()]
    return HEADER + ("\n".join(lines) + "\n" if lines else "      []\n") + FOOTER


def kustomization_current(root: pathlib.Path = ROOT) -> bool:
    path = root / "kustomization.yaml"
    return path.is_file() and path.read_text(encoding="utf-8") == kustomization(root)


# ── unpack ────────────────────────────────────────────────────────────────────────────────────────


def unpack(export: bytes, target: pathlib.Path) -> list[str]:
    """A Superset export ZIP (`dashboard_export_<ts>/…`) → a bundle at `target`, replacing what is there.

    Superset names its files `<title>_<id>.yaml`. The id is the exporting instance's, so a re-export would rename
    every file. A bundle names them after the object instead: a dataset by its table, a chart by its name, the
    dashboard by its title. Databases and `metadata.yaml` are left out (olymp's)."""
    written: list[str] = []
    with zipfile.ZipFile(io.BytesIO(export)) as z:
        entries = {}
        for info in z.infolist():
            parts = pathlib.PurePosixPath(info.filename).parts
            if len(parts) >= 3 and parts[1] in KINDS and info.filename.endswith(".yaml"):
                entries.setdefault(parts[1], []).append(z.read(info).decode("utf-8"))
    # Same-titled objects get `-2`, `-3`: in uuid order, so a re-export names each object as the last one did.
    for kind in entries:
        entries[kind].sort(key=lambda text: str(yaml.safe_load(text).get("uuid", "")))
    names = {"datasets": "table_name", "charts": "slice_name", "dashboards": "dashboard_title"}
    for kind in KINDS:
        (target / kind).mkdir(parents=True, exist_ok=True)
        for old in (target / kind).glob("*.yaml"):
            old.unlink()
        used: set[str] = set()
        for text in entries.get(kind, []):
            stem = slug(str(yaml.safe_load(text).get(names[kind], "")))
            name, n = stem, 2
            while name in used:
                name, n = f"{stem}-{n}", n + 1
            used.add(name)
            (target / kind / f"{name}.yaml").write_text(text, encoding="utf-8")
            written.append(f"{kind}/{name}.yaml")
    return written


# ── main ──────────────────────────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    k = sub.add_parser("kustomize")
    k.add_argument("--check", action="store_true", help="fail when dashboards/kustomization.yaml is stale")
    u = sub.add_parser("unpack")
    u.add_argument("export", type=pathlib.Path)
    u.add_argument("id")
    u.add_argument("world")
    args = ap.parse_args(argv)

    if args.cmd == "check":
        found = problems()
        for p in found:
            print(f"✗ {p}")
        stale = not kustomization_current()
        if stale:
            print("✗ dashboards/kustomization.yaml is stale or missing — run `just dashboards-kustomize`")
        if not found and not stale:
            print(f"✓ {len(bundle_files())} bundle files, every rule holds")
        return 1 if found or stale else 0
    if args.cmd == "kustomize":
        if args.check:
            ok = kustomization_current()
            print("✓ dashboards/kustomization.yaml is current" if ok else "✗ stale — run `just dashboards-kustomize`")
            return 0 if ok else 1
        path = ROOT / "kustomization.yaml"
        path.write_text(kustomization(), encoding="utf-8")
        print(f"wrote {path.relative_to(REPO)} ({len(bundle_files())} files)")
        return 0
    target = ROOT / args.id / "bundle" / args.world
    for name in unpack(args.export.read_bytes(), target):
        print(f"  {target.relative_to(REPO)}/{name}")
    print("next: `just dashboards-kustomize`, then `just dashboards-check`")
    return 0


if __name__ == "__main__":
    sys.exit(main())
