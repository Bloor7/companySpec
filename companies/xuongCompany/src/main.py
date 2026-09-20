#!/usr/bin/env python3
"""xuongCompany — hàng đợi ý tưởng và trạng thái làm dở của chúng.

Hợp đồng (C1): taskEnvelope trên stdin → companyResult trên stdout.

Đọc khối đầu companySpec.yaml trước. Ba điều quan trọng nhất trong file này,
nhắc lại ở đây vì người sửa mã thường không mở manifest:

1. NHỊP TIM. Mất điện thì không ai kịp ghi "tôi vừa chết" — dòng `dangLam` nằm
   lại y nguyên và nhìn từ ngoài giống hệt một việc đang chạy ngon. Nên sự
   sống được chứng minh bằng một mốc thời gian được đập lại liên tục, không
   bằng một cột trạng thái do ai đó hứa sẽ cập nhật.

2. ĐƯỜNG ĐỌC NÓI THẬT NGAY. `ds_viec` tự tính lại "đứt gánh hay không" mỗi lần
   đọc, không đợi ai sửa sổ. S3 cấm cron ghi, nên nếu để việc phát hiện nằm ở
   đường ghi thì một hệ ngủ ba ngày sẽ suốt ba ngày báo "đang làm".

3. `buocKeTiep` DO CODE GIỮ, KHÔNG DO MODEL NGHĨ. Nó chỉ là chuỗi mà kẻ thực
   thi ghi lại lúc còn tỉnh. Cùng lẽ với `session.dong_phien()`: lúc hệ hỏng
   nhất cũng đúng là lúc một lời gọi tóm tắt sẽ hỏng theo.
"""
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
COMPANY = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(COMPANY, "..", "..", "lib"))
import db  # noqa: E402

STORE = os.path.join(COMPANY, "store.sqlite")
TZ_VN = timezone(timedelta(hours=7))

# Nhịp tim cũ hơn ngần này thì coi là ĐỨT GÁNH. Chọn 10 phút vì một bước thật
# (sửa mã rồi chạy ca thử) hiếm khi im lặng lâu hơn thế, còn máy mất điện thì
# im mãi mãi. Đặt quá ngắn: việc đang chạy đúng bị gọi là chết. Đặt quá dài:
# sau khi bật máy lại, xưởng ngồi đợi vô ích.
NHIP_TIM_DUT_PHUT = 10

# Bao nhiêu bước gần nhất đi kèm gói tiếp tục. Ít thôi — cái cần là "đã tới
# đâu", không phải toàn bộ tiểu sử. Muốn đủ thì đọc `git log` của nhánh.
GOI_TIEP_TUC_SO_BUOC = 8

# Xếp ưu tiên trong SQL. Từ vựng CÙNG todoCompany (cao|thường|thấp) —
# xem khối lý do trong companySpec.yaml. Viết thành hằng chứ không ghép
# chuỗi tại chỗ: một khái niệm thì một định nghĩa, ở chỗ mọi câu SQL cùng
# đọc, kẻo hai chỗ xếp hai kiểu rồi không ai biết tin cái nào.
XEP = "CASE uuTien WHEN 'cao' THEN 1 WHEN 'thường' THEN 2 ELSE 3 END"

DANG_MO = ("moi", "dangLam", "tamDung")
DA_DONG = ("choXem", "daGop", "bo", "hong")


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _doc(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc)


