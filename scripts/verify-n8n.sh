#!/usr/bin/env bash
# N8-P1 S1.2 — read-only checks; no owner setup, sign-in or secret retrieval.
set -euo pipefail
exec python3 -B "$(cd "$(dirname "$0")" && pwd)/verify_n8n_lib.py" "$@"
