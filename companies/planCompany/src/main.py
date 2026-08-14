#!/usr/bin/env python3
"""planCompany — theo dõi kế hoạch 100 video trên Notion.

Hợp đồng (C1): taskEnvelope trên stdin → companyResult trên stdout.

Company đầu tiên SỬA bản ghi đã có. Hai luật tự đặt cho mình:
  · Đọc giá trị cũ TRƯỚC khi ghi đè, và khai vào sideEffects.previousValue.
    Không có nó thì không ai hoàn tác được, kể cả admin.
  · Không tìm thấy STT thì báo lỗi rõ, KHÔNG tạo mới. Sửa nhầm thành thêm mới
    là kiểu hỏng im lặng tệ nhất.
"""
import json
import os
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "lib"))
import notionClient as notion  # noqa: E402
import db  # noqa: E402

STORE = os.path.join(HERE, "..", "store.sqlite")
TZ = timezone(timedelta(hours=7))

CHUA_LAM = "chưa làm"
THU_TU = [CHUA_LAM, "đang viết", "đã quay", "đã dựng", "đã đăng"]

# Giai đoạn suy được từ STT — kiểm chứng trên 85 dòng sạch của bảng hiện có.
# Nhờ vậy admin không phải nhớ, và không thể điền lệch nhau nữa.
MOC_GIAI_DOAN = [(25, "GD1"), (50, "GD2"), (75, "GD3"), (100, "GD4")]


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def database_id() -> str:
    dbid = os.environ.get("NOTION_PLAN_DATABASE_ID", "")
    if not dbid:
        raise notion.NotionError(
            "Thiếu NOTION_PLAN_DATABASE_ID. Chạy: python3 ops/setup-notion.py")
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


def norm_stt(raw: str) -> str:
    """"8" · "08" · "008" đều là video số 8. Chuẩn hoá về đúng dạng trong bảng."""
    digits = "".join(c for c in str(raw) if c.isdigit())
    if not digits:
        raise ValueError(f"STT '{raw}' không phải số")
    return f"{int(digits):03d}"


def giai_doan_of(stt: str) -> str:
    num = int(stt)
    for moc, ten in MOC_GIAI_DOAN:
        if num <= moc:
            return ten
    raise ValueError(f"STT {stt} vượt quá 100, ngoài phạm vi kế hoạch")


def row_to_task(page: dict) -> dict:
    p = page.get("properties", {})
    return {
        "pageId": page["id"],
        "stt": (notion.plain(p.get("STT")) or "").strip(),
        "chuDe": notion.plain(p.get("Chủ đề")) or "",
        "giaiDoan": notion.plain(p.get("Giai đoạn")),
        "loaiChuDe": notion.plain(p.get("Loại chủ đề")),
        # Cột mới nâng cấp: bản ghi cũ chưa đặt thì coi như chưa làm.
        "trangThai": notion.plain(p.get("Trạng thái")) or CHUA_LAM,
        "kpiChinh": notion.plain(p.get("KPI chính")) or "",
        "kpiDat": (p.get("KPI check") or {}).get("checkbox"),
        "url": page.get("url", ""),
    }


def find_by_stt(token, stt: str) -> dict | None:
    pages = notion.query_database(
        token, database_id(),
        filter_={"property": "STT", "title": {"equals": stt}}, page_size=2)
    return row_to_task(pages[0]) if pages else None


# ───────────────────────── năng lực ─────────────────────────

