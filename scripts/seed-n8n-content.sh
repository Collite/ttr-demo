#!/usr/bin/env bash
# Private-file/vault password input only. No secret value in argv, environment or logs.
set +x
set -euo pipefail
umask 077
N8N_CONTENT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
N8N_CONTENT_ARGS=()
N8N_CONTENT_OWNER=""
N8N_CONTENT_PG=""
N8N_CONTENT_VERIFY=false
N8N_CONTENT_WORKFLOWS="$N8N_CONTENT_DIR/../n8n/demo"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --dir|--owner-password-file|--pg-ro-password-file|--webhook-key-file)
      [ "$#" -ge 2 ] || { echo 'ERROR: option requires a value' >&2; exit 2; }
      case "$1" in
        --dir) N8N_CONTENT_WORKFLOWS="$2" ;;
        --owner-password-file) N8N_CONTENT_OWNER="$2" ;;
        --pg-ro-password-file) N8N_CONTENT_PG="$2" ;;
      esac
      N8N_CONTENT_ARGS+=("$1" "$2"); shift 2 ;;
    --verify) N8N_CONTENT_VERIFY=true; N8N_CONTENT_ARGS+=("$1"); shift ;;
    --help|-h) exec python3 -B "$N8N_CONTENT_DIR/seed_n8n_content.py" --help ;;
    *) echo 'ERROR: unknown option; use --help' >&2; exit 2 ;;
  esac
done
# Validate documents before vault reads; only referenced credentials need input.
N8N_CONTENT_REQUIRED="$(python3 -B "$N8N_CONTENT_DIR/seed_n8n_content.py" --dir "$N8N_CONTENT_WORKFLOWS" --list-required-credentials)"
# Keep this private-temp/vault block identical to seed-n8n-users.sh.
N8N_SEED_TMP="$(mktemp -d "${TMPDIR:-/tmp}/n8n-seed.XXXXXXXX")"
trap 'rm -rf -- "$N8N_SEED_TMP"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
vault_read() {
  # Suppress az's error stream: extensions and debug settings can echo a response.
  if ! az keyvault secret show --vault-name "${VAULT:-hartland}" --name "$1" --query value -o tsv > "$2" 2>/dev/null; then
    printf 'ERROR: could not read vault key %s\n' "$1" >&2
    exit 1
  fi
}
if [ -z "$N8N_CONTENT_OWNER" ]; then
  vault_read n8n-owner-password "$N8N_SEED_TMP/owner"
  N8N_CONTENT_ARGS+=(--owner-password-file "$N8N_SEED_TMP/owner")
fi
if ! "$N8N_CONTENT_VERIFY" && [ -z "$N8N_CONTENT_PG" ] && [[ $'\n'"$N8N_CONTENT_REQUIRED"$'\n' == *$'\n'hartland-cz-pg$'\n'* ]]; then
  vault_read pg-hartland-cz-ro "$N8N_SEED_TMP/pg"
  N8N_CONTENT_ARGS+=(--pg-ro-password-file "$N8N_SEED_TMP/pg")
fi
python3 -B "$N8N_CONTENT_DIR/seed_n8n_content.py" "${N8N_CONTENT_ARGS[@]}"
