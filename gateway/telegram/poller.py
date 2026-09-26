#!/usr/bin/env python3
"""Nhận tin Telegram bằng long polling — cửa vào thật của hệ.

VÌ SAO KHÔNG DÙNG WEBHOOK: Telegram chỉ gọi được vào URL công khai có HTTPS.
Máy này nằm sau NAT, không có IP công khai. Muốn webhook thì phải mở một cửa
từ internet vào máy — cái giá quá đắt cho một trợ lý giữ dữ liệu riêng.

Polling thì ngược lại: máy tự hỏi Telegram, không ai gọi vào được. Không mở
cổng, không qua bên thứ ba.

Việc định kỳ (§12c scheduledTrigger) chạy bằng systemd timer, cũng theo hướng
từ trong ra — không cần ai gọi vào.

    set -a && source ops/.env && set +a && python3 gateway/telegram/poller.py
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

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import db  # noqa: E402

# ⚠ `session.py`, KHÔNG phải `gateway.py`. Module ấy đổi tên vì có một GÓI tên
# `gateway/` rồi — nhưng lần đổi tên §36 (commit 75b8958) đổi luôn cả đường dẫn
# ở đây thành `gateway/telegram/gateway.py`, một file CHƯA TỪNG tồn tại.
#
# Hậu quả: mọi tin nhắn của admin đều ra "Hệ gặp lỗi khi xử lý". Không ai phát
# hiện suốt từ lúc đổi tên vì admin chưa nhắn lần nào sau đó — journal có ĐÚNG
# 0 dòng `gateway lỗi`. Cửa vào không sập (O8 giữ đúng), nó chỉ luôn luôn từ
# chối, và đó là kiểu hỏng khó thấy hơn.
GATEWAY = os.path.join(ROOT, "gateway", "telegram", "session.py")
CEO_STORE = os.path.join(ROOT, "ceo", "store.sqlite")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN = os.environ.get("COMPANYSPEC_ADMIN_CHAT_ID", "")
API = f"https://api.telegram.org/bot{TOKEN}"
POLL_TIMEOUT = 30
# Tin gửi trong ngần này phút trước lúc khởi động thì VẪN trả lời. Đủ rộng để
# ôm trọn một lần khởi động lại (mất khoảng 15 giây), đủ hẹp để sau một đêm
# poller chết thì không thức dậy trả lời hàng loạt tin từ hôm qua.
NHAN_LAI_PHUT = 10


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
        log("  xem cái nào:  pgrep -af gateway/telegram/poller.py")
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


# ───────────────────────── thực đơn /tay ─────────────────────────
#
# "/tay …" đi THẲNG tới company, KHÔNG đánh thức CEO. Ba lẽ, xếp theo sức nặng:
#
# · Rẻ. Một phiên CEO tốn hạn mức gói Pro — thứ đang là nút thắt của cả hệ.
#   Hỏi "xưởng đang làm gì" mà phải đốt một phiên là trả tiền cho việc mà một
#   lời gọi đọc làm xong trong nửa giây.
# · Chắc. Việc đã biết trước cách làm thì viết thẳng, đừng để agent lái —
#   dòng "để agent lái việc đã biết trước cách làm" trong CLAUDE.md là bài
#   học 4–9 phút đổi lấy 16 giây.
# · Rõ. Thực đơn đếm được: đọc hàm này là biết hết bề mặt.
#
# CỐ Ý KHÔNG CÓ LỆNH TUỲ Ý. Không mục nào ở đây chạy chữ do admin gõ; mỗi mục
# gọi một năng lực đã khai sẵn trong manifest. Muốn "gõ gì cũng được" thì đó
# là việc khác, và nó phải đi qua phiếu duyệt hiện nguyên văn lệnh.
#
# Và KHÔNG có mục nào sai khiến cái hộp. Hộp tự tới lấy việc theo nhịp của
# nó (timer trong distro openclaw) — nên ở đây không tồn tại chiều host→hộp
# để mà lỡ nới ra.
TAY_HUONG_DAN = (
    "Thực đơn /tay — đi thẳng tới company, không đánh thức CEO:\n\n"
    "/tay xem      — xưởng đang làm gì, việc nào chờ đại ca xem\n"
    "/tay nhatky   — mấy hôm nay xưởng làm được những gì\n"
    "/tay them <ý tưởng>  — SỬA HỆ NÀY: thêm/bớt/chữa trong companySpec\n"
    "/tay duan <ý tưởng>  — DỰ ÁN RIÊNG: web, bot, script… làm ở thư mục riêng\n"
    "/tay api <từ khoá>   — tra danh mục API công khai\n\n"
    "Hộp tự lấy việc mỗi vài phút, không cần gọi."
)


def goi_company(company: str, capability: str, inp: dict, tra: int = 60) -> dict:
    """Gọi dispatcher — cổng duy nhất (T2). Dựng argv bằng tay, không qua shell."""
    try:
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "gateway", "cli", "dispatch.py"), "call",
             "--company", company, "--capability", capability,
             "--input", json.dumps(inp, ensure_ascii=False)],
            capture_output=True, text=True, cwd=ROOT, timeout=tra)
        if not proc.stdout.strip():
            # O10 — câm thì nói là câm. Cắt TỪ ĐUÔI: traceback để loại lỗi ở
            # dòng cuối.
            return {"status": "failed",
                    "summary": f"dispatch không trả gì (mã {proc.returncode}): "
                               f"{proc.stderr.strip()[-600:]}"}
        return json.loads(proc.stdout)
    except subprocess.TimeoutExpired:
        # O8 — cửa vào không được phép sập.
        return {"status": "failed",
                "summary": f"{company}.{capability} quá {tra} giây. Việc có thể "
                           "ĐÃ chạy một phần — kiểm trước khi gõ lại."}
    except Exception as exc:
        return {"status": "failed",
                "summary": f"gọi {company}.{capability} hỏng: "
                           f"{type(exc).__name__}: {exc}"}


def _tin(chat_id, chu: str, markup=None) -> dict:
    return {"kind": "sendMessage", "chatId": chat_id, "text": telegram.esc(chu),
            "replyMarkupJson": markup or '{"inline_keyboard": []}'}


def _tra_loi_company(chat_id, kq: dict, company: str, capability: str) -> list:
    """Một kết quả company → tin nhắn, kèm nút duyệt nếu cần.

    Việc GHI vẫn phải xin duyệt như mọi đường khác — thực đơn này không phải
    cửa sau. Phiếu sinh ra ở đây thì CHÍNH ĐÂY phải gắn nút, vì không có phiên
    CEO nào đi cùng để làm hộ; không gắn thì phiếu nằm im và admin không bao
    giờ thấy (đúng lỗi câm mà gateway/telegram/cau.py đã phải chữa một lần).
    """
    chu = (kq.get("summary") or "").strip() or f"({company}.{capability} không nói gì)"
    if kq.get("status") == "needsApproval":
        xin = kq.get("approvalRequest") or {}
        try:
            import session
            nut = session.approval_keyboard(
                xin.get("approvalId"),
                session.can_whitelist(company, capability,
                                      xin.get("riskTier", "write")))
            return [_tin(chat_id, "Cần đại ca duyệt:\n" + (xin.get("consequence") or "")[:600],
                         session.markup_json(nut))]
        except Exception as exc:
            return [_tin(chat_id, f"Sinh được phiếu duyệt nhưng KHÔNG gắn được "
                                  f"nút: {type(exc).__name__}: {exc}. "
                                  f"Gõ /duyet để bấm.")]
    if kq.get("status") not in ("ok", None):
        chu = f"[{kq.get('status')}] {chu}"
    return [_tin(chat_id, chu)]


def xu_ly_tay(chu: str, chat_id) -> list:
    phan = chu.split(None, 2)          # ['/tay', '<mục>', '<phần còn lại>']
    muc = (phan[1].lower() if len(phan) > 1 else "").strip()
    con_lai = phan[2].strip() if len(phan) > 2 else ""

    if muc in ("", "help", "?"):
        return [_tin(chat_id, TAY_HUONG_DAN)]
    if muc == "xem":
        return _tra_loi_company(chat_id, goi_company("xuongCompany", "dsViec", {}),
                                "xuongCompany", "dsViec")
    if muc == "nhatky":
        return _tra_loi_company(chat_id,
                                goi_company("xuongCompany", "nhatKy", {"soNgay": 7}),
                                "xuongCompany", "nhatKy")
    if muc in ("them", "duan"):
        # HAI MỤC RIÊNG chứ không phải một mục có cờ. Loại việc quyết định việc
        # được làm Ở ĐÂU — sửa repo companySpec, hay dựng một dự án riêng trong
        # thư mục của hộp — và ghi nhầm thì mã đẻ ra lạc chỗ. Bắt admin gõ rõ
        # ngay từ chữ thứ hai thì không còn gì để đoán sai.
        loai = "duAn" if muc == "duan" else "repo"
        if len(con_lai) < 4:
            return [_tin(chat_id, f"Ghi gì vào xưởng? Gõ: /tay {muc} <ý tưởng>")]
        # Dòng đầu làm tiêu đề, cả câu giữ nguyên trong mô tả — chép chữ admin,
        # đừng diễn giải lại.
        return _tra_loi_company(
            chat_id,
            goi_company("xuongCompany", "themViec",
                        {"tieuDe": con_lai.splitlines()[0][:120],
                         "moTa": con_lai[:4000], "nguon": "admin",
                         "loai": loai}),
            "xuongCompany", "themViec")
    if muc == "api":
        if len(con_lai) < 2:
            return [_tin(chat_id, "Tra API gì? Gõ: /tay api <từ khoá>")]
        return _tra_loi_company(
            chat_id,
            goi_company("apiCompany", "timApi",
                        {"tuKhoa": con_lai[:80], "gioiHan": 6}),
            "apiCompany", "timApi")
    return [_tin(chat_id, f"Không có mục '{muc}'.\n\n{TAY_HUONG_DAN}")]


def run_gateway(update: dict) -> list:
    """Gateway là tiến trình riêng — hỏng thì chỉ hỏng một lượt, không sập poller."""
    try:
        proc = subprocess.run(
            [sys.executable, GATEWAY, "handle"],
            input=json.dumps(update, ensure_ascii=False),
            # 1140 > TREO_GIAY (1020) của gateway > 900s ngân sách company dài
            # nhất. Lớp ngoài phải chờ lâu hơn lớp trong, nếu không thì câu báo
            # cụ thể của gateway không bao giờ kịp gửi.
            capture_output=True, text=True, cwd=ROOT, timeout=1140,
        )
    except subprocess.TimeoutExpired:
        return [{"kind": "sendMessage", "chatId": ADMIN,
                 "text": "Quá 19 phút chưa xong, em dừng lại rồi. Việc có thể CHƯA CHẠY — đại ca kiểm lại trước khi nhắn lại.",
                 "replyMarkupJson": '{"inline_keyboard": []}'}]
    if proc.returncode != 0:
        # 2000 chứ không phải 300. Traceback Python có thứ đáng giá nhất ở
        # DÒNG CUỐI (loại lỗi và câu lỗi), còn 300 ký tự đầu chỉ đủ mấy khung
        # gọi trên cùng. Đo được 2026-08-19: gateway sập vì TimeoutExpired,
        # journal chỉ giữ tới "line 1597, in h" rồi cụt — mất đúng dòng nói nó
        # hỏng vì cái gì, phải đi suy ngược từ dấu thời gian mới ra.
        log("gateway lỗi:", proc.stderr.strip()[-2000:])
        return [{"kind": "sendMessage", "chatId": ADMIN,
                 "text": "Hệ gặp lỗi khi xử lý. Xem log để biết chi tiết.",
                 "replyMarkupJson": '{"inline_keyboard": []}'}]
    try:
        return json.loads(proc.stdout).get("actions", [])
    except json.JSONDecodeError:
        log("gateway trả về không phải JSON:", proc.stdout[:200])
        return []


def do_actions(actions: list, da_tra_loi_bam: bool = False, chat_id=None):
    """Thi hành hành động gateway trả về.

    `da_tra_loi_bam`: poller đã trả lời cái bấm ngay lúc nhận (xem vòng chính).
    Khi đó câu trả lời của gateway KHÔNG gửi lại thành toast được nữa — Telegram
    chỉ nhận một answerCallbackQuery cho mỗi lần bấm — nên nó được chuyển thành
    TIN NHẮN THƯỜNG. Bỏ đi thì mất hẳn những câu chỉ sống trong toast, ví dụ
    "Phiếu đã hết hạn" — và mất đúng lúc admin cần biết nhất.
    """
    for act in actions:
        kind = act.get("kind")

        if kind == "answerCallback" and da_tra_loi_bam:
            chu = (act.get("text") or "").strip()
            if chu:
                telegram.send_message(act.get("chatId") or chat_id, chu)
            continue

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


#: Dấu vết bộ canh cấp hệ thống (ops/canhHe.sh) để lại mỗi lần phải dựng lại.
DAU_VET_CANH = os.path.join(ROOT, "ops", ".canhHe.log")


def _bao_canh() -> str:
    """Đọc rồi XOÁ dấu vết của bộ canh — trả câu báo admin, hoặc "" nếu không có.

    Bộ canh chạy bằng root và không cầm token Telegram (T1: cửa ra là gateway),
    nên nó chỉ ghi lại. Người nói ra là poller, vì mỗi lần bộ canh dựng lại
    user manager thì poller cũng vừa khởi động — đúng lúc đọc.

    Không báo thì lần dựng lại ấy vô hình: hệ tự khỏi, admin không bao giờ biết
    nó đã chết, và sự cố lặp lại mỗi sáng trông y hệt một hệ khoẻ.
    """
    try:
        with open(DAU_VET_CANH, encoding="utf-8") as fh:
            dong = [d.rstrip("\n").split("\t", 1) for d in fh if d.strip()]
        os.remove(DAU_VET_CANH)
    except FileNotFoundError:
        return ""
    except OSError as exc:
        # O10: đọc hỏng không phải "không có gì". Nói ra.
        log(f"không đọc được {DAU_VET_CANH}: {exc}")
        return f"Em không đọc được sổ của bộ canh ({type(exc).__name__}) — đại ca xem journal giúp em."
    if not dong:
        return ""
    ra = [f"· {d[0][11:16]} {d[0][8:10]}/{d[0][5:7]}: {d[1] if len(d) > 1 else ''}"
          for d in dong[-5:]]
    if len(dong) > 5:
        ra.insert(0, f"· …và {len(dong) - 5} lần trước đó")
    return (f"Bộ canh vừa phải dựng lại hệ {len(dong)} lần — tức là trước đó em đã "
            "chết mà không tự nói được:\n" + "\n".join(ra))


def _bao_tin_bo_qua(bo_qua: list) -> str:
    """Câu báo tin bị bỏ lúc khởi động — DẪN LẠI từng tin, không chỉ đếm.

    Bản cũ chỉ nói "có 2 tin cũ em không đọc nữa". Ngày 2026-09-25 hệ chết cả
    ngày (user manager của WSL không lên được), admin nhắn hai lần vào khoảng
    trống ấy, rồi nửa đêm nhận về một con số — phải tự nhớ lại mình đã hỏi gì.
    Dẫn giờ và vài chục ký tự đầu thì admin biết ngay tin nào còn cần.
    """
    dong = []
    for upd in bo_qua[:5]:
        m = upd.get("message") or {}
        if not m:
            dong.append("· (một lần bấm nút)")
            continue
        chu = (m.get("text") or m.get("caption") or "(tệp/ảnh)").replace("\n", " ")
        gio = time.strftime("%H:%M %d/%m", time.localtime(m.get("date") or 0))
        dong.append(f"· {gio}: {chu[:80]}{'…' if len(chu) > 80 else ''}")
    if len(bo_qua) > 5:
        dong.append(f"· …và {len(bo_qua) - 5} tin nữa")
    return (f"Em vừa khởi động lại. Có {len(bo_qua)} tin cũ em không xử lý nữa — "
            "đại ca nhắn lại giúp em tin nào còn cần:\n" + "\n".join(dong))


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

    # Tin nhắn tồn đọng lúc khởi động: XỬ LÝ tin mới, bỏ qua tin cũ — và nếu có
    # bỏ thì NÓI RA.
    #
    # Bản cũ nhảy thẳng tới tin cuối cùng, tức bỏ sạch mọi thứ gửi trước lúc
    # khởi động, im lặng. Ý định đúng (đừng trả lời tin từ hôm kia), nhưng nó
    # nuốt luôn tin vừa gửi cách đây mười giây — đúng khoảng admin nhắn trong
    # lúc poller đang được khởi động lại. Xảy ra thật 2026-08-17: khởi động lại
    # mất 15 giây, admin nhắn vào đúng lúc đó và không bao giờ nhận được trả
    # lời, cũng không có gì báo là tin đã rơi.
    #
    # Nay: tin trong vòng NHAN_LAI_PHUT thì xử lý bình thường; cũ hơn thì bỏ
    # nhưng đếm và nhắn admin một câu. O10 — không nuốt im lặng.
    ton_dong, bo_qua_cu, offset = [], [], 0
    init = call("getUpdates", {"offset": 0, "timeout": 0}, timeout=20)
    if init.get("ok") and init.get("result"):
        nguong = time.time() - NHAN_LAI_PHUT * 60
        for upd in init["result"]:
            offset = upd["update_id"] + 1
            m = upd.get("message") or upd.get("callback_query", {}).get("message") or {}
            (ton_dong if (m.get("date") or 0) >= nguong else bo_qua_cu).append(upd)

    bao_canh = _bao_canh()
    if bao_canh:
        telegram.send_message(ADMIN, bao_canh)
    if bo_qua_cu:
        log(f"bỏ qua {len(bo_qua_cu)} tin cũ hơn {NHAN_LAI_PHUT} phút")
        telegram.send_message(ADMIN, _bao_tin_bo_qua(bo_qua_cu))
    log(f"sẵn sàng, đang chờ tin nhắn… ({len(ton_dong)} tin vừa gửi sẽ xử lý ngay)"
        if ton_dong else "sẵn sàng, đang chờ tin nhắn…")

    backoff = 1
    while True:
        # Mẻ tồn đọng vừa gom ở trên được xử lý trước, đúng một lần.
        if ton_dong:
            res, ton_dong = {"ok": True, "result": ton_dong}, []
        else:
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

            # TRẢ LỜI CÁI BẤM NGAY, TRƯỚC KHI LÀM VIỆC.
            #
            # Telegram chỉ nhận answerCallbackQuery trong khoảng 15 giây. Bản
            # cũ để gateway trả lời, mà gateway chỉ trả lời SAU KHI đã chạy
            # xong việc vừa được duyệt — đo 18/09: một lượt mất 191 giây, và
            # Telegram đáp "query is too old". Hậu quả không phải mất một dòng
            # log: NÚT BÁO ĐỎ TRÊN MÁY ADMIN trong khi việc thật ra đang chạy
            # đúng. Admin thấy hỏng, bấm lại, và mất niềm tin vào cái nút.
            #
            # Nên tách hai việc: báo "đã nhận" ngay tại đây, còn kết quả thì
            # gửi thành tin nhắn bình thường (xem do_actions).
            da_tra_loi_bam = False
            cq = upd.get("callback_query")
            if cq:
                telegram.answer_callback(cq["id"], "Đã nhận, đang chạy…")
                da_tra_loi_bam = True

            # `caption` CŨNG là chữ admin gõ. Bản cũ chỉ đọc `text` nên tệp gửi
            # kèm câu hỏi thì câu hỏi bị vứt — cùng lỗi đã ghi trong CLAUDE.md.
            m = upd.get("message") or {}
            chu = (m.get("text") or m.get("caption") or "").strip()
            if chu.lower().split(None, 1)[:1] == ["/tay"]:
                do_actions(xu_ly_tay(chu, chat_id))
                continue

            do_actions(run_gateway(upd), da_tra_loi_bam, chat_id)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("dừng.")
