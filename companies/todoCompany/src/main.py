#!/usr/bin/env python3
"""todoCompany — việc vặt, cất vào Notion.

Hợp đồng (C1): taskEnvelope trên stdin → companyResult trên stdout.

HAI ĐIỂM THIẾT KẾ ĐÁNG ĐỌC TRƯỚC KHI SỬA:

1. CHỐNG TRÙNG BẰNG CODE, KHÔNG BẰNG LỜI DẶN (P1). Việc kéo từ kế hoạch sang
   mang theo `khoaNguon` — một chuỗi định danh được ở nguồn, ví dụ "plan:stt-42".
   Khoá nằm trong sổ sqlite riêng của company, có UNIQUE. CEO gọi lại mười lần
   thì chín lần sau bị bỏ qua, vì trí nhớ của model không phải chỗ đáng tin để
   giữ "đã thêm việc này chưa".

   Hệ quả cố ý: admin xoá một việc trên Notion thì khoá VẪN còn, nên việc đó
   không tự quay lại. Đúng ý muốn — đã bỏ một lần thì đừng nhét lại mỗi sáng.
   Muốn nó quay lại thì thêm tay, không qua khoá.

2. HỎNG MỘT PHẦN THÌ NÓI RÕ PHẦN NÀO (O10). Thêm 5 việc mà việc thứ 4 hỏng:
   ba việc đầu ĐÃ nằm trên Notion. Ném lỗi cả mẻ ở đây thì dispatcher ghi
   `failed`, CEO báo admin "chưa thêm được", admin thử lại — và ba việc đầu
   thành sáu. Nên gom lỗi lại, trả về đúng số đã tạo, kể tên việc hỏng.
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


def today() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def ngay_sau(n: int) -> str:
    return (datetime.now(TZ) + timedelta(days=n)).strftime("%Y-%m-%d")


def database_id() -> str:
    dbid = os.environ.get("NOTION_TODO_DATABASE_ID", "")
    if not dbid:
        raise notion.NotionError(
            "Thiếu NOTION_TODO_DATABASE_ID. Chạy: python3 ops/setup-notion.py")
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
        -- Khoá chống trùng. PRIMARY KEY là thứ làm cho "gọi lại không nhân đôi"
        -- thành một sự thật của cơ sở dữ liệu, không phải một lời hứa trong prompt.
        CREATE TABLE IF NOT EXISTS nguonKhoa (
          khoaNguon TEXT PRIMARY KEY,
          pageId    TEXT NOT NULL,
          ten       TEXT,
          taoLuc    TEXT NOT NULL
        );
        """
    )
    return conn


def row_to_todo(page: dict) -> dict:
    props = page.get("properties", {})
    return {
        "todoId": page["id"],
        "ten": notion.plain(props.get("Việc")) or "",
        "xong": bool(notion.plain(props.get("Xong"))),
        "uuTien": notion.plain(props.get("Ưu tiên")),
        "han": (notion.plain(props.get("Hạn")) or None),
        "nguon": notion.plain(props.get("Nguồn")) or "",
        "ghiChu": notion.plain(props.get("Ghi chú")) or "",
        "url": page.get("url", ""),
    }


# ───────────────────────── năng lực ─────────────────────────

def list_todos(token, inp):
    trang_thai = inp.get("trangThai") or "chưa xong"
    dieu_kien = []
    if trang_thai != "tất cả":
        dieu_kien.append({"property": "Xong",
                          "checkbox": {"equals": trang_thai == "đã xong"}})
    if inp.get("trongNgay") is not None:
        # Chỉ việc CÓ hạn nằm trong khoảng. Việc không hạn bị loại — đó là ý
        # nghĩa của câu hỏi "sắp tới hạn cái gì".
        dieu_kien.append({"property": "Hạn",
                          "date": {"on_or_before": ngay_sau(inp["trongNgay"])}})

    flt = {"and": dieu_kien} if dieu_kien else None
    pages = notion.query_database(
        token, database_id(), filter_=flt,
        sorts=[{"property": "Hạn", "direction": "ascending"}],
        page_size=inp.get("gioiHan", 30),
    )
    todos = [row_to_todo(p) for p in pages]
    hom_nay = today()
    qua_han = sum(1 for t in todos
                  if not t["xong"] and t["han"] and t["han"][:10] < hom_nay)

    # S7 — summary RỖNG nghĩa là "không có gì để nói", và lịch định kỳ dựa vào
    # đúng quy ước này để im lặng. Không có việc nào mà vẫn nhắn mỗi sáng thì
    # admin sẽ ngừng đọc, rồi bỏ lỡ hôm thật sự có việc.
    if not todos:
        return {"todos": [], "count": 0, "quaHan": 0}, "", []

    gap = ", ".join(t["ten"][:40] for t in todos[:5])
    them = f" (+{len(todos) - 5} việc nữa)" if len(todos) > 5 else ""
    canh = f" · {qua_han} việc QUÁ HẠN" if qua_han else ""
    return (
        {"todos": todos, "count": len(todos), "quaHan": qua_han},
        f"{len(todos)} việc chưa xong{canh}: {gap}{them}",
        [],
    )


