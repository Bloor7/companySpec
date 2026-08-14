#!/usr/bin/env python3
"""walletCompany — số dư thực đang có trong tay.

Hợp đồng (C1): taskEnvelope trên stdin → companyResult trên stdout.

Mỗi ví là một dòng trên Notion, và con số trong đó là SỐ THẬT: mở Notion ra thấy
bao nhiêu thì trong túi bấy nhiêu. Mỗi lần tiền vào/ra, CEO gọi adjustBalance
ngay sau khi ghi thu/chi.

Company này cố ý không biết gì về sổ thu chi (C3) — nó chỉ nhận lệnh cộng trừ.
Việc đối chiếu "ví có khớp với sổ không" là của báo cáo tối, nơi được phép gọi
nhiều company.
"""
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "lib"))
import notionClient as notion  # noqa: E402
import db  # noqa: E402

STORE = os.path.join(HERE, "..", "store.sqlite")
TZ = timezone(timedelta(hours=7))
VI = ["tiền mặt", "tài khoản"]


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def bay_gio_iso() -> str:
    """Thời điểm kiểm kê phải có GIỜ, không chỉ có ngày.

    Ngày 2026-08-04 đo được lỗi này: admin đếm tiền lúc 12:43 được 4.000đ, mà
    5 khoản chi 261.000đ ghi lúc 02:43 và 11:59 — tức đã nằm trong con số 4.000
    rồi. Công thức cũ so bằng NGÀY nên trừ chúng lần nữa, ra số dư âm 177.000đ.
    Có giờ thì mới phân biệt được "trước lúc đếm" và "sau lúc đếm".
    """
    return datetime.now(TZ).strftime("%Y-%m-%dT%H:%M:%S+07:00")


def database_id() -> str:
    dbid = os.environ.get("NOTION_WALLET_DATABASE_ID", "")
    if not dbid:
        raise notion.NotionError(
            "Thiếu NOTION_WALLET_DATABASE_ID. Chạy: python3 ops/setup-notion.py")
    return dbid


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


def money(amount: float) -> str:
    return f"{amount:,.0f}đ".replace(",", ".")


def row_to_wallet(page: dict) -> dict:
    props = page.get("properties", {})
    return {
        "walletId": page["id"],
        "vi": notion.plain(props.get("Tên")) or "",
        "soTien": notion.plain(props.get("Số dư")) or 0,
        "ngay": notion.plain(props.get("Kiểm kê lúc")),
        "ghiChu": notion.plain(props.get("Ghi chú")) or "",
    }


def fetch(token) -> list:
    pages = notion.query_database(token, database_id(), page_size=50)
    vis = [row_to_wallet(p) for p in pages]
    vis.sort(key=lambda v: VI.index(v["vi"]) if v["vi"] in VI else 99)
    return vis


def tim(vis: list, ten: str):
    return next((v for v in vis if v["vi"] == ten), None)


# ───────────────────────── năng lực ─────────────────────────

def get_balance(token, inp):
    vis = fetch(token)
    if inp.get("vi"):
        vis = [v for v in vis if v["vi"] == inp["vi"]]
    if not vis:
        return ({"vi": [], "tong": 0, "kiemKeTu": None},
                "Chưa kiểm kê ví nào. Nhắn em số tiền đang có để ghi mốc đầu tiên.",
                [])

    tong = sum(v["soTien"] for v in vis)
    ngays = [v["ngay"] for v in vis if v["ngay"]]
    tu = max(ngays) if ngays else None

    dong = [f'{v["vi"]}: {money(v["soTien"])}' for v in vis]
    return (
        {"vi": vis, "tong": tong, "kiemKeTu": tu},
        "\n".join(dong) + (f"\nTổng: {money(tong)}" if len(vis) > 1 else ""),
        [],
    )


def set_balance(token, inp):
    ngay = inp.get("ngay") or bay_gio_iso()
    vis = fetch(token)
    cu = tim(vis, inp["vi"])

    props = {
        "Tên":         notion.title_prop(inp["vi"]),
        "Số dư":       notion.number_prop(inp["soTien"]),
        "Kiểm kê lúc": notion.date_prop(ngay),
        "Ghi chú":     notion.text_prop(inp.get("ghiChu", "")),
    }

    if cu:
        notion.update_page(token, cu["walletId"], props)
        truoc, kieu, target = cu["soTien"], "notion.updatePage", cu["walletId"]
    else:
        page = notion.create_page(token, database_id(), props)
        truoc, kieu, target = None, "notion.createPage", page["id"]

    tong = sum(v["soTien"] for v in fetch(token))
    lech = (f" (trước đó ghi {money(truoc)}, lệch {money(inp['soTien'] - truoc)})"
            if truoc is not None and truoc != inp["soTien"] else "")
    return (
        {"vi": inp["vi"], "soTien": inp["soTien"], "ngay": ngay,
         "previous": truoc, "tong": tong},
        f'Đã kiểm kê {inp["vi"]}: {money(inp["soTien"])}{lech}. '
        f"Tổng cả hai ví: {money(tong)}.",
        # D5 — ghi đè một con số gốc thì phải chép lại giá trị cũ.
        [{"type": kieu, "target": target,
          "idempotencyKey": f'kiemke|{inp["vi"]}|{ngay}|{inp["soTien"]}',
          "reversible": True,
          "previousValue": (f'{cu["soTien"]}|{cu["ngay"]}' if cu else None)}],
    )


