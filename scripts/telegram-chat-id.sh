#!/usr/bin/env bash
# Which chats has a Telegram bot seen? Read-only: the bot's identity, its webhook state, and the chats in getUpdates.
#
#   scripts/telegram-chat-id.sh hebe-marketa-telegram-token     # (`just hebe-telegram-chat-id`) from a machine logged into az
#
# The token is a vault secret (B-4.2). It goes vault -> a 0600 file -> a curl config file (-K), so it never reaches
# argv, the shell history or the output. getUpdates without an offset confirms nothing, so the script can be re-run.
# In a private chat the chat id equals the sender's user id; that number goes into Hebe's
# [channels.telegram] chat_user_map (a chat id is not a secret).
#
# While Hebe runs with the Telegram channel on it long-polls the bot, and Telegram answers this script's getUpdates
# with 409: read the chat id from Hebe's log line `ignored message from unmapped chat <id>` instead.
set -euo pipefail
VAULT="${VAULT:-hartland}"
NAME="${1:?usage: $0 <vault secret holding the bot token>}"
command -v az >/dev/null 2>&1 || { echo "az CLI not found" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "jq not found" >&2; exit 1; }
umask 077
D=$(mktemp -d "${TMPDIR:-/tmp}/tg.XXXXXX")
trap 'rm -rf "$D"' EXIT
az keyvault secret show --vault-name "$VAULT" --name "$NAME" --query value -o tsv > "$D/token" 2>"$D/az.err" \
  || { echo "az: could not read '$NAME' from vault '$VAULT':"; sed 's/^/  /' "$D/az.err"; exit 1; }
tok=$(<"$D/token")
if [[ "$tok" =~ ^[0-9]+:[A-Za-z0-9_-]{30,}$ ]]; then echo "token shape: ok (${#tok} chars, bot id ${tok%%:*})"
else echo "token shape: UNEXPECTED (${#tok} chars; whitespace=$([[ "$tok" =~ [[:space:]] ]] && echo yes || echo no))"; fi
call() {  # call <method> -> body in $D/out, prints the HTTP code
  printf 'url = "https://api.telegram.org/bot%s/%s"\n' "$tok" "$1" > "$D/cfg"
  curl -sS -K "$D/cfg" -o "$D/out" -w '%{http_code}' --max-time 20
}
echo "--- getMe: HTTP $(call getMe)"
jq -c '{ok, description, bot: (.result | {username, first_name, can_join_groups, can_read_all_group_messages})}' "$D/out"
echo "--- getWebhookInfo: HTTP $(call getWebhookInfo)"
jq -c '{ok, webhook_set: ((.result.url // "") != ""), pending_update_count: .result.pending_update_count, last_error_message: .result.last_error_message}' "$D/out"
echo "--- getUpdates: HTTP $(call getUpdates)"
jq -c '{ok, description, count: (.result | length? // null)}' "$D/out"
jq -r '.result[]? | (.message // .edited_message // .my_chat_member // .channel_post) as $m
  | "update \(.update_id): chat.id=\($m.chat.id) type=\($m.chat.type) from=@\($m.from.username // "-") (\($m.from.first_name // "-")) text=\(($m.text // "-")[0:40] | @json)"' "$D/out"
case "$(jq -r 'if .ok then (if (.result|length)==0 then "empty" else "some" end) else (.error_code|tostring) end' "$D/out")" in
  empty) echo "hint: no updates queued. Send the bot a message in its private chat (press Start first) from the stage phone, then re-run." ;;
  401)   echo "hint: Telegram rejects this token: the vault value is not the token BotFather gave (or it was revoked)." ;;
  409)   echo "hint: another client is reading this bot (Hebe's long polling, or a webhook). With Hebe running, read the chat id from its log: 'ignored message from unmapped chat <id>'." ;;
  some)  echo "hint: in a private chat chat.id equals the sender's user id; that number goes into chat_user_map." ;;
esac
