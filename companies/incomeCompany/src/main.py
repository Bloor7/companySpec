#!/usr/bin/env python3
"""incomeCompany — theo dõi thu nhập, cất vào Notion.

Hợp đồng (C1): taskEnvelope trên stdin → companyResult trên stdout.
Không biết gì về CEO hay Telegram.

Dữ liệu THẬT nằm ở Notion. store.sqlite ở đây chỉ giữ nhật ký công việc (C3).

Company này KHÔNG biết gì về chi tiêu. Muốn biết "còn dư bao nhiêu" thì CEO gọi
thêm expenseCompany.sumExpenses rồi tự trừ — phép trừ không để lại dấu vết nên
CEO được tự làm.
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
    dbid = os.environ.get("NOTION_INCOME_DATABASE_ID", "")
    if not dbid:
        raise notion.NotionError(
            "Thiếu NOTION_INCOME_DATABASE_ID. Chạy: python3 ops/setup-notion.py"
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


def row_to_income(page: dict) -> dict:
    props = page.get("properties", {})
    return {
        "incomeId": page["id"],
        "amount": notion.plain(props.get("Số tiền")) or 0,
        "nguon": notion.plain(props.get("Nguồn")),
        "note": notion.plain(props.get("Ghi chú")) or "",
        "date": notion.plain(props.get("Ngày")),
        "url": page.get("url", ""),
    }


# ───────────────────────── năng lực ─────────────────────────

def _date_filter(inp):
    frm = inp.get("tuNgay") or month_start()
    to = inp.get("denNgay") or today()
    return frm, to, {"and": [
        {"property": "Ngày", "date": {"on_or_after": frm}},
        {"property": "Ngày", "date": {"on_or_before": to}},
    ]}


def list_incomes(token, inp):
    frm, to, flt = _date_filter(inp)
    if inp.get("nguon"):
        flt["and"].append(
            {"property": "Nguồn", "select": {"equals": inp["nguon"]}})

    pages = notion.query_database(
        token, database_id(), filter_=flt,
        sorts=[{"property": "Ngày", "direction": "descending"}],
        page_size=inp.get("gioiHan", 50),
    )
    items = [row_to_income(p) for p in pages]
    total = sum(i["amount"] or 0 for i in items)
    return (
        {"incomes": items, "count": len(items)},
        f"{frm} → {to}: {len(items)} khoản thu, tổng {money(total)}",
        [],
    )


def sum_incomes(token, inp):
    frm, to, flt = _date_filter(inp)
    pages = notion.query_database(token, database_id(), filter_=flt, page_size=100)
    items = [row_to_income(p) for p in pages]

    by_src: dict = {}
    for it in items:
        src = it["nguon"] or "(chưa phân loại)"
        by_src[src] = by_src.get(src, 0) + (it["amount"] or 0)
    total = sum(by_src.values())

    top = sorted(by_src.items(), key=lambda kv: -kv[1])[:3]
    detail = ", ".join(f"{s} {money(v)}" for s, v in top)
    return (
        {"total": total, "count": len(items), "byNguon": by_src,
         "from": frm, "to": to},
        f"{frm} → {to}: tổng thu {money(total)} qua {len(items)} khoản. "
        + (f"Lớn nhất: {detail}." if top else "Chưa có khoản nào."),
        [],
    )


def add_income(token, inp):
    date = inp.get("ngay") or bay_gio_iso()
    note = inp.get("ghiChu", "")
    title = note or inp["nguon"]

    page = notion.create_page(token, database_id(), {
        "Tên":     notion.title_prop(title),
        "Số tiền": notion.number_prop(inp["soTien"]),
        "Nguồn":   notion.select_prop(inp["nguon"]),
        "Ngày":    notion.date_prop(date),
        "Ghi chú": notion.text_prop(note),
    })

    return (
        {"incomeId": page["id"], "amount": inp["soTien"],
         "nguon": inp["nguon"], "date": date, "url": page.get("url", "")},
        f'Đã ghi thu {money(inp["soTien"])} · {inp["nguon"]} · {date}',
        # D3 — ghi lên Notion là tác động ra ngoài thật, phải khai
        [{"type": "notion.createPage", "target": page["id"],
          "idempotencyKey": f'{date}|{inp["nguon"]}|{inp["soTien"]}|{note}',
          "reversible": True}],
    )


def delete_income(token, inp):
    """Xoá một khoản thu, nhưng chỉ khi nó đúng là khoản admin đã duyệt.

    D5 — chép toàn bộ nội dung cũ vào previousValue. Xoá mà không chép lại thì
    "khôi phục được trong 30 ngày" chỉ đúng trên lý thuyết.
    """
    page = notion.get_page(token, inp["incomeId"])
    if page.get("archived"):
        raise ValueError("Khoản thu này đã bị xoá trước đó rồi.")
    cur = row_to_income(page)

    # Đối chiếu với thứ admin đã nhìn thấy lúc bấm duyệt. Lệch một chi tiết là
    # dừng — thà không xoá còn hơn xoá nhầm.
    if float(cur["amount"] or 0) != float(inp["soTien"]):
        raise ValueError(
            f"Không khớp: khoản đó là {money(cur['amount'] or 0)}, "
            f"không phải {money(inp['soTien'])}. Em không xoá.")
    # So NGÀY với NGÀY — xem chú thích dài ở expenseCompany.delete_expense.
    # Notion trả cả giờ, schema ép `ngay` đúng 10 ký tự, nên so nguyên chuỗi
    # thì không khoản thu nào xoá được.
    if (cur["date"] or "")[:10] != inp["ngay"]:
        raise ValueError(
            f"Không khớp: khoản đó ngày {(cur['date'] or '')[:10]}, "
            f"không phải {inp['ngay']}. Em không xoá.")

    notion.archive_page(token, inp["incomeId"])
    truoc = f'{cur["date"]}|{cur["amount"]}|{cur["nguon"]}|{cur["note"]}'
    return (
        {"incomeId": inp["incomeId"], "amount": cur["amount"],
         "nguon": cur["nguon"], "date": cur["date"], "note": cur["note"]},
        f'Đã xoá khoản thu {money(cur["amount"] or 0)} · {cur["nguon"]} · {(cur["date"] or "")[:10]}'
        + (f' ({cur["note"]})' if cur["note"] else "")
        + ". Notion giữ trong thùng rác 30 ngày.",
        [{"type": "notion.archivePage", "target": inp["incomeId"],
          "idempotencyKey": f'delete|{inp["incomeId"]}',
          "reversible": True, "previousValue": truoc}],
    )


HANDLERS = {"listIncomes": list_incomes, "sumIncomes": sum_incomes,
            "addIncome": add_income, "deleteIncome": delete_income}


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
            raise ValueError(f"incomeCompany không có năng lực '{cap}'")

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
                      summary=f"incomeCompany hỏng khi chạy {cap}.")

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