def _truoc_day(ts: str) -> str:
    """"12 phút trước" — người đọc cần khoảng cách, không cần chuỗi ISO."""
    if not ts:
        return "chưa bao giờ"
    giay = (datetime.now(timezone.utc) - _doc(ts)).total_seconds()
    if giay < 90:
        return f"{int(giay)} giây trước"
    if giay < 5400:
        return f"{int(giay // 60)} phút trước"
    if giay < 172800:
        return f"{giay / 3600:.0f} giờ trước"
    return f"{giay / 86400:.0f} ngày trước"


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
        CREATE TABLE IF NOT EXISTS viec (
          viecId TEXT PRIMARY KEY,
          tieuDe TEXT NOT NULL, moTa TEXT NOT NULL DEFAULT '',
          nguon TEXT NOT NULL DEFAULT 'admin',
          trangThai TEXT NOT NULL,
          uuTien INTEGER NOT NULL DEFAULT 3,
          nhanh TEXT NOT NULL DEFAULT '',
          -- MỘT CÂU: làm gì tiếp. Thứ duy nhất đọc lại sau khi mất điện.
          buocKeTiep TEXT NOT NULL DEFAULT '',
          lyDoDung TEXT NOT NULL DEFAULT '',
          ghiChuDung TEXT NOT NULL DEFAULT '',
          -- Mốc nên thử lại. Hết hạn mức thì đặt đúng giờ nhà cung cấp báo.
          tiepLuc TEXT,
          -- Chứng cứ SỐNG, không phải lời hứa sẽ cập nhật trạng thái.
          nhipTim TEXT,
          aiLam TEXT NOT NULL DEFAULT '',
          ketQua TEXT NOT NULL DEFAULT '',
          taoLuc TEXT NOT NULL, batDauLuc TEXT, xongLuc TEXT,
          capNhatLuc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS viec_tt ON viec (trangThai, uuTien, taoLuc);
        CREATE TABLE IF NOT EXISTS buoc (
          buocId INTEGER PRIMARY KEY AUTOINCREMENT,
          viecId TEXT NOT NULL, thuTu INTEGER NOT NULL,
          ten TEXT NOT NULL, trangThai TEXT NOT NULL,
          ketQua TEXT NOT NULL DEFAULT '', maThoat INTEGER,
          batDauLuc TEXT NOT NULL, xongLuc TEXT
        );
        CREATE INDEX IF NOT EXISTS buoc_viec ON buoc (viecId, thuTu);
        """
    )
    _them_cot(conn, "viec", "loai", "TEXT NOT NULL DEFAULT 'repo'")
    return conn


def _them_cot(conn, bang: str, cot: str, kieu: str) -> None:
    """Thêm cột cho sổ đã có sẵn dữ liệu.

    HỎI TRƯỚC RỒI MỚI THÊM, không `try/except: pass`. Nuốt lỗi ở đây nghĩa là
    một lần ALTER hỏng vì lý do khác (sổ khoá, đĩa đầy) sẽ trông y hệt "cột đã
    có rồi" — O10. Đọc pragma là một câu hỏi rõ ràng, trả lời rõ ràng.
    """
    # Tên bảng/cột KHÔNG đặt tham số '?' được — SQLite chỉ nhận tham số ở vị
    # trí GIÁ TRỊ, không ở vị trí định danh.
    # sql-an-toan: ba mảnh ghép vào đây đều là hằng viết trong chính file này
    # (connect() gọi với chuỗi cứng), không mảnh nào đến từ đầu vào của ai.
    co = {r[1] for r in conn.execute(f"PRAGMA table_info({bang})")}
    if cot not in co:
        # sql-an-toan: như trên — hằng trong file, không phải đầu vào.
        conn.execute(f"ALTER TABLE {bang} ADD COLUMN {cot} {kieu}")
        conn.commit()


def _lay(conn, viec_id: str) -> sqlite3.Row:
    r = conn.execute("SELECT * FROM viec WHERE viecId=?", (viec_id,)).fetchone()
    if r is None:
        # D6 — không tìm thấy thì BÁO, đừng lặng lẽ coi như đã xong.
        raise ValueError(f"Không có việc nào mang mã {viec_id}. Chạy dsViec "
                         "để lấy mã đúng, đừng đoán.")
    return r


def _dut_ganh(r: sqlite3.Row) -> bool:
    """Đang làm mà nhịp tim đã tắt = đứt gánh. Tính lúc ĐỌC, không đợi ai ghi."""
    if r["trangThai"] != "dangLam":
        return False
    if not r["nhipTim"]:
        return True
    return (datetime.now(timezone.utc) - _doc(r["nhipTim"])
            ).total_seconds() > NHIP_TIM_DUT_PHUT * 60


def _dap_nhip(conn, viec_id: str) -> None:
    conn.execute("UPDATE viec SET nhipTim=?, capNhatLuc=? WHERE viecId=?",
                 (now_utc(), now_utc(), viec_id))


# ───────────────────────── thêm và liệt kê ─────────────────────────

def them_viec(inp: dict) -> tuple:
    conn = connect()
    viec_id = "y_" + os.urandom(5).hex()
    luc = now_utc()
    conn.execute(
        "INSERT INTO viec (viecId, tieuDe, moTa, nguon, trangThai, uuTien, "
        "loai, taoLuc, capNhatLuc) VALUES (?,?,?,?,?,?,?,?,?)",
        (viec_id, inp["tieuDe"].strip(), (inp.get("moTa") or "").strip(),
         inp.get("nguon") or "admin", "moi", inp.get("uuTien") or "thường",
         inp.get("loai") or "repo", luc, luc))
    cho = conn.execute(
        "SELECT COUNT(*) FROM viec WHERE trangThai IN ('moi','tamDung')"
    ).fetchone()[0]
    conn.commit()
    conn.close()
    loai = inp.get("loai") or "repo"
    # Nói RÕ loại việc trong câu xác nhận. Hai loại làm ở hai chỗ khác hẳn
    # nhau, và ghi nhầm loại thì mã đẻ ra lạc chỗ — admin phải thấy được cái
    # sai ngay lúc xác nhận chứ không phải lúc đọc kết quả.
    ten_loai = ("sửa chính repo companySpec" if loai == "repo"
                else "dự án riêng, thư mục riêng trong hộp")
    return ({"viecId": viec_id, "tieuDe": inp["tieuDe"].strip(),
             "soDangCho": cho, "loai": loai},
            f"Đã ghi vào xưởng: {inp['tieuDe'][:80]} (mã {viec_id}, "
            f"loại {loai} — {ten_loai}). "
            f"Hàng đợi còn {cho} việc chưa làm xong.",
            [{"type": "idea.add", "target": viec_id,
              "idempotencyKey": f"xuong|{inp['tieuDe'][:60]}",
              "reversible": True}])


def _mo_ta_viec(conn, r: sqlite3.Row) -> dict:
    so_buoc = conn.execute("SELECT COUNT(*) FROM buoc WHERE viecId=?",
                           (r["viecId"],)).fetchone()[0]
    tt = r["trangThai"]
    if _dut_ganh(r):
        # Nói nguyên văn, đừng làm tròn thành "đang chạy". Đây là chỗ một cái
        # sai im lặng sẽ bắt đầu nếu ai đó thấy chữ này khó nghe rồi đổi đi.
        tt = "ĐỨT GÁNH"
    return {"viecId": r["viecId"], "tieuDe": r["tieuDe"], "trangThai": tt,
            "loai": r["loai"], "uuTien": r["uuTien"], "soBuoc": so_buoc,
            "buocKeTiep": r["buocKeTiep"], "lyDoDung": r["lyDoDung"],
            "tiepLuc": r["tiepLuc"] or "", "nhanh": r["nhanh"],
            "nhipTim": _truoc_day(r["nhipTim"]),
            "taoLuc": r["taoLuc"]}


def ds_viec(inp: dict) -> tuple:
    conn = connect()
    if inp.get("trangThai"):
        rows = list(conn.execute(
            "SELECT * FROM viec WHERE trangThai=? "
            "ORDER BY " + XEP + ", taoLuc LIMIT ?",
            (inp["trangThai"], int(inp.get("gioiHan") or 20))))
    else:
        rows = list(conn.execute(
            "SELECT * FROM viec WHERE trangThai IN ('moi','dangLam','tamDung',"
            "'choXem') ORDER BY (trangThai='choXem') DESC, " + XEP + ", taoLuc "
            "LIMIT ?", (int(inp.get("gioiHan") or 20),)))
    ds = [_mo_ta_viec(conn, r) for r in rows]
    tong = conn.execute("SELECT COUNT(*) FROM viec").fetchone()[0]
    cho_xem = conn.execute(
        "SELECT COUNT(*) FROM viec WHERE trangThai='choXem'").fetchone()[0]
    conn.close()
    dang_do = sum(1 for d in ds if d["trangThai"] in ("dangLam", "ĐỨT GÁNH",
                                                      "tamDung"))
    if not ds:
        return ({"cacViec": [], "tong": tong, "dangDo": 0, "choXem": 0},
                "Xưởng trống — không có việc nào đang mở.", [])
    dong = []
    for d in ds:
        phu = f" · {d['buocKeTiep'][:70]}" if d["buocKeTiep"] else ""
        if d["trangThai"] == "ĐỨT GÁNH":
            phu += f" (nhịp tim cuối {d['nhipTim']} — máy tắt hoặc tiến trình chết)"
        if d["trangThai"] == "tamDung" and d["lyDoDung"]:
            phu += f" (dừng vì {d['lyDoDung']}"
            phu += f", thử lại {d['tiepLuc'][:16]})" if d["tiepLuc"] else ")"
        dong.append(f"[{d['trangThai']}·{d['loai']}] {d['tieuDe'][:55]} — "
                    f"{d['viecId']} · {d['soBuoc']} bước{phu}")
    return ({"cacViec": ds, "tong": tong, "dangDo": dang_do,
             "choXem": cho_xem},
            f"{len(ds)} việc đang mở (tổng {tong} từ trước tới nay):\n"
            + "\n".join(dong), [])


# ───────────────────────── nhận việc, gói tiếp tục ─────────────────────────

def nhan_viec(inp: dict) -> tuple:
    """Chọn việc kế tiếp và trả GÓI TIẾP TỤC.

    Thứ tự CÓ CHỦ Ý — dở dang trước, việc mới sau:
      1. `tamDung` đã tới `tiepLuc` (hoặc không hẹn giờ)
      2. `dangLam` mà nhịp tim đã tắt (mất điện, tiến trình chết)
      3. `moi` theo ưu tiên rồi tới trước làm trước
    Một việc bỏ dở tốn hơn một việc chưa bắt đầu: nhánh git còn đó, bối cảnh
    còn đó, và mỗi ngày trôi qua là một ngày nó khó quay lại hơn.
    """
    conn = connect()
    moc = now_utc()
    r = conn.execute(
        "SELECT * FROM viec WHERE trangThai='tamDung' "
        "AND (tiepLuc IS NULL OR tiepLuc = '' OR tiepLuc <= ?) "
        "ORDER BY " + XEP + ", taoLuc LIMIT 1", (moc,)).fetchone()
    if r is None:
        for ung in conn.execute(
                "SELECT * FROM viec WHERE trangThai='dangLam' "
                "ORDER BY " + XEP + ", taoLuc"):
            if _dut_ganh(ung):
                r = ung
                break
    if r is None:
        r = conn.execute(
            "SELECT * FROM viec WHERE trangThai='moi' "
            "ORDER BY " + XEP + ", taoLuc LIMIT 1").fetchone()
    if r is None:
        # Còn việc tạm dừng nhưng CHƯA tới giờ thì phải nói ra, đừng để kẻ
        # thực thi tưởng xưởng rỗng rồi đi ngủ luôn.
        hen = conn.execute(
            "SELECT tieuDe, tiepLuc FROM viec WHERE trangThai='tamDung' "
            "AND tiepLuc > ? ORDER BY tiepLuc LIMIT 1", (moc,)).fetchone()
        conn.close()
        if hen is not None:
            return ({"coViec": False},
                    f"Chưa có việc nào nhận được lúc này. Việc gần nhất chờ "
                    f"tới {hen['tiepLuc']}: {hen['tieuDe'][:60]}.", [])
        return {"coViec": False}, "Xưởng trống, không có việc để nhận.", []

    viec_id = r["viecId"]
    lan_truoc = ""
    if r["trangThai"] == "tamDung" and r["lyDoDung"]:
        lan_truoc = f"{r['lyDoDung']}"
        if r["ghiChuDung"]:
            lan_truoc += f" — {r['ghiChuDung']}"
    elif _dut_ganh(r):
        lan_truoc = (f"dutGanh — nhịp tim cuối {_truoc_day(r['nhipTim'])}, "
                     "máy tắt hoặc tiến trình bị giết giữa chừng")

    buoc = list(conn.execute(
        "SELECT thuTu, ten, trangThai, ketQua, maThoat FROM buoc "
        "WHERE viecId=? ORDER BY thuTu DESC LIMIT ?",
        (viec_id, GOI_TIEP_TUC_SO_BUOC)))
    buoc_da_xong = [
        {"thuTu": b["thuTu"], "ten": b["ten"], "trangThai": b["trangThai"],
         "ketQua": (b["ketQua"] or "")[:200], "maThoat": b["maThoat"]}
        for b in reversed(buoc)]

    conn.execute(
        "UPDATE viec SET trangThai='dangLam', nhipTim=?, capNhatLuc=?, "
        "aiLam=?, batDauLuc=COALESCE(batDauLuc, ?), lyDoDung='', "
        "ghiChuDung='', tiepLuc=NULL WHERE viecId=?",
        (moc, moc, (inp.get("aiLam") or "hop")[:40], moc, viec_id))
    conn.commit()
    conn.close()

    ke_tiep = r["buocKeTiep"] or "Chưa có ghi chú bước kế tiếp — đọc lại mô tả việc rồi tự chọn bước đầu."
    dong_buoc = "\n".join(
        f"  {b['thuTu']}. [{b['trangThai']}] {b['ten']}"
        + (f" → {b['ketQua'][:80]}" if b["ketQua"] else "")
        for b in buoc_da_xong) or "  (chưa có bước nào)"
    return ({"coViec": True, "viecId": viec_id, "tieuDe": r["tieuDe"],
             "moTa": r["moTa"], "nhanh": r["nhanh"], "buocKeTiep": ke_tiep,
             "buocDaXong": buoc_da_xong, "lanTruocDung": lan_truoc,
             "loai": r["loai"]},
            f"Nhận việc {viec_id} [{r['loai']}]: {r['tieuDe']}\n"
            + (f"Lần trước dừng vì: {lan_truoc}\n" if lan_truoc else "")
            + (f"Nhánh: {r['nhanh']}\n" if r["nhanh"] else "")
            + f"Các bước đã chạy:\n{dong_buoc}\n"
            + f"BƯỚC KẾ TIẾP: {ke_tiep}",
            [{"type": "idea.claim", "target": viec_id,
              "idempotencyKey": f"nhan|{viec_id}|{moc[:16]}",
              "reversible": True}])


def ghi_buoc(inp: dict) -> tuple:
    conn = connect()
    r = _lay(conn, inp["viecId"])
    viec_id = r["viecId"]
    moc = now_utc()
    thu_tu = conn.execute(
        "SELECT COALESCE(MAX(thuTu), 0) + 1 FROM buoc WHERE viecId=?",
        (viec_id,)).fetchone()[0]
    dang = conn.execute(
        "SELECT buocId, ten FROM buoc WHERE viecId=? AND trangThai='dangLam' "
        "ORDER BY thuTu DESC LIMIT 1", (viec_id,)).fetchone()
    if dang is not None and dang["ten"] == inp["ten"] and inp["trangThai"] != "dangLam":
        # Đóng đúng cái bước đang mở thay vì đẻ thêm một dòng nữa. Cùng tên =
        # cùng bước; khác tên thì đó là bước mới, kể cả khi bước cũ còn dở.
        conn.execute(
            "UPDATE buoc SET trangThai=?, ketQua=?, maThoat=?, xongLuc=? "
            "WHERE buocId=?",
            (inp["trangThai"], (inp.get("ketQua") or "")[:2000],
             inp.get("maThoat"), moc, dang["buocId"]))
    else:
        conn.execute(
            "INSERT INTO buoc (viecId, thuTu, ten, trangThai, ketQua, maThoat, "
            "batDauLuc, xongLuc) VALUES (?,?,?,?,?,?,?,?)",
            (viec_id, thu_tu, inp["ten"], inp["trangThai"],
             (inp.get("ketQua") or "")[:2000], inp.get("maThoat"), moc,
             None if inp["trangThai"] == "dangLam" else moc))
    if inp.get("buocKeTiep"):
        conn.execute("UPDATE viec SET buocKeTiep=? WHERE viecId=?",
                     (inp["buocKeTiep"][:500], viec_id))
    _dap_nhip(conn, viec_id)
    so = conn.execute("SELECT COUNT(*) FROM buoc WHERE viecId=?",
                      (viec_id,)).fetchone()[0]
    conn.commit()
    conn.close()
    return ({"viecId": viec_id, "soBuoc": so},
            f"{viec_id} · bước {so}: [{inp['trangThai']}] {inp['ten'][:80]}"
            + (f" → {inp['ketQua'][:100]}" if inp.get("ketQua") else ""),
            [])


def tam_dung(inp: dict) -> tuple:
    conn = connect()
    r = _lay(conn, inp["viecId"])
    if r["trangThai"] in DA_DONG:
        conn.close()
        raise ValueError(
            f"{inp['viecId']} đã đóng ({r['trangThai']}) rồi, không tạm dừng "
            "được. Muốn mở lại thì thêm việc mới và nói rõ nó nối tiếp cái nào.")
    moc = now_utc()
    tiep = (inp.get("tiepLuc") or "").strip() or None
    conn.execute(
        "UPDATE viec SET trangThai='tamDung', lyDoDung=?, ghiChuDung=?, "
        "tiepLuc=?, capNhatLuc=? WHERE viecId=?",
        (inp["lyDo"], (inp.get("ghiChu") or "")[:1000], tiep, moc,
         inp["viecId"]))
    if inp.get("buocKeTiep"):
        conn.execute("UPDATE viec SET buocKeTiep=? WHERE viecId=?",
                     (inp["buocKeTiep"][:500], inp["viecId"]))
    ke = conn.execute("SELECT buocKeTiep FROM viec WHERE viecId=?",
                      (inp["viecId"],)).fetchone()["buocKeTiep"]
    conn.commit()
    conn.close()
    return ({"viecId": inp["viecId"], "trangThai": "tamDung",
             "tiepLuc": tiep or ""},
            f"Đã dừng {inp['viecId']} ({r['tieuDe'][:50]}) vì {inp['lyDo']}"
            + (f", thử lại từ {tiep}" if tiep else "")
            + (f". Bước kế tiếp đã ghi: {ke[:120]}" if ke else
               ". CHƯA ghi bước kế tiếp — lần sau nhận lại sẽ phải dò từ đầu."),
            [{"type": "idea.pause", "target": inp["viecId"],
              "idempotencyKey": f"dung|{inp['viecId']}|{moc[:16]}",
              "reversible": True}])


def xong_viec(inp: dict) -> tuple:
    conn = connect()
    r = _lay(conn, inp["viecId"])
    moc = now_utc()
    conn.execute(
        "UPDATE viec SET trangThai=?, ketQua=?, nhanh=COALESCE(NULLIF(?,''), "
        "nhanh), xongLuc=?, capNhatLuc=?, buocKeTiep='' WHERE viecId=?",
        (inp["trangThai"], inp["ketQua"][:3000], (inp.get("nhanh") or ""),
         moc, moc, inp["viecId"]))
    so = conn.execute("SELECT COUNT(*) FROM buoc WHERE viecId=?",
                      (inp["viecId"],)).fetchone()[0]
    hong = conn.execute(
        "SELECT COUNT(*) FROM buoc WHERE viecId=? AND trangThai='hong'",
        (inp["viecId"],)).fetchone()[0]
    conn.commit()
    conn.close()
    canh = ""
    if inp["trangThai"] == "choXem" and hong:
        # Không chặn — nhưng phải NÓI RA. Đóng "chờ xem" trong khi có bước
        # hỏng là đúng hình dạng của bug `is_done()` cũ.
        canh = (f" ⚠ có {hong} bước HỎNG trong việc này — nói rõ với admin "
                "trước khi bảo là xong.")
    return ({"viecId": inp["viecId"], "trangThai": inp["trangThai"],
             "soBuoc": so},
            f"{inp['viecId']} ({r['tieuDe'][:50]}) → {inp['trangThai']} sau "
            f"{so} bước. {inp['ketQua'][:200]}{canh}",
            [{"type": "idea.close", "target": inp["viecId"],
              "idempotencyKey": f"xong|{inp['viecId']}|{inp['trangThai']}",
              "reversible": inp["trangThai"] != "daGop"}])


def don_dep(inp: dict) -> tuple:
    """Việc đang làm mà nhịp tim tắt → tạm dừng với lý do dutGanh.

    KHÔNG làm mất gì: bước đã ghi giữ nguyên, `buocKeTiep` giữ nguyên. Việc
    duy nhất nó làm là để `nhanViec` nhặt lại được.
    """
    conn = connect()
    qua = int(inp.get("quaPhut") or NHIP_TIM_DUT_PHUT)
    moc = (datetime.now(timezone.utc) - timedelta(minutes=qua)
           ).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = list(conn.execute(
        "SELECT viecId, tieuDe, nhipTim FROM viec WHERE trangThai='dangLam' "
        "AND (nhipTim IS NULL OR nhipTim < ?)", (moc,)))
    for r in rows:
        conn.execute(
            "UPDATE viec SET trangThai='tamDung', lyDoDung='dutGanh', "
            "ghiChuDung=?, capNhatLuc=? WHERE viecId=?",
            (f"nhịp tim cuối {_truoc_day(r['nhipTim'])} — máy tắt hoặc tiến "
             "trình bị giết giữa chừng", now_utc(), r["viecId"]))
    conn.commit()
    conn.close()
    ds = [{"viecId": r["viecId"], "tieuDe": r["tieuDe"],
           "nhipTim": _truoc_day(r["nhipTim"])} for r in rows]
    if not ds:
        return ({"daDon": 0, "cacViec": []},
                f"Không có việc nào đứt gánh (ngưỡng {qua} phút).", [])
    return ({"daDon": len(ds), "cacViec": ds},
            f"Đã dọn {len(ds)} việc đứt gánh, chúng sẽ được nhận lại:\n"
            + "\n".join(f"{d['viecId']} — {d['tieuDe'][:60]} "
                        f"(nhịp tim cuối {d['nhipTim']})" for d in ds),
            [{"type": "idea.sweep", "target": "xuongCompany",
              "idempotencyKey": f"don|{now_utc()[:16]}", "reversible": False}])


def nhat_ky(inp: dict) -> tuple:
    """Xưởng ĐÃ LÀM gì — trí nhớ giữa các phiên, để khỏi hỏi lại."""
    conn = connect()
    tu = (datetime.now(timezone.utc) - timedelta(days=int(inp.get("soNgay") or 7))
          ).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = list(conn.execute(
        "SELECT viecId, tieuDe, trangThai, ketQua, nhanh, xongLuc FROM viec "
        "WHERE trangThai IN ('choXem','daGop','bo','hong') AND xongLuc >= ? "
        "ORDER BY xongLuc DESC LIMIT ?",
        (tu, int(inp.get("gioiHan") or 20))))
    ds = []
    for r in rows:
        so = conn.execute("SELECT COUNT(*) FROM buoc WHERE viecId=?",
                          (r["viecId"],)).fetchone()[0]
        ds.append({"viecId": r["viecId"], "tieuDe": r["tieuDe"],
                   "trangThai": r["trangThai"], "ketQua": r["ketQua"][:400],
                   "nhanh": r["nhanh"], "soBuoc": so,
                   "xongLuc": r["xongLuc"],
                   "xong": _truoc_day(r["xongLuc"])})
    conn.close()
    if not ds:
        return ({"cacMuc": [], "tong": 0},
                f"Xưởng chưa đóng việc nào trong {inp.get('soNgay') or 7} "
                "ngày qua.", [])
    return ({"cacMuc": ds, "tong": len(ds)},
            f"{len(ds)} việc đã đóng:\n" + "\n".join(
                f"[{d['trangThai']}] {d['tieuDe'][:60]} ({d['xong']}, "
                f"{d['soBuoc']} bước) — {d['ketQua'][:120]}" for d in ds),
            [])


HANDLERS = {"themViec": them_viec, "dsViec": ds_viec, "nhanViec": nhan_viec,
            "ghiBuoc": ghi_buoc, "tamDung": tam_dung, "xongViec": xong_viec,
            "donDep": don_dep, "nhatKy": nhat_ky}


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
            raise ValueError(f"xuongCompany không có năng lực '{cap}'")
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
                      summary=f"xuongCompany hỏng khi chạy {cap}: {exc}")

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
