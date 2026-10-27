"""Ten read-only catalog checks; no login, secret retrieval, sync or mutation.

OM_URL and OM_TOKEN (or OM_TOKEN_FILE) are required. KUBE_CONTEXT defaults to hartland.
Thresholds reflect the current authored model: 36 physical tables/views, 40 ER
entities, six measures. Override OM_MIN_TABLES/ENTITIES/METRICS for a later model.
"""

import json
import os
import subprocess
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class CheckError(ValueError):
    """Only locally authored diagnostics are safe to show without response bodies."""


def require(ok, message):
    if not ok:
        raise CheckError(message)


class Catalog:
    def __init__(self, url, token):
        parsed = urlsplit(url)
        require(parsed.scheme in ("http", "https") and parsed.hostname, "invalid OM_URL")
        require(
            not (parsed.username or parsed.password or parsed.query or parsed.fragment),
            "OM_URL cannot contain credentials, query or fragment",
        )
        require(bool(token.strip()), "missing OM_TOKEN or OM_TOKEN_FILE")
        self.base = url.rstrip("/")
        if not self.base.endswith("/api"):
            self.base += "/api"
        self.token = token.strip()
        self.responses = {}
        self.lists = {}

    def get(self, path):
        if path in self.responses:
            return self.responses[path]
        request = Request(
            self.base + "/v1/" + path, headers={"Authorization": "Bearer " + self.token}
        )
        with build_opener(NoRedirect()).open(request, timeout=30) as response:
            result = json.load(response)
        self.responses[path] = result
        return result

    def listing(self, resource, fields):
        if (resource, fields) in self.lists:
            return self.lists[resource, fields]
        result, after, seen = [], None, set()
        while True:
            query = {"limit": 100, "fields": fields}
            if after:
                query["after"] = after
            page = self.get(resource + "?" + urlencode(query))
            result.extend(page["data"])
            after = page.get("paging", {}).get("after")
            if not after:
                self.lists[resource, fields] = result
                return result
            require(after not in seen, "repeated pagination cursor")
            seen.add(after)

    def tables(self):
        return self.listing("tables", "columns,tags,extension")

    def terms(self):
        return self.listing("glossaryTerms", "extension,parent")

    def store_sales(self):
        return self.get(
            "tables/name/"
            + quote("hartland-pg.hartland_us.public.store_sales", safe="")
            + "?fields=columns,tags,extension"
        )


def model_owned_metric(item):
    return item.get("extension", {}).get("ttrQname", "").startswith("md.measure.")


def columns(items):
    for item in items:
        yield item
        yield from columns(item.get("children") or [])


def summary(log):
    lines = []
    for line in log.splitlines():
        try:
            value = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict) and "snapshot" in value:
            lines.append(value)
    require(len(lines) == 1, "expected one connector JSON summary per Job")
    result = lines[0]
    require(isinstance(result["snapshot"], str) and result["snapshot"], "empty snapshot")
    require(
        all(
            type(result.get(k)) is int and result[k] >= 0
            for k in ("created", "updated", "deprecated", "linked", "warnings")
        ),
        "invalid summary counters",
    )
    require(type(result.get("not_modified")) is bool, "need connector >= 0.1.2 (not_modified missing/invalid)")
    return result


