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
# Chừa chỗ để lùi điểm cắt về ranh giới đọc được mà vẫn không chạm trần API.
AN_TOAN = 3800


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


def _lui_khoi_entity(s: str) -> str:
    """Không bao giờ cắt giữa một thực thể HTML.

    Chuỗi vào đây đã thoát HTML rồi, nên `&` mở đầu `&amp;` `&lt;` `&gt;`. Cắt
    đúng giữa nó thì Telegram từ chối cả tin vì parse_mode=HTML — và cách hỏng
    đó phụ thuộc vào việc admin có gõ dấu `&` ở đúng khoảng ký tự thứ 3800 hay
    không, tức là hỏng ngẫu nhiên, không ai tra ra được.
    """
    amp = s.rfind("&")
    if amp != -1 and ";" not in s[amp:]:
        return s[:amp]
    return s


def chia_doan(text: str, gioi_han: int = AN_TOAN) -> list:
    """Chia câu trả lời dài thành nhiều tin, cắt ở chỗ đọc được.

    VÌ SAO KHÔNG CẮT CỤT: bản trước làm `text[:MAX_LEN]` — câu trả lời dài hơn
    4096 ký tự bị mất phần đuôi, LẶNG LẼ. Admin đọc hết tin nhắn mà không biết
    còn phần nữa; hệ cũng không biết vì API vẫn trả về ok. Đo được hai lần
    trong lịch sử chat.

    Thứ tự ưu tiên khi tìm chỗ cắt: hết đoạn văn → hết dòng → hết từ. Cắt giữa
    từ chỉ dùng khi không còn lựa chọn (một khối chữ dài không có khoảng trắng,
    ví dụ một đường dẫn hoặc một chuỗi mã).
    """
    phan, con = [], text
    while len(con) > gioi_han:
        cua_so = con[:gioi_han]
        cat = max(cua_so.rfind("\n\n"), cua_so.rfind("\n"))
        if cat < gioi_han // 2:
            cat = cua_so.rfind(" ")
        if cat < gioi_han // 2:
            cat = gioi_han
        doan = _lui_khoi_entity(con[:cat])
        # Không tiến được thì cắt cứng — thà xấu còn hơn lặp vô hạn. Vẫn thử
        # lùi khỏi entity một lần nữa: nhánh này chỉ chạy khi cả đoạn là một
        # khối liền không khoảng trắng, và ở đó vẫn có thể có `&amp;`.
        if not doan.strip():
            doan = _lui_khoi_entity(con[:gioi_han]) or con[:gioi_han]
        phan.append(doan.rstrip())
        con = con[len(doan):].lstrip("\n")
    if con.strip():
        phan.append(con)
    return phan or [text[:gioi_han]]


def send_message(chat_id, text: str, reply_markup_json: str | None = None,
                 already_escaped: bool = False) -> dict:
    """Gửi một câu trả lời, chia nhiều tin nếu dài.

    Bàn phím duyệt chỉ gắn vào tin CUỐI: nút phải nằm dưới chỗ admin đọc xong,
    không phải giữa chừng.
    """
    noi_dung = text if already_escaped else esc(text)
    cac_phan = chia_doan(noi_dung)

    res = {"ok": False, "error": "không có nội dung để gửi"}
    for i, phan in enumerate(cac_phan):
        cuoi = i == len(cac_phan) - 1
        payload = {
            "chat_id": chat_id,
            "text": phan[:MAX_LEN],
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if cuoi and reply_markup_json and reply_markup_json != '{"inline_keyboard": []}':
            payload["reply_markup"] = reply_markup_json

        res = call("sendMessage", payload)
        if not res.get("ok"):
            # Thường là HTML hỏng. Gửi lại dạng thô để admin vẫn đọc được nội dung.
            payload.pop("parse_mode", None)
            res = call("sendMessage", payload)
        # O10 — một phần gãy thì DỪNG và báo. Gửi nốt phần sau sẽ cho admin một
        # câu trả lời thủng ở giữa mà trông vẫn liền mạch.
        if not res.get("ok"):
            print(f"[telegram] gãy ở phần {i + 1}/{len(cac_phan)} — dừng gửi.",
                  file=sys.stderr)
            return res
    return res


def send_document(chat_id, ten_tep: str, noi_dung: bytes, chu_thich: str = "",
                  loai: str = "text/html") -> dict:
    """Gửi một TỆP (trang HTML xem thay đổi…). Cùng cửa ra T1 với tin nhắn.

    Tin nhắn Telegram trần 4096 ký tự và không tô màu được — không đủ để admin
    "xem trực tiếp" một thay đổi mã (26/09). Một trang HTML gửi kèm thì bấm là
    mở trên điện thoại. Dựng multipart bằng tay: không thêm thư viện nào.
    """
    ranh = "----companySpec" + os.urandom(8).hex()
    phan = []
    for ten, gia in (("chat_id", str(chat_id)), ("caption", chu_thich[:1000])):
        phan.append(f"--{ranh}\r\nContent-Disposition: form-data; name=\"{ten}\"\r\n\r\n"
                    f"{gia}\r\n".encode())
    phan.append(f"--{ranh}\r\nContent-Disposition: form-data; name=\"document\"; "
                f"filename=\"{ten_tep}\"\r\nContent-Type: {loai}\r\n\r\n".encode()
                + noi_dung + b"\r\n")
    phan.append(f"--{ranh}--\r\n".encode())
    req = urllib.request.Request(
        _api("sendDocument"), data=b"".join(phan),
        headers={"Content-Type": f"multipart/form-data; boundary={ranh}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        print(f"[telegram] sendDocument lỗi {exc.code}: {body}", file=sys.stderr)
        return {"ok": False, "error": body}
    except Exception as exc:
        print(f"[telegram] sendDocument lỗi: {type(exc).__name__}: {exc}", file=sys.stderr)
        return {"ok": False, "error": str(exc)}


def answer_callback(callback_id: str, text: str = "") -> dict:
    return call("answerCallbackQuery",
                {"callback_query_id": callback_id, "text": text[:200]})


def chat_action(chat_id, action: str = "typing") -> dict:
    return call("sendChatAction", {"chat_id": chat_id, "action": action}, timeout=15)
