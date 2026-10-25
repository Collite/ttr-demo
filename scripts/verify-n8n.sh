#!/usr/bin/env bash
# N8 verification: P2 authenticates personas; P3 also sends a small authenticated echo request.
set -euo pipefail
exec python3 -B "$(cd "$(dirname "$0")" && pwd)/verify_n8n_lib.py" "$@"
