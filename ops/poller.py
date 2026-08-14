#!/usr/bin/env python3
"""Nhận tin Telegram bằng long polling — cửa vào thật của hệ.

VÌ SAO KHÔNG DÙNG WEBHOOK: Telegram chỉ gọi được vào URL công khai có HTTPS.
Máy này nằm sau NAT, không có IP công khai. Muốn webhook thì phải mở một cửa
từ internet vào máy — cái giá quá đắt cho một trợ lý giữ dữ liệu riêng.

Polling thì ngược lại: máy tự hỏi Telegram, không ai gọi vào được. Không mở
cổng, không qua bên thứ ba.

Việc định kỳ (§12c scheduledTrigger) chạy bằng systemd timer, cũng theo hướng
từ trong ra — không cần ai gọi vào.

    set -a && source ops/.env && set +a && python3 ops/poller.py
"""
import fcntl
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import telegram  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import db  # noqa: E402

GATEWAY = os.path.join(ROOT, "ops", "gateway.py")
CEO_STORE = os.path.join(ROOT, "ceo", "store.sqlite")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN = os.environ.get("COMPANYSPEC_ADMIN_CHAT_ID", "")
API = f"https://api.telegram.org/bot{TOKEN}"
POLL_TIMEOUT = 30


def log(*parts):
    print("[poller]", *parts, file=sys.stderr, flush=True)


def claim_singleton():
    """Chỉ cho phép MỘT poller sống.

    Hai tiến trình cùng gọi getUpdates trên một bot thì Telegram giao mỗi tin
    cho đúng một bên — tin nhắn rơi ngẫu nhiên, admin thấy lúc được lúc không.
    Rất khó đoán ra nếu không biết trước. Khoá file nên tự nhả khi tiến trình
    chết, không cần dọn tay.
    """
    lock_path = os.path.join(ROOT, "ops", ".poller.lock")
    fh = open(lock_path, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("đã có một poller khác đang chạy — thoát.")
        log("  xem cái nào:  pgrep -af ops/poller.py")
        log("  dừng bản systemd:  systemctl --user stop companyspec-gateway")
        sys.exit(1)
    fh.write(str(os.getpid()))
    fh.flush()
    return fh  # giữ tham chiếu, đóng file là mất khoá


def call(method: str, payload: dict, timeout: int = 60):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{API}/{method}", data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        log(f"{method} lỗi {exc.code}: {body}")
        return {"ok": False, "error": body}
    except Exception as exc:
        log(f"{method} lỗi: {type(exc).__name__}: {exc}")
        return {"ok": False, "error": str(exc)}


def remember_bot_message(message_id: int, thread_id):
    """R1 — nhớ tin nào của bot thuộc thread nào, để admin bấm Reply là nối đúng."""
    if not thread_id or not message_id:
        return
    conn = db.connect(CEO_STORE)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS botMessage (messageId INTEGER PRIMARY KEY, "
        "threadId INTEGER NOT NULL, sentAt TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT OR REPLACE INTO botMessage (messageId, threadId, sentAt) "
        "VALUES (?,?,datetime('now'))", (message_id, thread_id),
    )
    conn.commit()
    conn.close()


def run_gateway(update: dict) -> list:
    """Gateway là tiến trình riêng — hỏng thì chỉ hỏng một lượt, không sập poller."""
    try:
        proc = subprocess.run(
            [sys.executable, GATEWAY, "handle"],
            input=json.dumps(update, ensure_ascii=False),
            capture_output=True, text=True, cwd=ROOT, timeout=900,
        )
    except subprocess.TimeoutExpired:
        return [{"kind": "sendMessage", "chatId": ADMIN,
                 "text": "Quá 15 phút chưa xong, em dừng lại rồi.",
                 "replyMarkupJson": '{"inline_keyboard": []}'}]
    if proc.returncode != 0:
        log("gateway lỗi:", proc.stderr.strip()[:300])
        return [{"kind": "sendMessage", "chatId": ADMIN,
                 "text": "Hệ gặp lỗi khi xử lý. Xem log để biết chi tiết.",
                 "replyMarkupJson": '{"inline_keyboard": []}'}]
    try:
        return json.loads(proc.stdout).get("actions", [])
    except json.JSONDecodeError:
        log("gateway trả về không phải JSON:", proc.stdout[:200])
        return []


def do_actions(actions: list):
    for act in actions:
        kind = act.get("kind")

        if kind == "sendMessage":
            # gateway đã thoát HTML rồi, đừng thoát hai lần
            res = telegram.send_message(act["chatId"], act["text"],
                                        act.get("replyMarkupJson"),
                                        already_escaped=True)
            if res.get("ok"):
                remember_bot_message(res["result"]["message_id"], act.get("threadId"))

        elif kind == "answerCallback":
            telegram.answer_callback(act["callbackId"], act.get("text", ""))

        elif kind == "log":
            log(act.get("level", "info"), act.get("text", ""))

        else:
            log("action lạ:", kind)


def main() -> int:
    if not TOKEN:
        log("Thiếu TELEGRAM_BOT_TOKEN trong ops/.env — chạy lại: bash ops/setup-bot.sh")
        return 1
    if not ADMIN:
        log("Thiếu COMPANYSPEC_ADMIN_CHAT_ID (F6).")
        return 1

    _lock = claim_singleton()  # noqa: F841 — giữ khoá suốt vòng đời tiến trình

    me = call("getMe", {}, timeout=15)
    if not me.get("ok"):
        log("Token không dùng được.")
        return 1
    log(f"đã kết nối: @{me['result']['username']}  ·  chỉ nghe chat {ADMIN}")

    # Webhook và polling loại trừ nhau. Gỡ webhook cũ nếu có.
    call("deleteWebhook", {"drop_pending_updates": False}, timeout=15)

    # Bỏ qua tin nhắn tồn đọng từ trước khi khởi động — tránh trả lời tin cũ.
    init = call("getUpdates", {"limit": 1, "offset": -1, "timeout": 0}, timeout=20)
    offset = 0
    if init.get("ok") and init.get("result"):
        offset = init["result"][-1]["update_id"] + 1
    log("sẵn sàng, đang chờ tin nhắn…")

    backoff = 1
    while True:
        res = call("getUpdates", {"offset": offset, "timeout": POLL_TIMEOUT},
                   timeout=POLL_TIMEOUT + 15)
        if not res.get("ok"):
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            continue
        backoff = 1

        for upd in res.get("result", []):
            offset = upd["update_id"] + 1
            msg = upd.get("message") or upd.get("callback_query", {}).get("message") or {}
            chat_id = (msg.get("chat") or {}).get("id")

            # Lớp chặn thứ nhất; gateway còn chặn lần nữa (T1).
            if str(chat_id) != str(ADMIN):
                log(f"bỏ qua chatId lạ {chat_id}")
                continue

            if "message" in upd:
                # cho admin biết hệ đang làm, vì CEO có thể chạy vài chục giây
                telegram.chat_action(chat_id)

            do_actions(run_gateway(upd))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("dừng.")
