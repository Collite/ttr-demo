#!/usr/bin/env bash
# Demo reset is an operator action. Default is a read-only plan; see --help.
set -euo pipefail
exec python3 -B "$(cd "$(dirname "$0")" && pwd)/reset_openmetadata.py" "$@"