def progress_report(token, inp):
    flt = None
    if inp.get("giaiDoan"):
        flt = {"property": "Giai đoạn", "select": {"equals": inp["giaiDoan"]}}
    tasks = [row_to_task(p) for p in
             notion.query_database(token, database_id(), filter_=flt, page_size=100)]

    by_tt = Counter(t["trangThai"] for t in tasks)
    by_gd = Counter(t["giaiDoan"] or "(trống)" for t in tasks)
    by_lo = Counter(t["loaiChuDe"] or "(trống)" for t in tasks)
    done = by_tt.get("đã đăng", 0)
    total = len(tasks)
    pct = round(done * 100 / total, 1) if total else 0.0

    dang_lam = total - done - by_tt.get(CHUA_LAM, 0)
    scope = f"{inp['giaiDoan']}: " if inp.get("giaiDoan") else ""
    return (
        {"total": total, "done": done, "percentDone": pct,
         "byTrangThai": dict(by_tt), "byGiaiDoan": dict(by_gd),
         "byLoaiChuDe": dict(by_lo)},
        f"{scope}{done}/{total} đã đăng ({pct}%). Đang làm dở {dang_lam}, "
        f"chưa động tới {by_tt.get(CHUA_LAM, 0)}.",
        [],
    )


def list_tasks(token, inp):
    conds = []
    if inp.get("giaiDoan"):
        conds.append({"property": "Giai đoạn", "select": {"equals": inp["giaiDoan"]}})
    if inp.get("loaiChuDe"):
        conds.append({"property": "Loại chủ đề", "select": {"equals": inp["loaiChuDe"]}})
    flt = {"and": conds} if len(conds) > 1 else (conds[0] if conds else None)

    tasks = [row_to_task(p) for p in
             notion.query_database(token, database_id(), filter_=flt, page_size=100)]

    # Lọc trạng thái ở phía ta: bản ghi cũ để trống, Notion không lọc được "trống
    # HOẶC chưa làm" bằng một điều kiện.
    if inp.get("trangThai"):
        tasks = [t for t in tasks if t["trangThai"] == inp["trangThai"]]

    tasks.sort(key=lambda t: t["stt"])
    limit = inp.get("gioiHan", 30)
    shown = tasks[:limit]

    bits = [x for x in (inp.get("giaiDoan"), inp.get("loaiChuDe"),
                        inp.get("trangThai")) if x]
    scope = " · ".join(bits) or "toàn bộ"
    more = f" (hiện {len(shown)})" if len(tasks) > limit else ""
    return (
        {"tasks": shown, "count": len(tasks)},
        f"{scope}: {len(tasks)} video{more}",
        [],
    )


def update_progress(token, inp):
    stt = norm_stt(inp["stt"])
    task = find_by_stt(token, stt)
    if task is None:
        # Không tự tạo mới. Sửa nhầm thành thêm mới là hỏng im lặng.
        raise ValueError(f"Không có video STT {stt} trong kế hoạch")

    truoc = task["trangThai"]
    props = {"Trạng thái": notion.select_prop(inp["trangThai"])}
    if inp.get("kpiDat") is not None:
        props["KPI check"] = {"checkbox": bool(inp["kpiDat"])}
    notion.update_page(token, task["pageId"], props)

    return (
        {"stt": stt, "chuDe": task["chuDe"], "trangThai": inp["trangThai"],
         "previousTrangThai": truoc, "kpiDat": inp.get("kpiDat"),
         "url": task["url"]},
        f'Video {stt} "{task["chuDe"][:40]}": {truoc} → {inp["trangThai"]}',
        # previousValue là thứ duy nhất cho phép quay lại. Không khai thì mất.
        [{"type": "notion.updatePage", "target": f"video/{stt}",
          "idempotencyKey": f'{stt}|{inp["trangThai"]}',
          "reversible": True, "previousValue": truoc}],
    )


