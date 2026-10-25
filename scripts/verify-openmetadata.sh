#!/usr/bin/env bash
# XM-P3 S3.2: read-only catalog and completed-Job checks. Token stays in the environment.
set -euo pipefail
exec python3 -B "$(cd "$(dirname "$0")" && pwd)/verify_openmetadata.py" "$@"
