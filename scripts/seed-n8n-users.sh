#!/usr/bin/env bash
# Passwords are read from private files, never argv, environment variables, or logs.
set +x
set -euo pipefail
umask 077

N8N_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
N8N_ARGS=()
N8N_OWNER_FILE=""
N8N_MEMBER_FILE=""
N8N_MAILPIT=proxy
N8N_DRY_RUN=false
N8N_HELP=false
usage() {
  echo "usage: $0 [--owner USER] [--realm PATH] [--owner-password-file F] [--member-password-file F] [--mailpit proxy|URL|none] [--verify|--dry-run] [--reinvite]" >&2
  exit 2
}
while [ "$#" -gt 0 ]; do
  case "$1" in
    --owner|--realm|--owner-password-file|--member-password-file|--mailpit)
      [ "$#" -ge 2 ] || usage
      case "$1" in
        --owner-password-file) N8N_OWNER_FILE="$2" ;;
        --member-password-file) N8N_MEMBER_FILE="$2" ;;
        --mailpit) N8N_MAILPIT="$2" ;;
      esac
      N8N_ARGS+=("$1" "$2"); shift 2 ;;
    --dry-run) N8N_DRY_RUN=true; N8N_ARGS+=("$1"); shift ;;
    --help|-h) N8N_HELP=true; N8N_ARGS+=("$1"); shift ;;
    --verify|--reinvite) N8N_ARGS+=("$1"); shift ;;
    *) usage ;;
  esac
done

if "$N8N_DRY_RUN" || "$N8N_HELP"; then
  exec python3 -B "$N8N_SCRIPT_DIR/seed_n8n_users.py" "${N8N_ARGS[@]}"
fi

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
if [ -z "$N8N_OWNER_FILE" ]; then
  vault_read n8n-owner-password "$N8N_SEED_TMP/owner"
  N8N_ARGS+=(--owner-password-file "$N8N_SEED_TMP/owner")
fi
if [ "$N8N_MAILPIT" != none ] && [ -z "$N8N_MEMBER_FILE" ]; then
  vault_read n8n-member-password "$N8N_SEED_TMP/member"
  N8N_ARGS+=(--member-password-file "$N8N_SEED_TMP/member")
fi
python3 -B "$N8N_SCRIPT_DIR/seed_n8n_users.py" "${N8N_ARGS[@]}"
