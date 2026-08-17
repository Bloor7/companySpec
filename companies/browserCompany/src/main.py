#!/usr/bin/env python3
"""browserCompany — duyệt web bằng trình duyệt thật.

Hợp đồng (C1): taskEnvelope trên stdin → companyResult trên stdout.

FILE NÀY LÀ LỚP VỎ, chạy bằng python3 của hệ (3.10). Ruột nằm ở `runner.py`,
chạy bằng Python riêng trong `.venv` của company vì browser-use đòi >= 3.11.
Tách vậy cũng đúng về an toàn: Chromium và thư viện agent không nằm chung
tiến trình với dispatcher.

HÀNG RÀO Ở ĐÂY LÀ CODE CỨNG, KHÔNG PHẢI LỜI DẶN (P1/P2). Company này để chữ
trên trang lạ đi vào phần ra quyết định của một agent — không rào bằng prompt
được, vì prompt chính là chỗ kẻ tấn công viết vào. Nên rào bằng thứ agent
không nói vòng qua được:

  · danh sách ĐEN tên miền, kiểm trước khi mở và không lời gọi nào nới được
  · tên miền cho phép luôn được thu hẹp về đúng miền của urlBatDau nếu CEO
    không khai gì
  · trần bước cứng, trần thời gian cứng
  · hồ sơ trình duyệt trắng: không cookie, không phiên đăng nhập

Vì sao danh sách đen tồn tại dù đã có danh sách trắng: CEO là thứ dựng lời gọi,
và CEO đọc tin nhắn của admin — trong đó có thể có chữ admin chép từ nơi khác
về. Một lời gọi khai `tenMienChoPhep: ["mail.google.com"]` nhìn vẫn hợp lệ với
schema. Danh sách đen là chỗ nói "kể cả khai đúng cú pháp cũng không được vào".
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "lib"))
import db  # noqa: E402

STORE = os.path.join(HERE, "..", "store.sqlite")
VENV_PY = os.path.join(HERE, "..", ".venv", "bin", "python")
RUNNER = os.path.join(HERE, "runner.py")
KICHBAN = os.path.join(HERE, "kichban.py")

# Trần cứng. Manifest cho khai tới 20, nhưng con số cuối cùng là min của hai.
BUOC_TRAN = 20
BUOC_MAC_DINH = 10

# ───────────────────────── danh sách ĐEN ─────────────────────────
#
# Không lời gọi nào nới được. Ba nhóm, mỗi nhóm một lý do:
#   1. Nơi giữ dữ liệu của chính admin (Notion, Google, Telegram) — agent không
#      có cookie nên vào cũng không đọc được gì, nhưng chặn từ đầu thì không
#      phải tranh luận về "nếu lỡ còn phiên đăng nhập thì sao".
#   2. Tiền: ngân hàng, ví điện tử, sàn.
#   3. Mạng nội bộ và localhost — chặn agent quay vào chính máy này, gồm cả
#      gateway đang lắng nghe ở đó.
DEN = [
    r"(^|\.)notion\.so$", r"(^|\.)notion\.site$",
    r"(^|\.)google\.com$", r"(^|\.)gmail\.com$", r"(^|\.)googleapis\.com$",
    r"(^|\.)telegram\.org$", r"(^|\.)t\.me$",
    r"(^|\.)github\.com$",
    r"(^|\.)vietcombank\.com\.vn$", r"(^|\.)techcombank\.com\.vn$",
    r"(^|\.)mbbank\.com\.vn$", r"(^|\.)acb\.com\.vn$", r"(^|\.)vpbank\.com\.vn$",
    r"(^|\.)momo\.vn$", r"(^|\.)zalopay\.vn$", r"(^|\.)vnpay\.vn$",
    r"(^|\.)binance\.com$", r"(^|\.)paypal\.com$", r"(^|\.)stripe\.com$",
    r"^localhost$", r"^127\.", r"^10\.", r"^192\.168\.", r"^172\.(1[6-9]|2\d|3[01])\.",
    r"^0\.", r"^169\.254\.",
]
DEN_RE = [re.compile(p, re.I) for p in DEN]


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect() -> sqlite3.Connection:
    conn = db.connect(STORE)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS taskLog (
          taskId TEXT PRIMARY KEY, traceId TEXT NOT NULL, capability TEXT NOT NULL,
          inputHash TEXT NOT NULL, status TEXT NOT NULL, summary TEXT,
          startedAt TEXT NOT NULL, finishedAt TEXT, durationMs INTEGER, costUsd REAL
        );
        CREATE TABLE IF NOT EXISTS eventLog (
          eventId INTEGER PRIMARY KEY AUTOINCREMENT, taskId TEXT, traceId TEXT NOT NULL,
          eventType TEXT NOT NULL, payloadJson TEXT, createdAt TEXT NOT NULL
        );
        """
    )
    return conn


