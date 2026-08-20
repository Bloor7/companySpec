#!/usr/bin/env python3
"""expenseCompany — theo dõi chi tiêu, cất vào Notion.

Hợp đồng (C1): taskEnvelope trên stdin → companyResult trên stdout.
Không biết gì về CEO hay Telegram.

Dữ liệu THẬT nằm ở Notion (bộ nhớ thứ hai của admin).
store.sqlite ở đây chỉ giữ nhật ký công việc (C3) — không nhân bản dữ liệu,
để không bao giờ có hai nguồn sự thật lệch nhau.
"""
import json
import os
import sqlite3
import sys
import unicodedata
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "lib"))
import notionClient as notion  # noqa: E402
import db  # noqa: E402

STORE = os.path.join(HERE, "..", "store.sqlite")
TZ = timezone(timedelta(hours=7))  # Asia/Ho_Chi_Minh — ngày theo giờ admin sống


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def bay_gio_iso() -> str:
    """Thời điểm ghi, CÓ GIỜ.

    Ví giữ mốc kiểm kê kèm giờ; muốn biết khoản nào xảy ra trước/sau lúc admin
    đếm tiền thì khoản đó cũng phải có giờ. Chỉ có ngày thì mọi giao dịch trong
    ngày đều "bằng nhau" và số dư tính ra sai (đo được 2026-08-04).
    Admin nêu ngày cụ thể ("hôm qua") thì vẫn ghi ngày trần, không bịa giờ.
    """
    return datetime.now(TZ).strftime("%Y-%m-%dT%H:%M:%S+07:00")


def month_start() -> str:
    return datetime.now(TZ).strftime("%Y-%m-01")


