#!/usr/bin/env python3
"""journalCompany — nhật ký, cất vào Notion.

Hợp đồng (C1): taskEnvelope trên stdin → companyResult trên stdout.

Khác expenseCompany ở một chỗ: nội dung nhật ký dài, không nhét vừa property
của Notion (2000 ký tự). Nên nội dung đầy đủ nằm ở THÂN TRANG, còn property
"Trích đoạn" chỉ giữ 300 ký tự đầu để nhìn nhanh trong danh sách.

D1 — listEntries chỉ trả trích đoạn và đường dẫn, không trả toàn văn. Muốn đọc
trọn thì gọi readEntry. Giữ cho envelope luôn nhỏ.
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
PREVIEW = 300


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def days_ago(n: int) -> str:
    return (datetime.now(TZ) - timedelta(days=n)).strftime("%Y-%m-%d")


def database_id() -> str:
    dbid = os.environ.get("NOTION_JOURNAL_DATABASE_ID", "")
    if not dbid:
        raise notion.NotionError(
            "Thiếu NOTION_JOURNAL_DATABASE_ID. Chạy: python3 ops/setup-notion.py")
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


def headline(content: str, date: str) -> str:
    """Tiêu đề trang: câu đầu tiên, gọn lại. Notion hiển thị cái này."""
    first = content.strip().split("\n", 1)[0].strip()
    if len(first) > 70:
        first = first[:67].rstrip() + "…"
    return first or f"Nhật ký {date}"


def row_to_entry(page: dict) -> dict:
    props = page.get("properties", {})
    return {
        "entryId": page["id"],
        "title": notion.plain(props.get("Tiêu đề")) or "",
        "preview": notion.plain(props.get("Trích đoạn")) or "",
        "date": notion.plain(props.get("Ngày")),
        "theme": notion.plain(props.get("Chủ đề")),
        "mood": notion.plain(props.get("Tâm trạng")),
        "url": page.get("url", ""),
    }


# ───────────────────────── năng lực ─────────────────────────

def add_entry(token, inp):
    content = inp["noiDung"].strip()
    date = inp.get("ngay") or today()
    preview = content[:PREVIEW] + ("…" if len(content) > PREVIEW else "")

    props = {
        "Tiêu đề":    notion.title_prop(headline(content, date)),
        "Ngày":       notion.date_prop(date),
        "Chủ đề":     notion.select_prop(inp["chuDe"]),
        "Trích đoạn": notion.text_prop(preview),
    }
    if inp.get("mood"):
        props["Tâm trạng"] = notion.select_prop(inp["mood"])

    page = notion.create_page(token, database_id(), props,
                              children=notion.paragraphs(content))

    words = len(content.split())
    return (
        {"entryId": page["id"], "date": date, "theme": inp["chuDe"],
         "mood": inp.get("mood"), "url": page.get("url", "")},
        f'Đã ghi nhật ký {date} · {inp["chuDe"]} · {words} từ',
        [{"type": "notion.createPage", "target": page["id"],
          "idempotencyKey": f'{date}|{inp["chuDe"]}|{content[:80]}',
          "reversible": True}],
    )


def list_entries(token, inp):
    frm = inp.get("tuNgay") or days_ago(30)
    to = inp.get("denNgay") or today()
    flt = {"and": [
        {"property": "Ngày", "date": {"on_or_after": frm}},
        {"property": "Ngày", "date": {"on_or_before": to}},
    ]}
    if inp.get("chuDe"):
        flt["and"].append({"property": "Chủ đề", "select": {"equals": inp["chuDe"]}})

    pages = notion.query_database(
        token, database_id(), filter_=flt,
        sorts=[{"property": "Ngày", "direction": "descending"}],
        page_size=inp.get("gioiHan", 20),
    )
    entries = [row_to_entry(p) for p in pages]

    themes: dict = {}
    for e in entries:
        themes[e["theme"] or "khác"] = themes.get(e["theme"] or "khác", 0) + 1
    spread = ", ".join(f"{k} {v}" for k, v in
                       sorted(themes.items(), key=lambda kv: -kv[1]))

    return (
        {"entries": entries, "count": len(entries)},
        f"{frm} → {to}: {len(entries)} mục" + (f" ({spread})" if spread else ""),
        [],
    )


def read_entry(token, inp):
    page_id = inp["entryId"]
    page = notion._request("GET", f"/pages/{page_id}", token)
    content = notion.read_paragraphs(notion.block_children(token, page_id))
    meta = row_to_entry(page)
    return (
        {"entryId": page_id, "content": content, "date": meta["date"],
         "theme": meta["theme"], "mood": meta["mood"], "url": meta["url"]},
        f'Mục ngày {meta["date"]} · {meta["theme"]} · {len(content.split())} từ',
        [],
    )


def delete_entry(token, inp):
    """D7 — đối chiếu trước khi xoá. Lệch một chi tiết là dừng."""
    page = notion.get_page(token, inp["entryId"])
    if page.get("archived"):
        raise ValueError("Mục này đã bị xoá trước đó rồi.")
    cur = row_to_entry(page)

    # So NGÀY với NGÀY — xem chú thích dài ở expenseCompany.delete_expense.
    if (cur["date"] or "")[:10] != inp["ngay"]:
        raise ValueError(f"Không khớp: mục đó ngày {(cur['date'] or '')[:10]}, "
                         f"không phải {inp['ngay']}. Tớ không xoá.")
    if cur["theme"] != inp["chuDe"]:
        raise ValueError(f"Không khớp: mục đó chủ đề '{cur['theme']}', "
                         f"không phải '{inp['chuDe']}'. Tớ không xoá.")

    notion.archive_page(token, inp["entryId"])
    # D5 — nội dung đầy đủ ở thân trang vẫn nằm trong thùng rác Notion;
    # ở đây chép lại phần nhận diện để sau còn biết mục vừa mất là mục nào.
    truoc = f'{cur["date"]}|{cur["theme"]}|{cur["mood"]}|{cur["title"][:80]}'
    return (
        {"entryId": inp["entryId"], "date": cur["date"], "theme": cur["theme"],
         "title": cur["title"]},
        f'Đã xoá mục {cur["date"]} · {cur["theme"]} · "{cur["title"][:50]}". '
        "Notion giữ trong thùng rác 30 ngày.",
        [{"type": "notion.archivePage", "target": inp["entryId"],
          "idempotencyKey": f'delete|{inp["entryId"]}',
          "reversible": True, "previousValue": truoc}],
    )


HANDLERS = {"addEntry": add_entry, "listEntries": list_entries,
            "readEntry": read_entry, "deleteEntry": delete_entry}


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
            raise ValueError(f"journalCompany không có năng lực '{cap}'")

        if dry_run:  # W2
            preview = json.dumps(inp, ensure_ascii=False)[:200]
            result.update(status="ok", output=None,
                          summary=f"[dryRun] Sẽ chạy {cap} với {preview}")
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
                      summary=f"journalCompany hỏng khi chạy {cap}.")

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
