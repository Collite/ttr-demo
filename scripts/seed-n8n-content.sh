#!/usr/bin/env bash
# Private-file/vault password input only. No secret value in argv, environment or logs.
set +x
set -euo pipefail
umask 077
N8N_CONTENT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
N8N_CONTENT_ARGS=()
N8N_CONTENT_OWNER=""
N8N_CONTENT_PG=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --dir|--owner-password-file|--pg-ro-password-file|--webhook-key-file)
      [ "$#" -ge 2 ] || { echo 'ERROR: option requires a value' >&2; exit 2; }
      case "$1" in
        --owner-password-file) N8N_CONTENT_OWNER="$2" ;;
        --pg-ro-password-file) N8N_CONTENT_PG="$2" ;;
      esac
      N8N_CONTENT_ARGS+=("$1" "$2"); shift 2 ;;
    --verify) N8N_CONTENT_ARGS+=("$1"); shift ;;
    --help|-h) exec python3 -B "$N8N_CONTENT_DIR/seed_n8n_content.py" --help ;;
    *) echo 'ERROR: unknown option; use --help' >&2; exit 2 ;;
  esac
done
N8N_CONTENT_TMP="$(mktemp -d "${TMPDIR:-/tmp}/n8n-content.XXXXXXXX")"
trap 'rm -rf -- "$N8N_CONTENT_TMP"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
content_vault_read() {
  if ! az keyvault secret show --vault-name "${VAULT:-hartland}" --name "$1" --query value -o tsv > "$2" 2>/dev/null; then
    printf 'ERROR: could not read vault key %s\n' "$1" >&2
    exit 1
  fi
}
if [ -z "$N8N_CONTENT_OWNER" ]; then
  content_vault_read n8n-owner-password "$N8N_CONTENT_TMP/owner"
  N8N_CONTENT_ARGS+=(--owner-password-file "$N8N_CONTENT_TMP/owner")
fi
if [ -z "$N8N_CONTENT_PG" ]; then
  content_vault_read pg-hartland-cz-ro "$N8N_CONTENT_TMP/pg"
  N8N_CONTENT_ARGS+=(--pg-ro-password-file "$N8N_CONTENT_TMP/pg")
fi
python3 -B "$N8N_CONTENT_DIR/seed_n8n_content.py" "${N8N_CONTENT_ARGS[@]}"
