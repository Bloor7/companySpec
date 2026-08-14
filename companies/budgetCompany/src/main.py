#!/usr/bin/env python3
"""budgetCompany — hạn mức chi tiêu theo tháng.

Hợp đồng (C1): taskEnvelope trên stdin → companyResult trên stdout.

Mỗi dòng trên Notion là một hạn mức: tháng + danh mục + số tiền.
Company này KHÔNG đọc sổ chi tiêu (C3) — nó chỉ biết dự định, không biết thực tế.
Ghép hai nửa là việc của CEO hoặc của báo cáo định kỳ, những nơi được phép gọi
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


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def thang_nay() -> str:
    return datetime.now(TZ).strftime("%Y-%m")


def bay_gio_iso() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%dT%H:%M:%S+07:00")


def database_id() -> str:
    dbid = os.environ.get("NOTION_BUDGET_DATABASE_ID", "")
    if not dbid:
        raise notion.NotionError(
            "Thiếu NOTION_BUDGET_DATABASE_ID. Chạy: python3 ops/setup-notion.py")
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


def row_to_budget(page: dict) -> dict:
    props = page.get("properties", {})
    return {
        "budgetId": page["id"],
        "thang": notion.plain(props.get("Tháng")) or "",
        "danhMuc": notion.plain(props.get("Danh mục")),
        "hanMuc": notion.plain(props.get("Hạn mức")) or 0,
        # Mốc để đếm "đã tiêu bao nhiêu phần hạn mức" — xem chú thích ở setup-notion.
        "datLuc": notion.plain(props.get("Đặt lúc")),
        "ghiChu": notion.plain(props.get("Ghi chú")) or "",
    }


def fetch(token, thang: str) -> list:
    pages = notion.query_database(
        token, database_id(), page_size=100,
        filter_={"property": "Tháng", "rich_text": {"equals": thang}})
    items = [row_to_budget(p) for p in pages]
    items.sort(key=lambda b: -b["hanMuc"])
    return items


# ───────────────────────── năng lực ─────────────────────────

def get_budget(token, inp):
    thang = inp.get("thang") or thang_nay()
    items = fetch(token, thang)
    han = {b["danhMuc"]: b["hanMuc"] for b in items if b["danhMuc"]}
    tu = {b["danhMuc"]: b["datLuc"] for b in items if b["danhMuc"]}
    tong = sum(han.values())

    if not items:
        return ({"thang": thang, "hanMuc": {}, "tong": 0, "count": 0, "items": []},
                f"Tháng {thang} chưa đặt hạn mức nào.", [])

    dong = [f'{b["danhMuc"]}: {money(b["hanMuc"])}' for b in items]
    return (
        {"thang": thang, "hanMuc": han, "datLuc": tu, "tong": tong,
         "count": len(items), "items": items},
        f"Hạn mức tháng {thang} — tổng {money(tong)}:\n" + "\n".join(dong),
        [],
    )


def set_budget(token, inp):
    thang = inp.get("thang") or thang_nay()
    items = fetch(token, thang)
    cu = next((b for b in items if b["danhMuc"] == inp["danhMuc"]), None)

    props = {
        "Tên":      notion.title_prop(f'{thang} · {inp["danhMuc"]}'),
        "Tháng":    notion.text_prop(thang),
        "Danh mục": notion.select_prop(inp["danhMuc"]),
        "Hạn mức":  notion.number_prop(inp["hanMuc"]),
        "Đặt lúc":  notion.date_prop(bay_gio_iso()),
        "Ghi chú":  notion.text_prop(inp.get("ghiChu", "")),
    }

    if cu:
        notion.update_page(token, cu["budgetId"], props)
        truoc, kieu, target = cu["hanMuc"], "notion.updatePage", cu["budgetId"]
    else:
        page = notion.create_page(token, database_id(), props)
        truoc, kieu, target = None, "notion.createPage", page["id"]

    tong = sum(b["hanMuc"] for b in fetch(token, thang))
    lam = "Đã đổi" if cu else "Đã đặt"
    return (
        {"thang": thang, "danhMuc": inp["danhMuc"], "hanMuc": inp["hanMuc"],
         "previous": truoc, "tong": tong},
        f'{lam} hạn mức {inp["danhMuc"]} tháng {thang}: {money(inp["hanMuc"])}'
        + (f" (trước là {money(truoc)})" if truoc is not None else "")
        + f". Tổng ngân sách tháng: {money(tong)}.",
        # D5 — ghi đè thì chép lại giá trị cũ.
        [{"type": kieu, "target": target,
          "idempotencyKey": f'budget|{thang}|{inp["danhMuc"]}|{inp["hanMuc"]}',
          "reversible": True,
          "previousValue": (str(truoc) if truoc is not None else None)}],
    )


def copy_budget(token, inp):
    nguon = fetch(token, inp["tuThang"])
    if not nguon:
        raise ValueError(f'Tháng {inp["tuThang"]} không có hạn mức nào để chép.')
    da_co = fetch(token, inp["denThang"])
    if da_co:
        raise ValueError(
            f'Tháng {inp["denThang"]} đã có {len(da_co)} hạn mức rồi. '
            "Xoá bớt trước, hoặc đặt từng danh mục bằng setBudget.")

    side = []
    for b in nguon:
        page = notion.create_page(token, database_id(), {
            "Tên":      notion.title_prop(f'{inp["denThang"]} · {b["danhMuc"]}'),
            "Tháng":    notion.text_prop(inp["denThang"]),
            "Danh mục": notion.select_prop(b["danhMuc"]),
            "Hạn mức":  notion.number_prop(b["hanMuc"]),
            "Đặt lúc":  notion.date_prop(bay_gio_iso()),
            "Ghi chú":  notion.text_prop(b["ghiChu"]),
        })
        side.append({"type": "notion.createPage", "target": page["id"],
                     "idempotencyKey": f'copy|{inp["denThang"]}|{b["danhMuc"]}',
                     "reversible": True})

    tong = sum(b["hanMuc"] for b in nguon)
    return (
        {"tuThang": inp["tuThang"], "denThang": inp["denThang"],
         "soDanhMuc": len(nguon), "tong": tong},
        f'Đã chép {len(nguon)} hạn mức từ {inp["tuThang"]} sang {inp["denThang"]}, '
        f"tổng {money(tong)}.",
        side,
    )


def delete_budget(token, inp):
    thang = inp.get("thang") or thang_nay()
    cu = next((b for b in fetch(token, thang) if b["danhMuc"] == inp["danhMuc"]),
              None)
    if cu is None:
        raise ValueError(f'Tháng {thang} không có hạn mức cho "{inp["danhMuc"]}".')

    # Đối chiếu với thứ admin đã nhìn thấy lúc bấm duyệt (D7).
    if float(cu["hanMuc"]) != float(inp["hanMuc"]):
        raise ValueError(
            f'Không khớp: hạn mức {inp["danhMuc"]} đang là {money(cu["hanMuc"])}, '
            f'không phải {money(inp["hanMuc"])}. Em không xoá.')

    notion.archive_page(token, cu["budgetId"])
    return (
        {"thang": thang, "danhMuc": cu["danhMuc"], "hanMuc": cu["hanMuc"]},
        f'Đã bỏ hạn mức {cu["danhMuc"]} tháng {thang} ({money(cu["hanMuc"])}). '
        "Notion giữ trong thùng rác 30 ngày.",
        [{"type": "notion.archivePage", "target": cu["budgetId"],
          "idempotencyKey": f'delbudget|{thang}|{cu["danhMuc"]}',
          "reversible": True,
          "previousValue": f'{thang}|{cu["danhMuc"]}|{cu["hanMuc"]}'}],
    )


HANDLERS = {"getBudget": get_budget, "setBudget": set_budget,
            "copyBudget": copy_budget, "deleteBudget": delete_budget}


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
            raise ValueError(f"budgetCompany không có năng lực '{cap}'")

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
                      summary=f"budgetCompany hỏng khi chạy {cap}.")

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