# Chiều tiền đi của từng loại. `loai` là NGUỒN SỰ THẬT DUY NHẤT về chiều.
CHIEU_TIEN = {
    "thu": +1, "chi": -1,
    "nạp quỹ": -1, "rút quỹ": +1,          # tiền rời/về ví, không phải thu chi
    "điều chỉnh tăng": +1, "điều chỉnh giảm": -1,
}


def so_tien_co_dau(inp: dict) -> float:
    """Đổi `soTien` (độ lớn, luôn dương) thành mức thay đổi có dấu theo `loai`.

    VÌ SAO KHÔNG CÒN KIỂM DẤU NỮA: bản trước bắt `soTien` mang dấu, rồi kiểm nó
    có khớp `loai` không, lệch thì từ chối. Chốt đó bắt được lỗi thật ba lần
    (228.000đ ngày 06/08, 70.000đ và 45.000đ ngày 07–08/08) — nhưng lần nào CEO
    cũng gửi số DƯƠNG kèm loai "chi", tức là chốt chỉ đang thu phí một lượt gọi
    lại cho một lỗi chắc chắn sẽ lặp.

    Gốc rễ là hợp đồng bắt khai chiều tiền HAI LẦN: một lần bằng dấu, một lần
    bằng `loai`. Hai nguồn sự thật cho cùng một điều thì sớm muộn cũng đá nhau.

    Giờ chỉ còn MỘT: `soTien` là độ lớn, `loai` quyết chiều. Không còn mâu thuẫn
    nào để mà kiểm, vì không còn cách nào diễn đạt sai. `điều chỉnh` cũng tách
    thành `tăng`/`giảm` để không sót một trường hợp nào phải đoán.
    """
    chieu = CHIEU_TIEN.get(inp.get("loai"))
    if chieu is None:      # schema đã chặn, đây chỉ là lưới cuối
        raise ValueError(f'Không hiểu loai "{inp.get("loai")}".')
    return chieu * abs(float(inp["soTien"]))


def adjust_balance(token, inp):
    """Cộng/trừ thẳng vào số dư — số dương là tiền vào, âm là tiền ra.

    Đây là thứ giữ cho con số trên Notion luôn là con số thật. Nó KHÔNG tự chạy:
    CEO phải gọi ngay sau khi ghi thu/chi, và admin thấy số dư mới ngay trong câu
    trả lời nên quên là lộ ra liền.
    """
    thay_doi = so_tien_co_dau(inp)

    vis = fetch(token)
    cu = tim(vis, inp["vi"])
    if cu is None:
        raise ValueError(
            f'Chưa có ví "{inp["vi"]}". Nhắn em số tiền đang có ở ví đó trước.')

    moi = cu["soTien"] + thay_doi
    if moi < 0:
        raise ValueError(
            f'Ví "{inp["vi"]}" đang có {money(cu["soTien"])}, trừ {money(-thay_doi)} '
            "thì âm. Đại ca đếm lại tiền thật rồi báo em kiểm kê cho khớp.")

    ngay = bay_gio_iso()
    notion.update_page(token, cu["walletId"], {
        "Số dư": notion.number_prop(moi),
        "Kiểm kê lúc": notion.date_prop(ngay),
        "Ghi chú": notion.text_prop(inp.get("ghiChu", ""))})

    tong = sum(v["soTien"] for v in fetch(token))
    dau = "+" if thay_doi >= 0 else "−"
    return (
        {"vi": inp["vi"], "thayDoi": thay_doi, "soDuCu": cu["soTien"],
         "soDuMoi": moi, "tong": tong},
        f'{inp["vi"]}: {money(cu["soTien"])} {dau} {money(abs(thay_doi))} '
        f'= {money(moi)} ({inp["loai"]}). Tổng cả hai ví: {money(tong)}.',
        # D5 — số cũ phải nằm trong previousValue, nếu không thì không lùi lại được.
        [{"type": "notion.updatePage", "target": cu["walletId"],
          "idempotencyKey": f'adjust|{inp["vi"]}|{thay_doi}|{ngay}',
          "reversible": True, "previousValue": f'Số dư={cu["soTien"]}'}],
    )


