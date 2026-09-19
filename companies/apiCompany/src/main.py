#!/usr/bin/env python3
"""apiCompany — cuốn sổ tra API công khai. Hợp đồng (C1): taskEnvelope vào
stdin, companyResult ra stdout.

NÓ TRA, NÓ KHÔNG GỌI. Đọc khối đầu companySpec.yaml trước khi thêm bất cứ năng
lực nào ở đây — ranh giới ấy là lý do company này tồn tại riêng thay vì nhét
một hàm vào searchCompany.

Ba thứ trong file này được viết vì một bài học đã trả giá ở chỗ khác:

· `User-Agent` tự khai (lib/llmClient.py, 27/08). groq và cerebras trả 403 mà
  thật ra là Cloudflare chặn chữ ký `Python-urllib/3.10`. Ở đây cũng đi ra
  Internet nên cũng phải tự xưng tên, kẻo một ngày nào đó lại đi tạo lại khoá
  cho một lỗi không liên quan gì tới khoá.

· TUỔI của danh mục trả về cùng mọi kết quả đọc (registry/models.yaml, 31/08).
  Tên model cũ đi trong bốn ngày mà không nhà nào báo ai; API cũng thế. Một
  con số không kèm ngày chụp là một con số không tự già đi được trong mắt
  người đọc.

· `kiemApi` KHÔNG trả nội dung. Trả nội dung một lần là company này thành cái
  máy lấy dữ liệu từ URL bất kỳ, và cái ngày ấy sẽ không ai nhớ rằng nó từng
  chỉ là một cuốn sổ.
"""
import ipaddress
import json
import os
import re
import socket
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
COMPANY = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(COMPANY, "..", "..", "lib"))
import db  # noqa: E402

STORE = os.path.join(COMPANY, "store.sqlite")
TZ_VN = timezone(timedelta(hours=7))

NGUON = ("https://raw.githubusercontent.com/public-apis/public-apis"
         "/master/README.md")
# Tự xưng tên. Xem docstring.
UA = "companySpec-apiCompany/0.1 (+personal assistant; contact: admin)"