def mien_cua(url: str) -> str:
    """Tên miền của một URL. Không phân tích được thì trả chuỗi rỗng — và chuỗi
    rỗng sẽ trượt mọi phép kiểm ở dưới, tức là bị chặn. Đó là ý muốn."""
    try:
        return (urlparse(url).hostname or "").lower().strip(".")
    except Exception:
        return ""


def bi_cam(mien: str) -> bool:
    return any(r.search(mien) for r in DEN_RE)


def chuan_hoa_mien(inp: dict) -> list:
    """Danh sách tên miền cuối cùng agent được đi. Ném ValueError nếu không hợp lệ.

    Luôn có miền của `urlBatDau`. CEO khai thêm thì nhận, nhưng mỗi cái đều
    phải qua danh sách đen — khai 5 miền mà một cái bị cấm thì TỪ CHỐI CẢ LỜI
    GỌI, không âm thầm bỏ cái đó rồi chạy tiếp: im lặng sửa ý người gọi là
    cách chắc nhất để không ai biết hàng rào đã chặn cái gì.
    """
    goc = mien_cua(inp["urlBatDau"])
    if not goc:
        raise ValueError(f"urlBatDau không phải URL hợp lệ: {inp['urlBatDau'][:80]}")
    if not inp["urlBatDau"].lower().startswith(("http://", "https://")):
        raise ValueError("urlBatDau phải bắt đầu bằng http:// hoặc https://")

    mien = [goc] + [m.lower().strip(". ") for m in (inp.get("tenMienChoPhep") or [])]
    cam = [m for m in mien if bi_cam(m.lstrip("*."))]
    if cam:
        raise ValueError(
            f"Không mở được {', '.join(sorted(set(cam)))} — nằm trong danh sách cấm "
            "cứng của browserCompany (nơi giữ dữ liệu của admin, trang tiền bạc, "
            "hoặc địa chỉ nội bộ). Danh sách này không nới được bằng lời gọi.")
    # Bỏ trùng, giữ thứ tự
    ra = []
    for m in mien:
        if m and m not in ra:
            ra.append(m)
    return ra


