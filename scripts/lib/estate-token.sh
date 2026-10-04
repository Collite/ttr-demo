# IE-P3·S3.3 — how a drill gets a bearer. Sourced, never executed.
#
# ## Why this exists
#
# Both drills (`investment-dod`, `report-fingerprint`) ask studio-bff questions, and studio-bff wants a
# token the realm issued for the `studio` audience. Until S3.3 that meant a person copying one out of a
# browser — and a copied token is a **five-minute artifact**: the realm sets no lifespans, so Keycloak's
# default applies. Two of the three S3.0·T7 attempts died `401 AUTH_INVALID_JWT` on a bearer whose shape
# and audience were right and whose `exp` had passed. The `studio` client cannot help: it is public,
# with no direct grant and no service account, so nothing can mint from a script.
#
# So the realm grew `estate-drill` (olymp `platform/auth/keycloak/overlays/hartland/realm/kantheon.json`):
# a confidential service account audienced at `studio` ONLY — it can ask the BFF questions and cannot
# write through entry-substrate. Its secret is the authority to MINT, and unlike a token it does not
# expire.
#
# ## Use
#
#   . "$(dirname "$0")/lib/estate-token.sh"
#   BEARER="$(estate_token IE_DOD)"        # reads IE_DOD_BEARER or IE_DOD_OIDC_*
#
# `<PREFIX>_BEARER`             a token, used verbatim — a person's, which is what the WRITE drills
#                               still take (a service account that can write to an append-only ledger
#                               from a script is a decision, not a convenience).
# `<PREFIX>_BEARER_FILE`        a file whose first line is that token — a pipe (`…_BEARER_FILE=/dev/fd/3
#                               … 3< <(…)`), so a person's token is in neither the environment nor a file.
# `<PREFIX>_OIDC_TOKEN_URL`     the realm's token endpoint.
# `<PREFIX>_OIDC_CLIENT_ID`     `estate-drill`.
# `<PREFIX>_OIDC_CLIENT_SECRET` from the `estate-drill-oidc` Secret (key ESTATE_DRILL_CLIENT_SECRET).
#
# ⛔ Neither the secret nor the token is ever printed — not on success, not in an error. A failed grant
# is reported by Keycloak's own `error` field, which names the cause (`invalid_client`,
# `unauthorized_client`) without quoting anything secret.

estate_token() {
    local prefix="$1"
    local bearer_var="${prefix}_BEARER"
    local url_var="${prefix}_OIDC_TOKEN_URL"
    local id_var="${prefix}_OIDC_CLIENT_ID"
    local secret_var="${prefix}_OIDC_CLIENT_SECRET"
    local file_var="${prefix}_BEARER_FILE"
    local bearer="${!bearer_var:-}" url="${!url_var:-}" client="${!id_var:-}" secret="${!secret_var:-}"

    if [ -z "$bearer" ] && [ -n "${!file_var:-}" ]; then
        # `/dev/fd/N` is read from the descriptor itself: on Linux, OPENING /dev/fd/N fails (ENXIO) when N is a socket
        if [[ "${!file_var}" =~ ^/dev/fd/([0-9]+)$ ]]; then
            IFS= read -r -u "${BASH_REMATCH[1]}" bearer || true
        else
            IFS= read -r bearer <"${!file_var}" || true
        fi
    fi
    if [ -n "$bearer" ]; then
        printf '%s' "$bearer"
        return 0
    fi
    if [ -z "$url" ] || [ -z "$client" ] || [ -z "$secret" ]; then
        printf 'no bearer: set %s, or all three of %s / %s / %s (the `estate-drill` service account)\n' \
            "$bearer_var" "$url_var" "$id_var" "$secret_var" >&2
        return 1
    fi

    local body http token error
    body="$(mktemp)"
    http="$(curl -sS -o "$body" -w '%{http_code}' -X POST "$url" \
        -H 'content-type: application/x-www-form-urlencoded' \
        --data-urlencode 'grant_type=client_credentials' \
        --data-urlencode "client_id=$client" \
        --data-urlencode "client_secret=$secret" 2>/dev/null || true)"
    token="$(jq -r '.access_token // empty' <"$body" 2>/dev/null || true)"
    error="$(jq -r '[.error, .error_description] | map(select(. != null)) | join(": ") // empty' <"$body" 2>/dev/null || true)"
    rm -f "$body"

    if [ -z "$token" ]; then
        # ⚑ The body is NOT echoed — a token endpoint's answer can carry one. Keycloak's `error` names
        # the cause on its own: `invalid_client` = wrong or unseeded secret; `unauthorized_client` =
        # service accounts are off for this client.
        printf 'minting a token as `%s` failed (HTTP %s)%s\n' "$client" "${http:-000}" \
            "${error:+ — $error}" >&2
        return 1
    fi
    printf '%s' "$token"
}
