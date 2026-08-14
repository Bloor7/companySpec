#!/usr/bin/env python3
"""savingsCompany — quỹ tiết kiệm có mục tiêu, cất vào Notion.

Hợp đồng (C1): taskEnvelope trên stdin → companyResult trên stdout.

Mỗi dòng trên Notion là MỘT QUỸ. Nạp/rút là sửa cột "Đã có" của quỹ đó, nên
mọi thao tác ghi đều đọc giá trị cũ trước và khai vào sideEffects.previousValue
(D5) — không có nó thì con số cũ biến mất và không ai hoàn tác được.

Company này không biết gì về thu nhập hay chi tiêu (C3). Câu "tháng này để dành
được bao nhiêu" là việc của CEO: gọi sumIncomes, sumExpenses, fundProgress rồi
tự đối chiếu.
"""
import json
import os
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "lib"))
import notionClient as notion  # noqa: E402
import db  # noqa: E402

STORE = os.path.join(HERE, "..", "store.sqlite")
TZ = timezone(timedelta(hours=7))  # Asia/Ho_Chi_Minh


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> date:
    return datetime.now(TZ).date()


def database_id() -> str:
    dbid = os.environ.get("NOTION_SAVINGS_DATABASE_ID", "")
    if not dbid:
        raise notion.NotionError(
            "Thiếu NOTION_SAVINGS_DATABASE_ID. Chạy: python3 ops/setup-notion.py"
        )
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


def bar(pct: float, width: int = 10) -> str:
    """Thanh tiến độ bằng ký tự khối.

    Dùng khối chứ không dùng bảng: Telegram render font tỉ lệ nên cột căn bằng
    khoảng trắng sẽ lệch, còn ký tự khối thì rộng đều nhau ở mọi máy. Đây cũng
    không phải Markdown — CEO bị cấm Markdown vì nó hiện ra ký tự thô.

    Làm tròn xuống, nhưng đã có đồng nào thì hiện ít nhất một ô: 0,4% mà vẽ
    thanh rỗng thì admin tưởng chưa góp gì.
    """
    pct = max(0.0, min(100.0, pct or 0.0))
    filled = int(pct / 100 * width)
    if pct > 0 and filled == 0:
        filled = 1
    return "█" * filled + "░" * (width - filled)