def check_noop(context, execute=subprocess.check_output):
    require(bool(context), "empty KUBE_CONTEXT")
    base = ["kubectl", "--context", context, "-n", "openmetadata"]
    jobs = json.loads(
        execute(
            base + ["get", "jobs", "-l", "app.kubernetes.io/name=om-project-tatrman", "-o", "json"],
            text=True,
            timeout=30,
        )
    )["items"]
    jobs.sort(key=lambda job: job["metadata"]["creationTimestamp"])
    require(len(jobs) >= 2, "need two completed projection Jobs")
    pair = jobs[-2:]
    require(
        all(job.get("status", {}).get("succeeded") == 1 for job in pair),
        "latest two projection Jobs must succeed",
    )
    require(
        pair[0]["status"]["completionTime"] <= pair[1]["status"]["startTime"],
        "projection Jobs overlapped",
    )
    summaries = []
    for job in pair:
        pods = json.loads(execute(
            base + ["get", "pods", "-l", "job-name=" + job["metadata"]["name"], "-o", "json"],
            text=True, timeout=30,
        ))["items"]
        succeeded = [p for p in pods if p.get("status", {}).get("phase") == "Succeeded"]
        require(len(succeeded) == 1, "expected exactly one Succeeded pod per projection Job")
        summaries.append(summary(execute(
            base + ["logs", "pod/" + succeeded[0]["metadata"]["name"], "-c", "project"],
            text=True, timeout=30,
        )))
    for index, value in enumerate(summaries):
        require(value["not_modified"] is False,
                ("first" if index == 0 else "second") + " Job did not sync (304); run the idempotency pair")
    require(summaries[0]["snapshot"] == summaries[1]["snapshot"], "source changed between Jobs")
    require(
        all(
            summaries[1][key] == 0
            for key in ("created", "updated", "deprecated", "linked", "warnings")
        ),
        "second projection is not a clean no-op",
    )
    return "same snapshot; all second-run counters zero"


