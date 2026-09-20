#!/usr/bin/env bash
# Lấy chatId và sinh gateway token. Chạy một lần khi cắm bot mới.
#
#   bash ops/setup-bot.sh
#
# Token bot được lưu vào ops/.env — file này bị .gitignore chặn và chmod 600,
# nên nó KHÔNG nằm trong repo (F2). Poller cần nó để gọi Telegram.

set -euo pipefail
cd "$(dirname "$0")/.."
ENV_FILE="ops/.env"

command -v curl >/dev/null || { echo "Cần curl. cài: sudo apt install curl"; exit 1; }
command -v python3 >/dev/null || { echo "Cần python3."; exit 1; }

echo "════════════════════════════════════════════════════════"
echo " Cắm bot Telegram cho companySpec"
echo "════════════════════════════════════════════════════════"
echo
echo "Chưa có bot? Nhắn @BotFather trên Telegram:  /newbot"
echo "Nó trả về token dạng  1234567890:AAF-xxxxxxxxxxxxxxxxxxxx"
echo

# -s: không hiện ra màn hình, không vào history
read -rsp "Dán token bot vào đây (gõ xong bấm Enter): " BOT_TOKEN
echo; echo

API="https://api.telegram.org/bot${BOT_TOKEN}"

echo "→ Kiểm tra token…"
ME=$(curl -sS --max-time 15 "${API}/getMe") || { echo "Không gọi được Telegram."; exit 1; }
if ! python3 -c "import json,sys; sys.exit(0 if json.loads(sys.argv[1]).get('ok') else 1)" "$ME"; then
  echo "Token sai hoặc bot đã bị xoá."
  echo "$ME" | head -c 200; echo
  exit 1
fi
USERNAME=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['result']['username'])" "$ME")
echo "  bot hợp lệ: @${USERNAME}"
echo

echo "→ Giờ mở Telegram, tìm @${USERNAME} và nhắn cho nó MỘT câu bất kỳ."
read -rp "  Nhắn xong thì bấm Enter… "
echo

echo "→ Đang tìm chatId…"
UPD=$(curl -sS --max-time 15 "${API}/getUpdates")
CHAT_ID=$(python3 - "$UPD" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
ids = []
for u in data.get("result", []):
    msg = u.get("message") or u.get("edited_message") or {}
    chat = msg.get("chat") or {}
    if chat.get("type") == "private" and chat.get("id") not in ids:
        ids.append(chat["id"])
print(ids[-1] if ids else "")
PY
)

if [ -z "$CHAT_ID" ]; then
  echo "  Chưa thấy tin nhắn nào."
  echo "  Thử lại: nhắn cho @${USERNAME} rồi chạy lại script này."
  echo "  (Nếu bot từng chạy webhook, gỡ trước:  curl -s \"\${API}/deleteWebhook\")"
  exit 1
fi
echo "  chatId của cậu: ${CHAT_ID}"
echo

if [ -f "$ENV_FILE" ] && grep -q COMPANYSPEC_GATEWAY_TOKEN "$ENV_FILE" 2>/dev/null; then
  GW=$(grep COMPANYSPEC_GATEWAY_TOKEN "$ENV_FILE" | cut -d= -f2-)
  echo "→ Giữ nguyên gateway token cũ."
else
  GW=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
  echo "→ Sinh gateway token mới."
fi

cat > "$ENV_FILE" <<EOF
# Sinh bởi ops/setup-bot.sh — KHÔNG commit (.gitignore đã chặn, chmod 600).
TELEGRAM_BOT_TOKEN=${BOT_TOKEN}
COMPANYSPEC_ADMIN_CHAT_ID=${CHAT_ID}
COMPANYSPEC_GATEWAY_TOKEN=${GW}
EOF
chmod 600 "$ENV_FILE"

unset BOT_TOKEN

echo "  đã ghi ${ENV_FILE} (chmod 600)"
echo
echo "════════════════════════════════════════════════════════"
echo " Xong. Chạy hệ:"
echo
echo "   set -a && source ops/.env && set +a && python3 gateway/telegram/poller.py"
echo
echo " Rồi nhắn cho @${USERNAME} trên Telegram."
echo
echo " Chạy nền vĩnh viễn:"
echo "   cp ops/companyspec-session.service ~/.config/systemd/user/"
echo "   systemctl --user daemon-reload"
echo "   systemctl --user enable --now companyspec-gateway"
echo "════════════════════════════════════════════════════════"