def transfer_balance(token, inp):
    if inp["tuVi"] == inp["denVi"]:
        raise ValueError("Chuyển từ ví này sang chính nó thì không đổi gì cả.")

    vis = fetch(token)
    nguon, dich = tim(vis, inp["tuVi"]), tim(vis, inp["denVi"])
    if nguon is None:
        raise ValueError(f'Chưa kiểm kê ví "{inp["tuVi"]}" bao giờ. '
                         "Nhắn em số tiền đang có ở ví đó trước.")
    if nguon["soTien"] < inp["soTien"]:
        raise ValueError(
            f'Ví "{inp["tuVi"]}" chỉ đang ghi {money(nguon["soTien"])}, '
            f'không chuyển được {money(inp["soTien"])}.')

    ngay = bay_gio_iso()
    notion.update_page(token, nguon["walletId"], {
        "Số dư": notion.number_prop(nguon["soTien"] - inp["soTien"]),
        "Kiểm kê lúc": notion.date_prop(ngay)})

    if dich:
        notion.update_page(token, dich["walletId"], {
            "Số dư": notion.number_prop(dich["soTien"] + inp["soTien"]),
            "Kiểm kê lúc": notion.date_prop(ngay)})
        dich_id, dich_cu = dich["walletId"], dich["soTien"]
    else:
        page = notion.create_page(token, database_id(), {
            "Tên": notion.title_prop(inp["denVi"]),
            "Số dư": notion.number_prop(inp["soTien"]),
            "Kiểm kê lúc": notion.date_prop(ngay),
            "Ghi chú": notion.text_prop("")})
        dich_id, dich_cu = page["id"], 0

    sau = {v["vi"]: v["soTien"] for v in fetch(token)}
    return (
        {"tuVi": inp["tuVi"], "denVi": inp["denVi"], "soTien": inp["soTien"],
         "conLai": sau, "tong": sum(sau.values())},
        f'Đã chuyển {money(inp["soTien"])} từ {inp["tuVi"]} sang {inp["denVi"]}. '
        + " · ".join(f"{k} {money(v)}" for k, v in sau.items())
        + ". Tổng không đổi — đây không phải khoản thu hay chi.",
        [{"type": "notion.updatePage", "target": nguon["walletId"],
          "idempotencyKey": f'chuyen|{inp["tuVi"]}|{inp["denVi"]}|{inp["soTien"]}|{ngay}',
          "reversible": True,
          "previousValue": f'{inp["tuVi"]}={nguon["soTien"]}'},
         {"type": "notion.updatePage", "target": dich_id,
          "idempotencyKey": f'chuyen-den|{inp["denVi"]}|{inp["soTien"]}|{ngay}',
          "reversible": True,
          "previousValue": f'{inp["denVi"]}={dich_cu}'}],
    )


HANDLERS = {"getBalance": get_balance, "setBalance": set_balance,
            "adjustBalance": adjust_balance,
            "transferBalance": transfer_balance}


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
        (task_id, trace_id, cap, env.get("_inputHash", ""), "running", now_utc()),
    )
    conn.commit()

    try:
        handler = HANDLERS.get(cap)
        if handler is None:
            raise ValueError(f"walletCompany không có năng lực '{cap}'")

        if dry_run:  # W2
            result.update(
                status="ok", output=None,
                summary=f"[dryRun] Sẽ chạy {cap} với {json.dumps(inp, ensure_ascii=False)}")
        else:
            token = notion.token_from_env()
            output, summary, side_effects = handler(token, inp)
            result.update(status="ok", output=output, summary=summary,
                          sideEffects=side_effects)

    except notion.NotionError as exc:
        result.update(status="failed", error=str(exc),
                      summary=f"Notion không phản hồi đúng: {exc}")
    except ValueError as exc:
        result.update(status="needsInput", error=str(exc), summary=str(exc))
    except Exception as exc:  # O3
        result.update(status="failed", error=f"{type(exc).__name__}: {exc}",
                      summary=f"walletCompany hỏng khi chạy {cap}.")

    duration = int((time.time() - started) * 1000)
    result["usage"] = {"steps": 1, "durationMs": duration, "costUsd": 0.0}

    conn.execute(
        "UPDATE taskLog SET status=?, summary=?, finishedAt=?, durationMs=?, costUsd=? "
        "WHERE taskId=?",
        (result["status"], result["summary"], now_utc(), duration, 0.0, task_id),
    )
    conn.execute(
        "INSERT INTO eventLog (taskId, traceId, eventType, payloadJson, createdAt) "
        "VALUES (?,?,?,?,?)",
        (task_id, trace_id, f"capability.{cap}",
         json.dumps({"status": result["status"]}, ensure_ascii=False), now_utc()),
    )
    conn.commit()
    conn.close()

    json.dump(result, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