def database_id() -> str:
    dbid = os.environ.get("NOTION_EXPENSE_DATABASE_ID", "")
    if not dbid:
        raise notion.NotionError(
            "Thiếu NOTION_EXPENSE_DATABASE_ID. Chạy: python3 ops/setup-notion.py"
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


def row_to_expense(page: dict) -> dict:
    props = page.get("properties", {})
    return {
        "expenseId": page["id"],
        "amount": notion.plain(props.get("Số tiền")) or 0,
        "category": notion.plain(props.get("Danh mục")),
        "note": notion.plain(props.get("Ghi chú")) or "",
        "date": notion.plain(props.get("Ngày")),
        "url": page.get("url", ""),
    }


# ───────────────────────── năng lực ─────────────────────────

def add_expense(token, inp):
    date = inp.get("ngay") or bay_gio_iso()
    note = inp.get("ghiChu", "")
    title = note or inp["danhMuc"]

    page = notion.create_page(token, database_id(), {
        "Tên":      notion.title_prop(title),
        "Số tiền":  notion.number_prop(inp["soTien"]),
        "Danh mục": notion.select_prop(inp["danhMuc"]),
        "Ngày":     notion.date_prop(date),
        "Ghi chú":  notion.text_prop(note),
    })

    return (
        {"expenseId": page["id"], "amount": inp["soTien"],
         "category": inp["danhMuc"], "date": date, "url": page.get("url", "")},
        f'Đã ghi {money(inp["soTien"])} · {inp["danhMuc"]} · {date}',
        # D3 — ghi lên Notion là tác động ra ngoài thật, phải khai
        [{"type": "notion.createPage", "target": page["id"],
          "idempotencyKey": f'{date}|{inp["danhMuc"]}|{inp["soTien"]}|{note}',
          "reversible": True}],
    )


def _date_filter(inp):
    frm = inp.get("tuNgay") or month_start()
    to = inp.get("denNgay") or today()
    return frm, to, {"and": [
        {"property": "Ngày", "date": {"on_or_after": frm}},
        {"property": "Ngày", "date": {"on_or_before": to}},
    ]}


def _bo_dau(t: str) -> str:
    """Bỏ dấu tiếng Việt để so chữ.

    Admin gõ "bach hoa xanh" nhưng ghi chú lưu "Bách Hoá Xanh" — so nguyên bản
    thì trượt. Và trượt ở đây im lặng: trả về 0 khoản trông y hệt "không có
    khoản nào", nên admin tin là sổ không có thật.
    """
    t = unicodedata.normalize("NFD", (t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").replace("đ", "d")


def list_expenses(token, inp):
    frm, to, flt = _date_filter(inp)
    if inp.get("danhMuc"):
        flt["and"].append(
            {"property": "Danh mục", "select": {"equals": inp["danhMuc"]}})

    tu_khoa = (inp.get("tuKhoa") or "").strip()
    # Lấy rộng hơn khi có từ khoá, vì lọc chữ làm ở đây chứ không ở Notion:
    # `contains` của Notion phân biệt dấu nên "bach hoa" không khớp "Bách Hoá".
    # Lấy đúng `gioiHan` rồi mới lọc thì admin xin 20 khoản BHX mà chỉ nhận
    # được số khoản BHX nằm trong 20 dòng gần nhất — thiếu mà trông như đủ.
    page_size = 100 if tu_khoa else inp.get("gioiHan", 50)

    pages = notion.query_database(
        token, database_id(), filter_=flt,
        sorts=[{"property": "Ngày", "direction": "descending"}],
        page_size=page_size,
    )
    items = [row_to_expense(p) for p in pages]

    da_loc = False
    if tu_khoa:
        can = _bo_dau(tu_khoa)
        items = [i for i in items if can in _bo_dau(i.get("note") or "")]
        items = items[: inp.get("gioiHan", 50)]
        da_loc = True

    total = sum(i["amount"] or 0 for i in items)
    tom = f"{frm} → {to}: {len(items)} khoản, tổng {money(total)}"
    if da_loc:
        tom = (f'{frm} → {to}, lọc theo "{tu_khoa}": {len(items)} khoản, '
               f"tổng {money(total)}")
        if not items:
            # O10 — nói rõ VÌ SAO rỗng. "0 khoản" trơ trọi bị đọc thành "không
            # tiêu gì", trong khi sự thật thường là khoản đó ghi mà KHÔNG có
            # ghi chú, nên tìm theo chữ không ra.
            tom += (". Không thấy khoản nào có chữ đó trong ghi chú — có thể "
                    "khoản đó đã ghi nhưng để trống ghi chú, thử tra theo ngày.")
    return ({"expenses": items, "count": len(items)}, tom, [])


def sum_expenses(token, inp):
    frm, to, flt = _date_filter(inp)
    pages = notion.query_database(token, database_id(), filter_=flt, page_size=100)
    items = [row_to_expense(p) for p in pages]

    by_cat: dict = {}
    for it in items:
        cat = it["category"] or "(chưa phân loại)"
        by_cat[cat] = by_cat.get(cat, 0) + (it["amount"] or 0)
    total = sum(by_cat.values())

    top = sorted(by_cat.items(), key=lambda kv: -kv[1])[:3]
    detail = ", ".join(f"{c} {money(v)}" for c, v in top)
    return (
        {"total": total, "count": len(items), "byCategory": by_cat,
         "from": frm, "to": to},
        f"{frm} → {to}: tổng {money(total)} qua {len(items)} khoản. "
        + (f"Nhiều nhất: {detail}." if top else "Chưa có khoản nào."),
        [],
    )


def delete_expense(token, inp):
    """Xoá một khoản, nhưng chỉ khi nó đúng là khoản admin đã duyệt.

    D5 — ghi lại toàn bộ nội dung cũ vào previousValue. Xoá mà không chép lại
    thì "khôi phục được trong 30 ngày" chỉ đúng trên lý thuyết: không ai nhớ
    khoản vừa mất là khoản nào.
    """
    page = notion.get_page(token, inp["expenseId"])
    if page.get("archived"):
        raise ValueError("Khoản này đã bị xoá trước đó rồi.")
    cur = row_to_expense(page)

    # Đối chiếu với thứ admin đã nhìn thấy lúc bấm duyệt. Lệch một chi tiết là
    # dừng — thà không xoá còn hơn xoá nhầm.
    if float(cur["amount"] or 0) != float(inp["soTien"]):
        raise ValueError(
            f"Không khớp: khoản đó là {money(cur['amount'] or 0)}, "
            f"không phải {money(inp['soTien'])}. Em không xoá.")
    # So NGÀY với NGÀY. Notion trả cả giờ ('2026-08-14T12:20:00.000+07:00',
    # 29 ký tự) trong khi schema ép `ngay` đúng 10 ký tự — nên phép so nguyên
    # chuỗi LUÔN lệch, và không khoản nào xoá được.
    # Đo được 2026-08-14 12:28–12:30: admin xoá một khoản, hệ trả về ba lần
    # `failed` với câu "expenseCompany hỏng khi chạy deleteExpense" — vô nghĩa
    # với admin. Cắt 10 ký tự đầu là đúng ý: admin duyệt câu "xoá 50.000đ ngày
    # 14/08", họ đối chiếu ngày chứ không đối chiếu phút.
    if (cur["date"] or "")[:10] != inp["ngay"]:
        raise ValueError(
            f"Không khớp: khoản đó ngày {(cur['date'] or '')[:10]}, "
            f"không phải {inp['ngay']}. Em không xoá.")

    notion.archive_page(token, inp["expenseId"])
    truoc = f'{cur["date"]}|{cur["amount"]}|{cur["category"]}|{cur["note"]}'
    return (
        {"expenseId": inp["expenseId"], "amount": cur["amount"],
         "category": cur["category"], "date": cur["date"], "note": cur["note"]},
        f'Đã xoá {money(cur["amount"] or 0)} · {cur["category"]} · {(cur["date"] or "")[:10]}'
        + (f' ({cur["note"]})' if cur["note"] else "")
        + ". Notion giữ trong thùng rác 30 ngày.",
        [{"type": "notion.archivePage", "target": inp["expenseId"],
          "idempotencyKey": f'delete|{inp["expenseId"]}',
          "reversible": True, "previousValue": truoc}],
    )


HANDLERS = {"addExpense": add_expense, "listExpenses": list_expenses,
            "sumExpenses": sum_expenses, "deleteExpense": delete_expense}


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
            raise ValueError(f"expenseCompany không có năng lực '{cap}'")

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
        # Dữ liệu admin/CEO đưa vào không dùng được — nói rõ để hỏi lại,
        # tuyệt đối không đoán rồi làm bừa.
        result.update(status="needsInput", error=str(exc), summary=str(exc))
    except Exception as exc:  # O3 — hỏng thì hỏng to
        result.update(status="failed", error=f"{type(exc).__name__}: {exc}",
                      summary=f"expenseCompany hỏng khi chạy {cap}.")

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