def add_task(token, inp):
    stt = norm_stt(inp["stt"])
    if find_by_stt(token, stt) is not None:
        raise ValueError(f"Video STT {stt} đã có trong kế hoạch")
    gd = giai_doan_of(stt)

    page = notion.create_page(token, database_id(), {
        "STT":         notion.title_prop(stt),
        "Chủ đề":      notion.text_prop(inp["chuDe"]),
        "Giai đoạn":   notion.select_prop(gd),
        "Loại chủ đề": notion.select_prop(inp["loaiChuDe"]),
        "Trạng thái":  notion.select_prop(CHUA_LAM),
        "KPI chính":   notion.text_prop(inp.get("kpiChinh", "")),
    })
    return (
        {"stt": stt, "chuDe": inp["chuDe"], "giaiDoan": gd,
         "loaiChuDe": inp["loaiChuDe"], "url": page.get("url", "")},
        f'Đã thêm video {stt} · {gd} · {inp["loaiChuDe"]} — "{inp["chuDe"][:40]}"',
        [{"type": "notion.createPage", "target": f"video/{stt}",
          "idempotencyKey": f"video/{stt}", "reversible": True}],
    )


def _same_text(a: str, b: str) -> bool:
    """So khớp chủ đề, bỏ qua hoa thường và khoảng trắng thừa.

    CEO chép chủ đề từ listTasks nên phải khớp; nhưng đừng để một dấu cách thừa
    chặn oan admin.
    """
    norm = lambda x: " ".join((x or "").lower().split())
    return norm(a) == norm(b)


def archive_task(token, inp):
    """D7 — đối chiếu chủ đề trước khi ẩn."""
    stt = norm_stt(inp["stt"])
    task = find_by_stt(token, stt)
    if task is None:
        raise ValueError(f"Không có video STT {stt} trong kế hoạch")
    if not _same_text(task["chuDe"], inp["chuDe"]):
        raise ValueError(
            f'Không khớp: video {stt} là "{task["chuDe"][:50]}", '
            f'không phải "{inp["chuDe"][:50]}". Tớ không ẩn.')

    notion.archive_page(token, task["pageId"])
    # target PHẢI là pageId, không phải "video/001".
    # Nhãn dễ đọc thì không khôi phục được: API search của Notion không trả về
    # trang trong thùng rác, nên không có id là mất đường về. Đã trả giá thật.
    truoc = (f'{stt}|{task["giaiDoan"]}|{task["loaiChuDe"]}|'
             f'{task["kpiChinh"]}|{task["trangThai"]}|{task["chuDe"][:80]}')
    return (
        {"stt": stt, "chuDe": task["chuDe"], "giaiDoan": task["giaiDoan"],
         "trangThai": task["trangThai"]},
        f'Đã ẩn video {stt} · {task["giaiDoan"]} · "{task["chuDe"][:44]}". '
        "Notion giữ trong thùng rác 30 ngày.",
        [{"type": "notion.archivePage", "target": task["pageId"],
          "idempotencyKey": f"archive|video/{stt}",
          "reversible": True, "previousValue": truoc}],
    )


HANDLERS = {"progressReport": progress_report, "listTasks": list_tasks,
            "updateProgress": update_progress, "addTask": add_task,
            "archiveTask": archive_task}


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
            raise ValueError(f"planCompany không có năng lực '{cap}'")

        if dry_run:  # W2
            result.update(status="ok", output=None,
                          summary=f"[dryRun] Sẽ chạy {cap} với "
                                  f"{json.dumps(inp, ensure_ascii=False)[:180]}")
        else:
            token = notion.token_from_env()
            output, summary, side_effects = handler(token, inp)
            result.update(status="ok", output=output, summary=summary,
                          sideEffects=side_effects)

    except notion.NotionError as exc:
        result.update(status="failed", error=str(exc),
                      summary=f"Notion không phản hồi đúng: {exc}")
    except ValueError as exc:
        # Lỗi do dữ liệu admin đưa vào — nói rõ để CEO hỏi lại, đừng đoán.
        result.update(status="needsInput", error=str(exc), summary=str(exc))
    except Exception as exc:  # O3
        result.update(status="failed", error=f"{type(exc).__name__}: {exc}",
                      summary=f"planCompany hỏng khi chạy {cap}.")

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
         json.dumps({"status": result["status"],
                     "sideEffects": result["sideEffects"]}, ensure_ascii=False),
         now_utc()),
    )
    conn.commit()
    conn.close()

    json.dump(result, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