def duyet_web(inp: dict):
    mien = chuan_hoa_mien(inp)
    so_buoc = min(int(inp.get("soBuocToiDa") or BUOC_MAC_DINH), BUOC_TRAN)

    if not os.path.isfile(VENV_PY):
        raise EnvironmentError(
            "Chưa dựng môi trường cho browserCompany. browser-use cần Python "
            ">= 3.11 mà máy đang chạy 3.10, nên nó dùng .venv riêng. "
            "Dựng bằng: bash companies/browserCompany/setup.sh")

    # Model local (nếu admin đã cắm) hoặc Gemini. Ưu tiên local: không tốn
    # đồng nào. Việc chọn nằm ở runner.chon_llm(); ở đây chỉ chuyển biến qua.
    base = os.environ.get("BROWSER_LLM_BASE_URL", "")
    khoa = os.environ.get("GEMINI_API_KEY", "")
    if not base and not khoa:
        raise EnvironmentError(
            "Chưa cấu hình model nào cho browserCompany. Hoặc cắm model local "
            "(BROWSER_LLM_BASE_URL + BROWSER_LLM_MODEL trong ops/.env — không "
            "tốn tiền), hoặc đặt GEMINI_API_KEY (TÍNH TIỀN THẬT, L8).")

    yeu_cau = {"nhiemVu": inp["nhiemVu"], "urlBatDau": inp["urlBatDau"],
               "tenMien": mien, "soBuoc": so_buoc}
    # Tiến trình con chỉ nhận đúng những biến nó cần (C2.4 áp dụng lại một tầng
    # nữa: dispatcher đã cắt env cho company, company cắt tiếp cho runner).
    env_con = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", ""),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "PYTHONIOENCODING": "utf-8",
        "GEMINI_API_KEY": khoa,
        "GOOGLE_API_KEY": khoa,      # browser-use đọc tên này
        "BROWSER_LLM_BASE_URL": base,
        "BROWSER_LLM_MODEL": os.environ.get("BROWSER_LLM_MODEL", ""),
        "BROWSER_LLM_API_KEY": os.environ.get("BROWSER_LLM_API_KEY", ""),
        "BROWSER_GEMINI_MODEL": os.environ.get("BROWSER_GEMINI_MODEL", ""),
        "ANONYMIZED_TELEMETRY": "false",
    }
    try:
        proc = subprocess.run(
            [VENV_PY, RUNNER], input=json.dumps(yeu_cau, ensure_ascii=False),
            capture_output=True, text=True, env=env_con, timeout=560)
    except subprocess.TimeoutExpired:
        raise TimeoutError("Quá 560 giây — cắt. Việc có thể đã làm được một phần.")

    if proc.returncode != 0:
        raise RuntimeError(f"runner hỏng: {proc.stderr.strip()[:300] or 'không nói gì'}")
    try:
        kq = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"runner trả về không phải JSON: {proc.stdout[:200]}")
    if kq.get("loi"):
        raise RuntimeError(kq["loi"][:300])

    het_buoc = bool(kq.get("hetBuocGiuaChung"))
    canh = " (HẾT BƯỚC giữa chừng — việc có thể chưa xong)" if het_buoc else ""
    ncc = kq.get("nhaCungCap") or "?"
    return (
        {"ketQua": kq.get("ketQua") or "",
         "soBuocDaChay": int(kq.get("soBuoc") or 0),
         "cacTrangDaVao": kq.get("cacTrang") or [],
         "hetBuocGiuaChung": het_buoc,
         "coLoi": bool(kq.get("coLoi"))},
        f'[{ncc}] Đã duyệt {len(kq.get("cacTrang") or [])} trang trong '
        f'{kq.get("soBuoc")} bước{canh}.',
        # D3 — có ra ngoài internet thì phải để lại dấu, dù chỉ là đọc.
        [{"type": "web.browse", "target": inp["urlBatDau"],
          "idempotencyKey": f'browse|{inp["urlBatDau"][:80]}',
          "reversible": True}],
        # L8 — phần khai TIỀN THẬT, đi vào `usage` chứ KHÔNG vào `output`:
        # outputSchema khai `additionalProperties: false` nên nhét trường lạ
        # vào output là bị chính cổng của mình từ chối (C2.3).
        # Chạy local thì paidVnd=0 — để trống thì dispatcher ghi theo giá ước
        # trong manifest, và sổ tiền thật sẽ đầy những khoản chưa từng tiêu.
        {"paidVnd": 0 if not kq.get("tonTienThat") else None,
         "paidProvider": ncc},
    )