def months_left(han: str | None) -> int | None:
    """Số tháng còn lại tới hạn, tối thiểu 1.

    Trả 1 khi hạn đã qua hoặc còn dưới một tháng: chia cho 0 thì vỡ, mà chia cho
    một số âm thì ra lời khuyên vô nghĩa ("mỗi tháng để dành -3 triệu").
    """
    if not han:
        return None
    try:
        d = datetime.strptime(han[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    days = (d - today()).days
    return max(1, round(days / 30.44))


def row_to_fund(page: dict) -> dict:
    props = page.get("properties", {})
    muc_tieu = notion.plain(props.get("Mục tiêu")) or 0
    da_co = notion.plain(props.get("Đã có")) or 0
    han = notion.plain(props.get("Hạn"))
    con_thieu = max(0, muc_tieu - da_co)
    thang = months_left(han)
    phan_tram = round(da_co / muc_tieu * 100, 1) if muc_tieu else 0.0
    return {
        "fundId": page["id"],
        "ten": notion.plain(props.get("Tên")) or "",
        "loai": notion.plain(props.get("Loại")),
        "mucTieu": muc_tieu,
        "daCo": da_co,
        "conThieu": con_thieu,
        "phanTram": phan_tram,
        # Company vẽ sẵn thanh, KHÔNG để CEO tự vẽ: thanh vẽ từ số nào thì phải
        # đúng số đó. CEO tự vẽ là một chỗ nữa để bịa (§ "Đừng bịa").
        "thanh": bar(phan_tram),
        "han": han,
        "thangConLai": thang,
        # Con số hành động được: mỗi tháng bỏ vào bao nhiêu thì kịp hạn.
        "canMoiThang": round(con_thieu / thang) if (thang and con_thieu) else 0,
        "trangThai": notion.plain(props.get("Trạng thái")),
        "ghiChu": notion.plain(props.get("Ghi chú")) or "",
        "url": page.get("url", ""),
    }


def fetch_funds(token, loai=None, trang_thai=None, limit=100) -> list:
    conds = []
    if loai:
        conds.append({"property": "Loại", "select": {"equals": loai}})
    if trang_thai:
        conds.append({"property": "Trạng thái", "select": {"equals": trang_thai}})
    flt = {"and": conds} if conds else None
    pages = notion.query_database(token, database_id(), filter_=flt,
                                  page_size=limit)
    return [row_to_fund(p) for p in pages]


def load_fund(token, fund_id: str, ten_quy: str) -> dict:
    """Đọc một quỹ và ĐỐI CHIẾU tên với thứ admin đã nhìn thấy lúc bấm duyệt.

    D7 — id thì đúng máy nhưng không đọc được; tên thì đọc được nhưng trùng được.
    Bắt cả hai khớp thì CEO không thể nạp nhầm quỹ mà admin vẫn tưởng đã duyệt.
    """
    page = notion.get_page(token, fund_id)
    if page.get("archived"):
        raise ValueError("Quỹ này đã bị xoá trước đó rồi.")
    fund = row_to_fund(page)
    if fund["ten"].strip().lower() != ten_quy.strip().lower():
        raise ValueError(
            f"Không khớp: quỹ đó tên '{fund['ten']}', không phải '{ten_quy}'. "
            "Em không đụng vào.")
    return fund


def apply_balance(token, fund: dict, new_amount: float):
    """Ghi số dư mới; đủ mục tiêu thì tự chuyển 'đã đạt', tụt xuống thì về 'đang góp'."""
    props = {"Đã có": notion.number_prop(new_amount)}
    trang_thai = fund["trangThai"]
    if fund["mucTieu"] and trang_thai != "tạm dừng":
        muon = "đã đạt" if new_amount >= fund["mucTieu"] else "đang góp"
        if muon != trang_thai:
            props["Trạng thái"] = notion.select_prop(muon)
            trang_thai = muon
    notion.update_page(token, fund["fundId"], props)
    return trang_thai


def balance_result(fund, new_amount, trang_thai):
    muc_tieu = fund["mucTieu"]
    return {
        "fundId": fund["fundId"], "ten": fund["ten"],
        "daCo": new_amount, "previousDaCo": fund["daCo"],
        "mucTieu": muc_tieu,
        "phanTram": round(new_amount / muc_tieu * 100, 1) if muc_tieu else 0.0,
        "trangThai": trang_thai,
        "conThieu": max(0, muc_tieu - new_amount),
    }


# ───────────────────────── năng lực ─────────────────────────

def fund_lines(funds: list, limit: int = 6) -> str:
    """Mỗi quỹ hai dòng: tên + thanh, rồi số liệu.

    Hai dòng chứ không phải một bảng — admin đọc trên điện thoại, dòng dài bị
    ngắt lung tung thì thanh tiến độ rơi xuống giữa chừng và mất hết tác dụng.
    """
    out = []
    for f in funds[:limit]:
        so = [f'còn {money(f["conThieu"])}'] if f["conThieu"] else ["đã đủ"]
        if f["thangConLai"]:
            so.append(f'{f["thangConLai"]} tháng nữa')
        if f["canMoiThang"]:
            so.append(f'cần {money(f["canMoiThang"])}/tháng')
        # Làm tròn nguyên cho khớp dòng tổng ở trên; số lẻ vẫn nằm trong output
        # để CEO trả lời được nếu admin hỏi kỹ.
        out.append(f'{f["ten"]} {f["thanh"]} {round(f["phanTram"])}%\n'
                   + " · ".join(so))
    if len(funds) > limit:
        out.append(f"…và {len(funds) - limit} quỹ nữa.")
    return "\n\n".join(out)


def list_funds(token, inp):
    funds = fetch_funds(token, inp.get("loai"), inp.get("trangThai"),
                        inp.get("gioiHan", 50))
    funds.sort(key=lambda f: (-(f["phanTram"] or 0), f["ten"]))
    tong = sum(f["daCo"] for f in funds)
    return (
        {"funds": funds, "count": len(funds)},
        (f"{len(funds)} quỹ, đang giữ tổng {money(tong)}\n\n"
         + fund_lines(funds)) if funds else "Chưa có quỹ nào.",
        [],
    )


def fund_progress(token, inp):
    funds = fetch_funds(token, inp.get("loai"))
    dang_chay = [f for f in funds if f["trangThai"] != "tạm dừng"]

    tong_da_co = sum(f["daCo"] for f in funds)
    tong_muc_tieu = sum(f["mucTieu"] for f in funds)
    can_thang = sum(f["canMoiThang"] for f in dang_chay)

    by_loai: dict = {}
    for f in funds:
        k = f["loai"] or "(chưa phân loại)"
        cur = by_loai.setdefault(k, {"daCo": 0, "mucTieu": 0, "soQuy": 0})
        cur["daCo"] += f["daCo"]
        cur["mucTieu"] += f["mucTieu"]
        cur["soQuy"] += 1

    # Hạn gần nhất lên đầu: quỹ sắp tới hạn mới là quỹ cần hành động tháng này.
    funds.sort(key=lambda f: (f["thangConLai"] is None, f["thangConLai"] or 0))
    pct_tong = round(tong_da_co / tong_muc_tieu * 100, 1) if tong_muc_tieu else 0.0

    dau = f"{len(funds)} quỹ {bar(pct_tong)} {round(pct_tong)}%\n" \
          f"đã có {money(tong_da_co)} / {money(tong_muc_tieu)}"
    if can_thang:
        dau += f"\nĐể kịp mọi hạn: {money(can_thang)}/tháng."

    than = ""
    if inp.get("nhacNap") and can_thang:
        # Kết bằng một câu hỏi, không phải một dấu chấm: admin trả lời được ngay
        # trong Telegram thì việc nạp quỹ mới thật sự xảy ra.
        than = (f"\n\nTháng này nạp bao nhiêu vào quỹ? Nhắn em số tiền là em ghi. "
                f"Bỏ qua tháng này cũng được — em tính lại cho kịp hạn.")

    return (
        {"tongDaCo": tong_da_co, "tongMucTieu": tong_muc_tieu,
         "phanTram": pct_tong,
         "canMoiThang": can_thang, "byLoai": by_loai, "funds": funds},
        (dau + "\n\n" + fund_lines(funds) + than) if funds else "Chưa có quỹ nào.",
        [],
    )


def create_fund(token, inp):
    da_co = inp.get("daCo", 0)
    muc_tieu = inp["mucTieu"]
    props = {
        "Tên":        notion.title_prop(inp["ten"]),
        "Loại":       notion.select_prop(inp["loai"]),
        "Mục tiêu":   notion.number_prop(muc_tieu),
        "Đã có":      notion.number_prop(da_co),
        "Trạng thái": notion.select_prop(
            "đã đạt" if muc_tieu and da_co >= muc_tieu else "đang góp"),
        "Ghi chú":    notion.text_prop(inp.get("ghiChu", "")),
    }
    if inp.get("han"):
        props["Hạn"] = notion.date_prop(inp["han"])

    page = notion.create_page(token, database_id(), props)
    thang = months_left(inp.get("han"))
    con_thieu = max(0, muc_tieu - da_co)

    return (
        {"fundId": page["id"], "ten": inp["ten"], "loai": inp["loai"],
         "mucTieu": muc_tieu, "daCo": da_co, "han": inp.get("han"),
         "url": page.get("url", "")},
        f'Đã mở quỹ "{inp["ten"]}" ({inp["loai"]}) · mục tiêu {money(muc_tieu)}'
        + (f", đã có {money(da_co)}" if da_co else "")
        + (f". Còn {thang} tháng tới hạn, cần {money(con_thieu / thang)}/tháng."
           if thang and con_thieu else "."),
        # D3 — ghi lên Notion là tác động ra ngoài thật
        [{"type": "notion.createPage", "target": page["id"],
          "idempotencyKey": f'quy|{inp["ten"]}|{muc_tieu}',
          "reversible": True}],
    )


def deposit_fund(token, inp):
    fund = load_fund(token, inp["fundId"], inp["tenQuy"])
    new_amount = fund["daCo"] + inp["soTien"]
    trang_thai = apply_balance(token, fund, new_amount)
    out = balance_result(fund, new_amount, trang_thai)

    # Không emoji: summary này được CEO đọc lại cho admin trên Telegram.
    xong = " Đủ mục tiêu rồi." if trang_thai == "đã đạt" \
        and fund["trangThai"] != "đã đạt" else ""
    return (
        out,
        f'Đã nạp {money(inp["soTien"])} vào quỹ "{fund["ten"]}": '
        f'{money(fund["daCo"])} → {money(new_amount)}'
        + (f'/{money(fund["mucTieu"])} ({out["phanTram"]}%)' if fund["mucTieu"] else "")
        + "." + xong,
        # D5 — số cũ phải nằm trong previousValue, nếu không thì không hoàn tác được
        [{"type": "notion.updatePage", "target": fund["fundId"],
          "idempotencyKey": f'nap|{fund["fundId"]}|{inp["soTien"]}|{today()}',
          "reversible": True,
          "previousValue": f'Đã có={fund["daCo"]}|Trạng thái={fund["trangThai"]}'}],
    )


def withdraw_fund(token, inp):
    fund = load_fund(token, inp["fundId"], inp["tenQuy"])
    if inp["soTien"] > fund["daCo"]:
        raise ValueError(
            f'Quỹ "{fund["ten"]}" chỉ đang có {money(fund["daCo"])}, '
            f'không rút được {money(inp["soTien"])}.')

    new_amount = fund["daCo"] - inp["soTien"]
    trang_thai = apply_balance(token, fund, new_amount)
    out = balance_result(fund, new_amount, trang_thai)

    return (
        out,
        f'Đã rút {money(inp["soTien"])} khỏi quỹ "{fund["ten"]}": '
        f'{money(fund["daCo"])} → {money(new_amount)}'
        + (f'/{money(fund["mucTieu"])} ({out["phanTram"]}%)' if fund["mucTieu"] else "")
        + ".",
        [{"type": "notion.updatePage", "target": fund["fundId"],
          "idempotencyKey": f'rut|{fund["fundId"]}|{inp["soTien"]}|{today()}',
          "reversible": True,
          "previousValue": f'Đã có={fund["daCo"]}|Trạng thái={fund["trangThai"]}'}],
    )


HANDLERS = {"listFunds": list_funds, "fundProgress": fund_progress,
            "createFund": create_fund, "depositFund": deposit_fund,
            "withdrawFund": withdraw_fund}


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
            raise ValueError(f"savingsCompany không có năng lực '{cap}'")

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
        # Dữ liệu không dùng được (sai tên quỹ, rút quá số dư) — nói rõ để hỏi lại,
        # tuyệt đối không đoán rồi làm bừa.
        result.update(status="needsInput", error=str(exc), summary=str(exc))
    except Exception as exc:  # O3 — hỏng thì hỏng to
        result.update(status="failed", error=f"{type(exc).__name__}: {exc}",
                      summary=f"savingsCompany hỏng khi chạy {cap}.")

    duration = int((time.time() - started) * 1000)
    result["usage"] = {"steps": 1, "durationMs": duration, "costUsd": 0.0}

    conn.execute(
        "UPDATE taskLog SET status=?, summary=?, finishedAt=?, durationMs=?, costUsd=? "
        "WHERE taskId=?",
        (result["status"], result["summary"], now_utc(), duration, 0.0, task_id),
    )
    # Lịch sử nạp/rút sống ở đây (C3) — Notion chỉ giữ số dư hiện tại.
    conn.execute(
        "INSERT INTO eventLog (taskId, traceId, eventType, payloadJson, createdAt) "
        "VALUES (?,?,?,?,?)",
        (task_id, trace_id, f"capability.{cap}",
         json.dumps({"status": result["status"], "input": inp,
                     "output": result["output"]}, ensure_ascii=False), now_utc()),
    )
    conn.commit()
    conn.close()

    json.dump(result, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