def add_todos(token, inp):
    conn = connect()
    uu_tien_chung = inp.get("uuTien") or "thường"
    them, bo_qua, loi = [], 0, []

    for viec in inp["cacViec"]:
        khoa = (viec.get("khoaNguon") or "").strip()
        if khoa:
            da_co = conn.execute(
                "SELECT pageId FROM nguonKhoa WHERE khoaNguon=?", (khoa,)
            ).fetchone()
            if da_co:
                bo_qua += 1
                continue

        props = {
            "Việc":     notion.title_prop(viec["ten"]),
            "Xong":     notion.checkbox_prop(False),
            "Ưu tiên":  notion.select_prop(viec.get("uuTien") or uu_tien_chung),
        }
        if viec.get("han"):
            props["Hạn"] = notion.date_prop(viec["han"])
        if viec.get("nguon"):
            props["Nguồn"] = notion.text_prop(viec["nguon"])
        if viec.get("ghiChu"):
            props["Ghi chú"] = notion.text_prop(viec["ghiChu"])

        try:
            page = notion.create_page(token, database_id(), props)
        except Exception as exc:
            # Không dừng cả mẻ — việc sau có thể vẫn thêm được, và việc trước
            # thì đã nằm trên Notion rồi.
            loi.append(f'{viec["ten"][:60]}: {type(exc).__name__}: {exc}'[:200])
            continue

        if khoa:
            conn.execute(
                "INSERT OR REPLACE INTO nguonKhoa (khoaNguon, pageId, ten, taoLuc) "
                "VALUES (?,?,?,?)", (khoa, page["id"], viec["ten"], now_utc()))
            conn.commit()
        them.append({**row_to_todo(page)})

    conn.close()

    if not them and loi:
        # Không tạo được gì cả thì đây là hỏng thật, để dispatcher ghi failed.
        raise notion.NotionError("Không thêm được việc nào. " + " | ".join(loi))

    phan = [f"Đã thêm {len(them)} việc"]
    if bo_qua:
        phan.append(f"bỏ qua {bo_qua} việc đã có")
    if loi:
        phan.append(f"HỎNG {len(loi)}: " + " | ".join(loi))
    return (
        {"themMoi": len(them), "boQua": bo_qua, "todos": them, "loi": loi},
        " · ".join(phan),
        [{"type": "notion.createPage", "target": t["todoId"],
          "idempotencyKey": f'todo|{t["ten"][:80]}',
          "reversible": True} for t in them],
    )


def done_todos(token, inp):
    xong = inp.get("xong", True)
    doi, loi = [], []

    for viec in inp["cacViec"]:
        try:
            page = notion.get_page(token, viec["todoId"])
            cur = row_to_todo(page)
            # D7 — đối chiếu trước khi sửa. Admin duyệt dựa trên TÊN việc; nếu
            # todoId trỏ sang việc khác thì dừng, đừng tick nhầm.
            if cur["ten"].strip() != viec["ten"].strip():
                raise ValueError(
                    f'không khớp: id đó là việc "{cur["ten"][:60]}", '
                    f'không phải "{viec["ten"][:60]}"')
            if cur["xong"] == xong:
                continue  # đã ở đúng trạng thái rồi, không tính là một thay đổi
            notion.update_page(token, viec["todoId"],
                               {"Xong": notion.checkbox_prop(xong)})
            doi.append({**cur, "xong": xong})
        except Exception as exc:
            loi.append(f'{viec["ten"][:60]}: {exc}'[:200])

    if not doi and loi:
        raise ValueError("Không đổi được việc nào. " + " | ".join(loi))

    tu = "xong" if xong else "chưa xong"
    phan = [f"Đã đánh dấu {len(doi)} việc {tu}"]
    if loi:
        phan.append(f"HỎNG {len(loi)}: " + " | ".join(loi))
    return (
        {"daDoi": len(doi), "todos": doi, "loi": loi},
        " · ".join(phan),
        [{"type": "notion.updatePage", "target": t["todoId"],
          "idempotencyKey": f'done|{t["todoId"]}|{xong}',
          "reversible": True, "previousValue": f'xong={not xong}'} for t in doi],
    )


def delete_todo(token, inp):
    """D7 — đối chiếu trước khi xoá. Lệch một chi tiết là dừng."""
    page = notion.get_page(token, inp["todoId"])
    if page.get("archived"):
        raise ValueError("Việc này đã bị xoá trước đó rồi.")
    cur = row_to_todo(page)
    if cur["ten"].strip() != inp["ten"].strip():
        raise ValueError(f'Không khớp: id đó là việc "{cur["ten"][:60]}", '
                         f'không phải "{inp["ten"][:60]}". Tớ không xoá.')

    notion.archive_page(token, inp["todoId"])

    # Gỡ khoá chống trùng: việc bị XOÁ HẲN thì cho phép nó quay lại sau này.
    # Khác với đánh dấu xong — xong thì khoá phải giữ, nếu không sáng mai nó
    # được thêm lại như chưa từng làm.
    conn = connect()
    conn.execute("DELETE FROM nguonKhoa WHERE pageId=?", (inp["todoId"],))
    conn.commit()
    conn.close()

    return (
        {"todoId": inp["todoId"], "ten": cur["ten"]},
        f'Đã xoá việc "{cur["ten"][:60]}". Notion giữ trong thùng rác 30 ngày.',
        [{"type": "notion.archivePage", "target": inp["todoId"],
          "idempotencyKey": f'delete|{inp["todoId"]}',
          "reversible": True,
          "previousValue": f'{cur["ten"]}|{cur["uuTien"]}|{cur["han"]}'}],
    )


HANDLERS = {"listTodos": list_todos, "addTodos": add_todos,
            "doneTodos": done_todos, "deleteTodo": delete_todo}


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
            raise ValueError(f"todoCompany không có năng lực '{cap}'")

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
                      summary=f"todoCompany hỏng khi chạy {cap}.")

    duration = int((time.time() - started) * 1000)
    result["usage"] = {"steps": 1, "durationMs": duration, "costUsd": 0.0}
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