def kiem_tra_trang(inp: dict):
    """Kịch bản CỨNG — không LLM, không tốn tiền, kết quả lặp lại được.

    Dùng chung hàng rào tên miền với duyetWeb: kịch bản do CEO dựng nên vẫn có
    thể trỏ vào chỗ không nên trỏ.
    """
    chuan_hoa_mien({"urlBatDau": inp["url"]})   # ném ValueError nếu bị cấm

    if not os.path.isfile(VENV_PY):
        raise EnvironmentError(
            "Chưa dựng môi trường cho browserCompany. "
            "Dựng bằng: bash companies/browserCompany/setup.sh")

    env_con = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", ""),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "PYTHONIOENCODING": "utf-8",
    }
    try:
        proc = subprocess.run(
            [VENV_PY, KICHBAN], input=json.dumps(inp, ensure_ascii=False),
            capture_output=True, text=True, env=env_con, timeout=80)
    except subprocess.TimeoutExpired:
        raise TimeoutError("Quá 80 giây — cắt. Trang có thể đang rất chậm.")

    if proc.returncode != 0:
        raise RuntimeError(f"kịch bản hỏng: {proc.stderr.strip()[:300] or 'không nói gì'}")
    kq = json.loads(proc.stdout)
    if kq.get("loi"):
        raise RuntimeError(kq["loi"][:300])

    tim = kq.get("timChu") or {}
    thay = [t for t, co in tim.items() if co]
    canh = f" · thấy chữ: {', '.join(thay)}" if thay else ""
    # Trang không nhúc nhích sau khi bấm là dấu hiệu bấm nhầm nút — nói ra,
    # đừng để CEO tưởng đã thao tác xong.
    if inp.get("bamNut") and kq.get("chuThayDoi") == 0:
        canh += " · TRANG KHÔNG PHẢN ỨNG sau khi bấm (bấm nhầm nút?)"
    return (
        kq,
        f'HTTP {kq.get("maHttp")} · "{(kq.get("tieuDe") or "")[:50]}" · '
        f'{kq.get("soNut")} nút, {kq.get("soOnhap")} ô nhập{canh}',
        [{"type": "web.browse", "target": inp["url"],
          "idempotencyKey": f'kiemtra|{inp["url"][:80]}', "reversible": True}],
        {"paidVnd": 0, "paidProvider": "không dùng model"},
    )


HANDLERS = {"duyetWeb": duyet_web, "kiemTraTrang": kiem_tra_trang}


def main() -> int:
    started = time.time()
    env = json.load(sys.stdin)
    task_id, trace_id = env["taskId"], env["traceId"]
    cap, inp = env["capability"], env["input"]
    dry_run = env.get("policy", {}).get("dryRun", False)

    result = {"taskId": task_id, "traceId": trace_id, "status": "failed",
              "output": None, "summary": "", "sideEffects": [], "error": None}
    tien_khai = {}      # phần khai TIỀN THẬT, gắn vào `usage` ở cuối (L8)

    conn = connect()
    conn.execute(
        "INSERT OR REPLACE INTO taskLog (taskId, traceId, capability, inputHash, "
        "status, startedAt) VALUES (?,?,?,?,?,?)",
        (task_id, trace_id, cap, env.get("_inputHash", ""), "running", now_utc()),
    )
    conn.commit()

    try:
        handler = HANDLERS.get(cap)
        if handler is None:
            raise ValueError(f"browserCompany không có năng lực '{cap}'")

        if dry_run:  # W2
            preview = json.dumps(inp, ensure_ascii=False)[:200]
            result.update(status="ok", output=None,
                          summary=f"[dryRun] Sẽ chạy {cap} với {preview}")
        else:
            output, summary, side_effects, tien = handler(inp)
            result.update(status="ok", output=output, summary=summary,
                          sideEffects=side_effects)
            # L8 — khai TIỀN THẬT. `paidVnd=0` khi chạy model local; `None` khi
            # chạy Gemini, để dispatcher ghi theo giá ước trong manifest (chưa
            # moi được số thật từ thư viện — đo xong lần đầu thì sửa lại đây).
            tien_khai.update({k: v for k, v in tien.items() if v is not None})

    except ValueError as exc:
        result.update(status="needsInput", error=str(exc), summary=str(exc))
    except (EnvironmentError, TimeoutError, RuntimeError) as exc:
        result.update(status="failed", error=str(exc), summary=str(exc))
    except Exception as exc:  # O3
        result.update(status="failed", error=f"{type(exc).__name__}: {exc}",
                      summary=f"browserCompany hỏng khi chạy {cap}.")

    duration = int((time.time() - started) * 1000)
    result["usage"] = {"steps": 1, "durationMs": duration, "costUsd": 0.0,
                       **tien_khai}
    conn.execute(
        "UPDATE taskLog SET status=?, summary=?, finishedAt=?, durationMs=? "
        "WHERE taskId=?",
        (result["status"], result["summary"][:400], now_utc(), duration, task_id),
    )
    conn.execute(
        "INSERT INTO eventLog (taskId, traceId, eventType, payloadJson, createdAt) "
        "VALUES (?,?,?,?,?)",
        (task_id, trace_id, f"{cap}.{result['status']}",
         json.dumps(inp, ensure_ascii=False)[:1000], now_utc()),
    )
    conn.commit()
    conn.close()

    json.dump(result, sys.stdout, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
