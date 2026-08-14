#!/usr/bin/env python3
"""Đường ra Telegram duy nhất của hệ.

T1 — một cửa ra. Poller và scheduler đều gọi qua đây, không ai tự dựng lời gọi
API riêng. Hai chỗ gửi tin là hai chỗ phải nhớ thoát HTML, cắt 4096 ký tự, và
xử lý lỗi — sớm muộn cũng lệch nhau.
"""
import json
import os
import sys
import urllib.error
import urllib.request

MAX_LEN = 4096


def _api(method: str) -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("Thiếu TELEGRAM_BOT_TOKEN")
    return f"https://api.telegram.org/bot{token}/{method}"


def call(method: str, payload: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        _api(method), data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        print(f"[telegram] {method} lỗi {exc.code}: {body}", file=sys.stderr)
        return {"ok": False, "error": body}
    except Exception as exc:
        print(f"[telegram] {method} lỗi: {type(exc).__name__}: {exc}", file=sys.stderr)
        return {"ok": False, "error": str(exc)}


def esc(text: str) -> str:
    """parse_mode là bắt buộc, và Markdown cũ vỡ với tiếng Việt. Dùng HTML,
    thoát sạch: không định dạng, nhưng không bao giờ vỡ."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send_message(chat_id, text: str, reply_markup_json: str | None = None,
                 already_escaped: bool = False) -> dict:
    payload = {
        "chat_id": chat_id,
        "text": (text if already_escaped else esc(text))[:MAX_LEN],
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup_json and reply_markup_json != '{"inline_keyboard": []}':
        payload["reply_markup"] = reply_markup_json

    res = call("sendMessage", payload)
    if not res.get("ok"):
        # Thường là HTML hỏng. Gửi lại dạng thô để admin vẫn đọc được nội dung.
        payload.pop("parse_mode", None)
        res = call("sendMessage", payload)
    return res


def answer_callback(callback_id: str, text: str = "") -> dict:
    return call("answerCallbackQuery",
                {"callback_query_id": callback_id, "text": text[:200]})


def chat_action(chat_id, action: str = "typing") -> dict:
    return call("sendChatAction", {"chat_id": chat_id, "action": action}, timeout=15)