# Danh mục cũ hơn ngần này thì mọi kết quả đọc phải KÊU LÊN, không chỉ ghi tuổi.
CU_SAU_NGAY = 30


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
        CREATE TABLE IF NOT EXISTS api (
          ten TEXT PRIMARY KEY, moTa TEXT NOT NULL, auth TEXT NOT NULL,
          https TEXT NOT NULL, cors TEXT NOT NULL, link TEXT NOT NULL,
          nhom TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS api_nhom ON api (nhom);
        -- Một dòng duy nhất, id=1. Giữ mốc chụp để mọi câu trả lời nói được
        -- tuổi của mình.
        CREATE TABLE IF NOT EXISTS danhMuc (
          id INTEGER PRIMARY KEY CHECK (id = 1),
          nguon TEXT NOT NULL, capNhatLuc TEXT NOT NULL,
          tongMuc INTEGER NOT NULL, soNhom INTEGER NOT NULL
        );
        """
    )
    return conn


# ───────────────────────── tuổi của bản chụp ─────────────────────────

def _meta(conn):
    return conn.execute("SELECT * FROM danhMuc WHERE id=1").fetchone()


def _tuoi(meta) -> str:
    """"cập nhật 3 giờ trước" — và nói thẳng khi chưa có gì.

    O10: chưa có danh mục thì KHÔNG trả chuỗi rỗng cho giống như mọi khi.
    Chuỗi rỗng đọc y hệt "vừa cập nhật xong".
    """
    if meta is None:
        return "CHƯA CÓ DANH MỤC — phải chạy capNhatDanhMuc trước"
    moc = datetime.strptime(meta["capNhatLuc"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc)
    giay = (datetime.now(timezone.utc) - moc).total_seconds()
    if giay < 3600:
        tuoi = f"{int(giay // 60)} phút trước"
    elif giay < 86400:
        tuoi = f"{giay / 3600:.0f} giờ trước"
    else:
        tuoi = f"{giay / 86400:.0f} ngày trước"
    canh = ""
    if giay > CU_SAU_NGAY * 86400:
        canh = (f" — ĐÃ CŨ hơn {CU_SAU_NGAY} ngày, API có thể đã chết hoặc đổi "
                "điều khoản; chạy capNhatDanhMuc rồi hãy tin")
    return f"cập nhật {tuoi}{canh}"


# ───────────────────────── bóc README ─────────────────────────

MUC = re.compile(r"^\|\s*\[(?P<ten>[^\]]+)\]\((?P<link>[^)\s]+)[^)]*\)\s*\|")


def _boc(chu: str) -> list:
    """Bóc README thành danh sách mục.

    Hình dữ liệu: `### Nhóm` mở một mục lớn, rồi một bảng 5 cột
    `| [Tên](link) | Mô tả | Auth | HTTPS | CORS |`.

    Hai thứ cố ý bỏ: bảng nhà tài trợ ở đầu file (chỉ 3 cột, và nằm TRƯỚC
    tiêu đề `###` đầu tiên), và mục lục dạng danh sách gạch đầu dòng.
    Điều kiện lọc vì thế là "đã thấy một nhóm" VÀ "đủ 5 ô" — chứ không phải
    dò chuỗi con, vì dò chuỗi con thì hỏng lặng lẽ.
    """
    ra, nhom = [], None
    for dong in chu.splitlines():
        if dong.startswith("### "):
            nhom = dong[4:].strip()
            continue
        if nhom is None or not dong.startswith("| ["):
            continue
        o = [x.strip() for x in dong.split("|")]
        # ['', tên+link, mô tả, auth, https, cors, ''] — đúng 7 mảnh.
        if len(o) != 7:
            continue
        m = MUC.match(dong)
        if m is None:
            continue
        ra.append({
            "ten": m.group("ten").strip(),
            "link": m.group("link").strip(),
            "moTa": o[2],
            "auth": o[3].strip("`") or "No",
            "https": o[4],
            "cors": o[5],
            "nhom": nhom,
        })
    return ra


def cap_nhat(inp: dict) -> tuple:
    conn = connect()
    meta = _meta(conn)
    if meta is not None and not inp.get("batBuoc"):
        moc = datetime.strptime(meta["capNhatLuc"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - moc).total_seconds() < 86400:
            tong, so_nhom, luc = meta["tongMuc"], meta["soNhom"], meta["capNhatLuc"]
            conn.close()
            return ({"tongMuc": tong, "soNhom": so_nhom, "capNhatLuc": luc,
                     "boQua": True, "themMoi": 0, "matDi": 0},
                    f"Danh mục mới cập nhật dưới 24 giờ ({tong} mục) nên bỏ "
                    "qua. Muốn ép thì gọi lại với batBuoc: true.", [])

    req = urllib.request.Request(NGUON, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        chu = r.read().decode("utf-8", "replace")
    muc = _boc(chu)
    if len(muc) < 200:
        # O10 — bóc ra quá ít nghĩa là hình dữ liệu đã đổi, KHÔNG phải nghĩa là
        # thế giới còn ít API. Hỏng thì phải kêu, đừng ghi đè sổ tốt bằng sổ rác.
        raise RuntimeError(
            f"Chỉ bóc được {len(muc)} mục từ {len(chu)} ký tự — README của "
            "public-apis nhiều khả năng đã đổi định dạng bảng. KHÔNG ghi đè "
            "danh mục cũ. Xem lại hàm _boc().")

    cu = {r["ten"] for r in conn.execute("SELECT ten FROM api")}
    moi = {m["ten"] for m in muc}
    conn.execute("DELETE FROM api")
    conn.executemany(
        "INSERT OR REPLACE INTO api (ten, moTa, auth, https, cors, link, nhom) "
        "VALUES (?,?,?,?,?,?,?)",
        [(m["ten"], m["moTa"], m["auth"], m["https"], m["cors"], m["link"],
          m["nhom"]) for m in muc])
    so_nhom = len({m["nhom"] for m in muc})
    luc = now_utc()
    conn.execute(
        "INSERT OR REPLACE INTO danhMuc (id, nguon, capNhatLuc, tongMuc, soNhom) "
        "VALUES (1,?,?,?,?)", (NGUON, luc, len(muc), so_nhom))
    conn.commit()
    conn.close()
    them, mat = len(moi - cu), len(cu - moi)
    return ({"tongMuc": len(muc), "themMoi": them, "matDi": mat,
             "soNhom": so_nhom, "capNhatLuc": luc, "boQua": False},
            f"Danh mục API: {len(muc)} mục trong {so_nhom} nhóm "
            f"(+{them} mới, -{mat} mất). Nguồn public-apis.",
            [{"type": "catalog.refresh", "target": "apiCompany/danhMuc",
              "idempotencyKey": f"apiCatalog|{luc[:13]}", "reversible": True}])


# ───────────────────────── tra cứu ─────────────────────────

def _dong(r) -> dict:
    return {"ten": r["ten"], "moTa": r["moTa"], "auth": r["auth"],
            "https": r["https"], "cors": r["cors"], "link": r["link"],
            "nhom": r["nhom"]}


def tim_api(inp: dict) -> tuple:
    conn = connect()
    meta = _meta(conn)
    if meta is None:
        conn.close()
        raise ValueError(
            "Chưa có danh mục nào trong sổ. Gọi apiCompany.capNhatDanhMuc "
            "trước — nó miễn phí và mất khoảng 5 giây.")
    tu = inp["tuKhoa"].strip().lower()
    dk, tham = ["(lower(ten) LIKE ? OR lower(moTa) LIKE ?)"], [f"%{tu}%", f"%{tu}%"]
    if inp.get("nhom"):
        dk.append("lower(nhom) LIKE ?")
        tham.append(f"%{inp['nhom'].strip().lower()}%")
    if inp.get("khongCanKhoa"):
        dk.append("lower(auth) IN ('no','')")
    gioi_han = int(inp.get("gioiHan") or 10)
    dieu_kien = " AND ".join(dk)
    # Thứ tự: tên khớp đứng trước mô tả khớp — người hỏi "weather" muốn thấy
    # API có chữ weather trong TÊN trước, không phải một API ảnh tình cờ có
    # chữ weather trong câu mô tả.
    # sql-an-toan: `dieu_kien` ghép từ các mảnh HẰNG viết ngay phía trên, không
    # mảnh nào đến từ đầu vào; mọi giá trị người dùng nhập đi qua `tham` và '?'.
    rows = list(conn.execute(
        f"SELECT * FROM api WHERE {dieu_kien} "
        "ORDER BY (CASE WHEN lower(ten) LIKE ? THEN 0 ELSE 1 END), ten LIMIT ?",
        tham + [f"%{tu}%", gioi_han]))
    # sql-an-toan: cùng `dieu_kien` và cùng `tham` với câu ngay trên — đếm phải
    # dùng ĐÚNG bộ lọc ấy, viết thành hai chuỗi rời thì sớm muộn lệch nhau.
    tong = conn.execute(
        f"SELECT COUNT(*) FROM api WHERE {dieu_kien}", tham).fetchone()[0]
    tuoi = _tuoi(meta)
    tong_muc, luc = meta["tongMuc"], meta["capNhatLuc"]
    conn.close()
    ds = [_dong(r) for r in rows]
    if not ds:
        return ({"ketQua": [], "tong": 0, "tuoiDanhMuc": tuoi, "capNhatLuc": luc},
                f"Không có mục nào khớp '{inp['tuKhoa']}' trong {tong_muc} mục "
                f"({tuoi}).", [])
    dong = "\n".join(
        f"{d['ten']} [{d['nhom']}] — {d['moTa'][:70]} "
        f"(khoá: {d['auth']}, https: {d['https']})" for d in ds)
    return ({"ketQua": ds, "tong": tong, "tuoiDanhMuc": tuoi, "capNhatLuc": luc},
            f"{tong} mục khớp '{inp['tuKhoa']}', {len(ds)} cái đầu:\n{dong}\n"
            f"Danh mục {tuoi}. Mấy cột auth/https là LỜI KHAI của người đóng "
            "góp, chưa ai đo — muốn chắc thì gọi kiemApi. Và tìm ra không phải "
            "là dùng được: muốn dùng thật phải viết thành năng lực mới.",
            [])


def xem_api(inp: dict) -> tuple:
    conn = connect()
    meta = _meta(conn)
    r = conn.execute("SELECT * FROM api WHERE lower(ten)=?",
                     (inp["ten"].strip().lower(),)).fetchone()
    tuoi = _tuoi(meta)
    d = _dong(r) if r is not None else None
    conn.close()
    if d is None:
        raise ValueError(
            f"Không có mục nào tên đúng '{inp['ten']}'. Lấy tên từ timApi, "
            "đừng gõ lại theo trí nhớ.")
    return ({"api": d, "tuoiDanhMuc": tuoi},
            f"{d['ten']} [{d['nhom']}] — {d['moTa']}\n"
            f"khoá: {d['auth']} · https: {d['https']} · cors: {d['cors']}\n"
            f"{d['link']}\nDanh mục {tuoi}.", [])


# ───────────────────────── phép đo sức khoẻ ─────────────────────────

def _dia_chi_cong_cong(host: str) -> None:
    """Chặn SSRF: tên miền trong danh mục phải trỏ ra Internet, không trỏ về nhà.

    Danh mục là dữ liệu của người lạ. Một mục trỏ vào 127.0.0.1 hay 192.168.x
    sẽ biến phép đo sức khoẻ thành cái máy dò cổng trong mạng của admin. Hàng
    rào đặt ở đây, bằng mã, chứ không phải bằng lời dặn.
    """
    try:
        thong_tin = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError(f"Không phân giải được tên miền {host}: {exc}")
    for muc in thong_tin:
        ip = ipaddress.ip_address(muc[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast):
            raise ValueError(
                f"{host} phân giải ra địa chỉ nội bộ {ip} — từ chối gõ cửa. "
                "Mục này trong danh mục không đáng tin.")


def kiem_api(inp: dict) -> tuple:
    conn = connect()
    r = conn.execute("SELECT ten, link FROM api WHERE lower(ten)=?",
                     (inp["ten"].strip().lower(),)).fetchone()
    ten, url = (r["ten"], r["link"]) if r is not None else (None, None)
    conn.close()
    if ten is None:
        raise ValueError(f"Không có mục nào tên đúng '{inp['ten']}'. "
                         "Lấy tên từ timApi.")
    phan = urlsplit(url)
    if phan.scheme != "https":
        raise ValueError(
            f"{ten} khai địa chỉ {phan.scheme or 'không rõ'}:// — chỉ gõ cửa "
            "https. Đây cũng là một kết quả: mục này không dùng được.")
    _dia_chi_cong_cong(phan.hostname or "")

    req = urllib.request.Request(url, headers={"User-Agent": UA}, method="GET")
    bat_dau = time.time()
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ma = resp.status
    except urllib.error.HTTPError as exc:
        # 401/403 KHÔNG phải là chết — là còn sống và đang đòi khoá. Phân biệt
        # được hai thứ đó mới là điểm của phép đo này.
        ma = exc.code
    except Exception as exc:
        ms = int((time.time() - bat_dau) * 1000)
        return ({"ten": ten, "url": url, "msPhanHoi": ms,
                 "ketLuan": f"KHÔNG GỌI ĐƯỢC — {type(exc).__name__}: {exc}"},
                f"{ten}: không gọi được sau {ms}ms ({type(exc).__name__}). "
                "Coi như đã chết cho tới khi đo lại được.", [])
    ms = int((time.time() - bat_dau) * 1000)
    if ma in (401, 403):
        ket = f"CÒN SỐNG nhưng đòi khoá (HTTP {ma})"
    elif 200 <= ma < 400:
        ket = f"CÒN SỐNG (HTTP {ma})"
    elif ma == 429:
        ket = "CÒN SỐNG nhưng đang chặn vì gọi quá nhiều (HTTP 429)"
    else:
        ket = f"TRẢ LỖI (HTTP {ma})"
    return ({"ten": ten, "url": url, "maTrangThai": ma, "msPhanHoi": ms,
             "ketLuan": ket},
            f"{ten}: {ket}, phản hồi {ms}ms. Đây là phép đo lúc "
            f"{datetime.now(TZ_VN):%H:%M %d/%m}, không phải lời khai trong "
            "danh mục.", [])


HANDLERS = {"timApi": tim_api, "xemApi": xem_api,
            "capNhatDanhMuc": cap_nhat, "kiemApi": kiem_api}


def main() -> int:
    started = time.time()
    env = json.load(sys.stdin)
    task_id, trace_id = env["taskId"], env["traceId"]
    cap, inp = env["capability"], env["input"]
    dry_run = env.get("policy", {}).get("dryRun", False)

    result = {"taskId": task_id, "traceId": trace_id, "status": "failed",
              "output": None, "summary": "", "sideEffects": [], "error": None}

    conn = connect()
    conn.execute(
        "INSERT OR REPLACE INTO taskLog (taskId, traceId, capability, inputHash, "
        "status, startedAt) VALUES (?,?,?,?,?,?)",
        (task_id, trace_id, cap, env.get("_inputHash", ""), "running", now_utc()))
    conn.commit()
    conn.close()

    try:
        handler = HANDLERS.get(cap)
        if handler is None:
            raise ValueError(f"apiCompany không có năng lực '{cap}'")
        if dry_run:  # W2
            result.update(status="ok", output=None,
                          summary=f"[dryRun] {cap}: "
                                  + json.dumps(inp, ensure_ascii=False)[:150])
        else:
            output, summary, side_effects = handler(inp)
            result.update(status="ok", output=output, summary=summary,
                          sideEffects=side_effects)
    except ValueError as exc:
        result.update(status="needsInput", error=str(exc), summary=str(exc))
    except Exception as exc:  # O3
        result.update(status="failed", error=f"{type(exc).__name__}: {exc}",
                      summary=f"apiCompany hỏng khi chạy {cap}: {exc}")

    duration = int((time.time() - started) * 1000)
    result["usage"] = {"steps": 1, "durationMs": duration, "costUsd": 0.0}
    conn = connect()
    conn.execute(
        "UPDATE taskLog SET status=?, summary=?, finishedAt=?, durationMs=? "
        "WHERE taskId=?",
        (result["status"], result["summary"][:400], now_utc(), duration, task_id))
    conn.execute(
        "INSERT INTO eventLog (taskId, traceId, eventType, payloadJson, createdAt) "
        "VALUES (?,?,?,?,?)",
        (task_id, trace_id, f"{cap}.{result['status']}",
         json.dumps({"status": result["status"]}, ensure_ascii=False), now_utc()))
    conn.commit()
    conn.close()

    json.dump(result, sys.stdout, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