def checks(catalog, env):
    def version():
        require(catalog.get("system/version")["version"] == "2.0.6", "expected OM2.0.6")
        return "2.0.6"

    def inventory(database):
        count = sum(
            t["fullyQualifiedName"].startswith(f"hartland-pg.{database}.public.")
            for t in catalog.tables()
        )
        minimum = int(env.get("OM_MIN_TABLES", "36"))
        require(count >= minimum, f"{count} < {minimum}")
        return f"{count} tables/views"

    def entities():
        terms = [
            t
            for t in catalog.terms()
            if t.get("glossary", {}).get("name") == "hartland Entities"
            and ".er.entity." in "." + t.get("extension", {}).get("ttrQname", "")
            and not t.get("parent")
            and t.get("status") != "Deprecated"
            and t.get("entityStatus") != "Deprecated"
        ]
        minimum = int(env.get("OM_MIN_ENTITIES", "40"))
        require(len(terms) >= minimum, f"{len(terms)} entities < {minimum}")
        return f"{len(terms)} ER entities (attributes excluded)"

    def metrics():
        items = [
            m
            for m in catalog.listing("metrics", "extension,tags")
            if model_owned_metric(m)
            and not any(t.get("tagFQN") == "Tatrman.Deprecated" for t in m.get("tags") or [])
        ]
        minimum = int(env.get("OM_MIN_METRICS", "6"))
        require(len(items) >= minimum, f"{len(items)} metrics < {minimum}")
        require(
            all(
                m.get("metricExpression", {}).get("code")
                and m.get("extension", {}).get("ttrAdditivity")
                for m in items
            ),
            "metric expression/additivity missing",
        )
        return f"{len(items)} metrics with expression/additivity"

    def qname():
        value = catalog.store_sales().get("extension", {}).get("ttrQname")
        require(value == "db.dbo.store_sales", "store_sales ttrQname missing/wrong")
        return value

    def grounded():
        table = catalog.store_sales()
        column = next(c for c in columns(table["columns"]) if c["name"] == "ss_item_sk")
        require(
            all(
                any(t["tagFQN"] == "Tatrman.Grounded" for t in target.get("tags") or [])
                for target in (table, column)
            ),
            "Grounded tag missing on table/column",
        )
        require(
            column.get("extension", {}).get("ttrQname") == "db.dbo.store_sales.ss_item_sk",
            "bound column ttrQname missing",
        )
        return "store_sales and ss_item_sk"

    def link():
        fqns = {
            t["fullyQualifiedName"]
            for t in catalog.terms()
            if t.get("glossary", {}).get("name") == "hartland Entities"
        }
        table = catalog.store_sales()
        require(
            any(
                t.get("source") == "Glossary" and t["tagFQN"] in fqns
                for asset in [table, *columns(table["columns"])]
                for t in asset.get("tags") or []
            ),
            "no retained term-to-asset link on store_sales",
        )
        return "glossary tag points to an existing projected term"

    def url():
        native = catalog.get("metadata/types/name/hyperlink-cp")
        string = catalog.get("metadata/types/name/string")
        for kind in ("table", "glossaryTerm", "metric"):
            registry = catalog.get(f"metadata/types/name/{kind}?fields=customProperties")
            properties = {p["name"]: p for p in registry.get("customProperties", [])}
            for name, field_type in (("ttrStudioLink", native), ("ttrUrl", string)):
                prop = properties.get(name)
                require(prop is not None and prop["propertyType"]["id"] == field_type["id"],
                        f"{kind}.{name} has the wrong custom-property type")

        def model_url(asset, model):
            parsed = urlsplit(asset.get("extension", {}).get("ttrUrl", ""))
            require(
                parsed.scheme == "https"
                and parsed.netloc == "studio.hartland.collite.cz"
                and parsed.path == f"/m/hartland/s/{model}"
                and not parsed.query
                and not parsed.fragment,
                f"invalid Studio {model} model URL",
            )
            link = asset.get("extension", {}).get("ttrStudioLink")
            require(isinstance(link, dict) and link.get("url") == parsed.geturl()
                    and link.get("displayText") == {
                        "db": "Open database model in Studio",
                        "er": "Open E-R model in Studio",
                        "md": "Open dimensional model in Studio",
                    }[model],
                    f"missing or invalid native Studio {model} hyperlink")

        def eligible(term):
            status = term.get("entityStatus") or term.get("status")
            require(bool(status), "cannot decide link eligibility: Hartland term has no status")
            return status in {"Approved", "Draft"}

        model_url(catalog.store_sales(), "db")
        checked_terms = 0
        for term in catalog.terms():
            if (term.get("glossary") or {}).get("name") not in {"hartland Entities", "hartland Concepts"}:
                continue
            qname = term.get("extension", {}).get("ttrQname", "")
            if not eligible(term):
                continue
            if qname.startswith(("er.", "md.")):
                model_url(term, qname.split(".", 1)[0])
                checked_terms += 1
            elif qname.startswith("cn."):
                require(
                    not ({"ttrUrl", "ttrStudioLink"} & term.get("extension", {}).keys()),
                    "CN demo stays in OM; obsolete Studio URL must be removed",
                )
        minimum = int(env.get("OM_MIN_ENTITIES", "40"))
        require(checked_terms >= minimum, f"{checked_terms} checked ER/MD term links < {minimum}")
        for metric in catalog.listing("metrics", "extension,tags"):
            if model_owned_metric(metric) and not any(
                t.get("tagFQN") == "Tatrman.Deprecated" for t in metric.get("tags") or []
            ):
                model_url(metric, "md")
        return "native Studio hyperlinks db/er/md; CN stays in OM; browser click remains manual"

    return [
        ("version", version),
        ("US inventory", lambda: inventory("hartland_us")),
        ("CZ inventory", lambda: inventory("hartland_cz")),
        ("Entities glossary", entities),
        ("metrics", metrics),
        ("table qname", qname),
        ("grounded table/column", grounded),
        ("term-to-asset link", link),
        ("Studio URL", url),
        ("second sync no-op", lambda: check_noop(env.get("KUBE_CONTEXT", "hartland"))),
    ]


def main():
    try:
        token = os.environ.get("OM_TOKEN", "")
        if not token and os.environ.get("OM_TOKEN_FILE"):
            token = Path(os.environ["OM_TOKEN_FILE"]).read_text()
        catalog = Catalog(os.environ.get("OM_URL", ""), token)
    except Exception:
        print("fail setup: supply a valid OM_URL and OM_TOKEN or readable OM_TOKEN_FILE")
        return 10
    failures = 0
    for name, check in checks(catalog, os.environ):
        try:
            print(f"pass {name}: {check()}")
        except CheckError as exc:
            print(f"fail {name}: {exc}")
            failures += 1
        except Exception:
            # Neither response bodies nor exception text can leak credentials into rig output.
            print(f"fail {name}: check did not pass")
            failures += 1
    print(f"{10 - failures}/10 passed")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
