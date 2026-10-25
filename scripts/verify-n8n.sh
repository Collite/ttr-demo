#!/usr/bin/env bash
# N8 — read-only checks; --phase 2 authenticates via private-file/vault credentials.
set -euo pipefail
exec python3 -B "$(cd "$(dirname "$0")" && pwd)/verify_n8n_lib.py" "$@"
