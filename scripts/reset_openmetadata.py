"""Plan/reset only Hartland's two projected glossaries and six authored metrics."""

import argparse
import os
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, build_opener

from verify_openmetadata import Catalog, NoRedirect, require

MEASURES = {"revenue", "quantity", "orderCount", "lineCount", "returnAmount", "onHandQty"}


def targets(catalog):
    result = []
    for item in catalog.listing("glossaries", ""):
        if item["name"] in {"hartland Entities", "hartland Concepts"}:
            result.append(("glossaries", item["id"], item["name"]))
    for item in catalog.listing("metrics", "extension"):
        qname = item.get("extension", {}).get("ttrQname", "")
        if item["name"] in MEASURES and qname == "md.measure." + item["name"]:
            result.append(("metrics", item["id"], item["name"]))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute", action="store_true", help="delete listed demo projections; otherwise read-only"
    )
    args = parser.parse_args()
    require(
        os.environ.get("OM_URL", "").rstrip("/")
        in {
            "https://openmetadata.hartland.collite.cz",
            "https://openmetadata.hartland.collite.cz/api",
        },
        "reset only targets the Hartland catalog",
    )
    token = os.environ.get("OM_TOKEN", "")
    if not token and os.environ.get("OM_TOKEN_FILE"):
        token = Path(os.environ["OM_TOKEN_FILE"]).read_text()
    catalog = Catalog(os.environ["OM_URL"], token)
    require(catalog.get("users/loggedInUser").get("isAdmin") is True, "reset requires an admin JWT")
    planned = targets(catalog)
    for resource, _, name in planned:
        print(f"{'delete' if args.execute else 'would delete'} {resource}: {name}")
    if args.execute:
        for resource, identity, _ in planned:
            request = Request(
                catalog.base
                + "/v1/"
                + resource
                + "/"
                + quote(identity, safe="")
                + "?recursive=true&hardDelete=true",
                method="DELETE",
                headers={"Authorization": "Bearer " + catalog.token},
            )
            with build_opener(NoRedirect()).open(request, timeout=30) as response:
                require(response.status in (200, 204), "reset delete failed")
        print(
            "Run a fresh-state projection Job as documented; "
            "the saved URL ETag must not skip rebuilding."
        )
    else:
        print(
            "Read-only plan. Bora can rerun with --execute; "
            "scanned tables and projection state are retained."
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit("reset failed; credentials and response bodies omitted") from None
