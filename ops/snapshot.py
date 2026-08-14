#!/usr/bin/env python3
"""Chụp và phục hồi toàn bộ một sổ Notion.

VÌ SAO CÓ FILE NÀY: ngày 2026-08-04 tôi kiểm chứng `archiveTask` bằng cách ẩn
video 001 thật trong kế hoạch của admin. Notion giữ 30 ngày, nhưng API `search`
không trả về trang đã ẩn, và `sideEffects.target` lúc đó ghi nhãn `video/001`
chứ không phải page id — nên không có đường về. Admin mất trường `KPI chính`
và không khôi phục được.

W7 — mọi phép thử chạm tới thêm/sửa/xoá phải TỰ khôi phục được, không dựa vào
thùng rác của bên thứ ba. "Nền tảng giữ 30 ngày" là một hy vọng, không phải kế
hoạch phục hồi.

    python3 ops/snapshot.py save plan            # chụp trước khi làm gì
    python3 ops/snapshot.py list                 # xem các bản đã chụp
    python3 ops/snapshot.py diff plan            # so hiện tại với bản mới nhất
    python3 ops/snapshot.py restore plan --apply # dựng lại những gì đã mất
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import notionClient as notion  # noqa: E402

SNAP_DIR = os.path.join(ROOT, "backOffice", "snapshots")
TZ = timezone(timedelta(hours=7))

BOOKS = {
    "plan":    "NOTION_PLAN_DATABASE_ID",
    "expense": "NOTION_EXPENSE_DATABASE_ID",
    "journal": "NOTION_JOURNAL_DATABASE_ID",
    "income":  "NOTION_INCOME_DATABASE_ID",
    "savings": "NOTION_SAVINGS_DATABASE_ID",
    "calendar": "NOTION_CALENDAR_DATABASE_ID",
    "wallet":  "NOTION_WALLET_DATABASE_ID",
    "budget":  "NOTION_BUDGET_DATABASE_ID",
}


def token() -> str:
    return notion.token_from_env()


def db_id(book: str) -> str:
    var = BOOKS[book]
    val = os.environ.get(var, "")
    if not val:
        raise SystemExit(f"Thiếu {var} trong ops/.env")
    return val


def key_of(props: dict) -> str:
    """Khoá nhận diện bản ghi — cột title. Với kế hoạch đó là STT."""
    for p in props.values():
        if p.get("type") == "title":
            return "".join(t.get("plain_text", "") for t in p.get("title", [])).strip()
    return ""


def capture(book: str) -> dict:
    """Chụp ĐẦY ĐỦ mọi property, không chọn lọc.

    Chọn lọc là chỗ mất mát: lần trước previousValue chỉ giữ 4 trường nên khôi
    phục xong vẫn thiếu KPI chính. Không biết trước cái gì sẽ cần thì giữ hết.
    """
    tok = token()
    rows = notion.query_database(tok, db_id(book), page_size=100)
    return {
        "book": book,
        "databaseId": db_id(book),
        "capturedAt": datetime.now(TZ).strftime("%Y-%m-%dT%H:%M:%S%z"),
        "count": len(rows),
        "pages": [{"id": r["id"], "key": key_of(r["properties"]),
                   "url": r.get("url", ""), "properties": r["properties"]} for r in rows],
    }


def latest(book: str):
    if not os.path.isdir(SNAP_DIR):
        return None
    files = sorted(f for f in os.listdir(SNAP_DIR)
                   if f.startswith(f"{book}-") and f.endswith(".json"))
    if not files:
        return None
    return os.path.join(SNAP_DIR, files[-1])


def writable(props: dict) -> dict:
    """Bỏ những property Notion tự tính, giữ phần ghi lại được."""
    out = {}
    for name, p in props.items():
        t = p.get("type")
        if t in ("formula", "rollup", "created_time", "created_by",
                 "last_edited_time", "last_edited_by", "unique_id"):
            continue
        if t == "title":
            out[name] = {"title": p.get("title", [])}
        elif t == "rich_text":
            out[name] = {"rich_text": p.get("rich_text", [])}
        elif t in ("select", "status"):
            v = p.get(t)
            out[name] = {t: ({"name": v["name"]} if v else None)}
        elif t == "multi_select":
            out[name] = {"multi_select": [{"name": x["name"]} for x in p.get("multi_select", [])]}
        elif t in ("number", "checkbox", "url", "email", "phone_number"):
            out[name] = {t: p.get(t)}
        elif t == "date":
            out[name] = {"date": p.get("date")}
    return out


def cmd_save(args):
    snap = capture(args.book)
    os.makedirs(SNAP_DIR, exist_ok=True)
    stamp = datetime.now(TZ).strftime("%Y%m%d-%H%M%S")
    path = os.path.join(SNAP_DIR, f"{args.book}-{stamp}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(snap, fh, ensure_ascii=False, indent=1)
    print(f"đã chụp {snap['count']} bản ghi → {os.path.relpath(path, ROOT)}")
    return 0


def cmd_list(args):
    if not os.path.isdir(SNAP_DIR):
        print("chưa có bản chụp nào")
        return 0
    for f in sorted(os.listdir(SNAP_DIR)):
        if not f.endswith(".json"):
            continue
        d = json.load(open(os.path.join(SNAP_DIR, f), encoding="utf-8"))
        print(f"  {f:<34}{d['count']:>4} bản ghi   {d['capturedAt'][:16]}")
    return 0


def compare(book: str):
    path = latest(book)
    if not path:
        raise SystemExit(f"chưa có bản chụp nào cho '{book}' — chạy: save {book}")
    old = json.load(open(path, encoding="utf-8"))
    new = capture(book)
    old_ids = {p["id"] for p in old["pages"]}
    new_ids = {p["id"] for p in new["pages"]}
    missing = [p for p in old["pages"] if p["id"] not in new_ids]
    added = [p for p in new["pages"] if p["id"] not in old_ids]
    return path, old, new, missing, added


def cmd_diff(args):
    path, old, new, missing, added = compare(args.book)
    print(f"bản chụp : {os.path.basename(path)}  ({old['count']} bản ghi)")
    print(f"hiện tại : {new['count']} bản ghi\n")
    if not missing and not added:
        print("  không lệch gì")
        return 0
    for p in missing:
        print(f"  MẤT   {p['key'] or '(không tên)'}")
    for p in added:
        print(f"  THÊM  {p['key'] or '(không tên)'}")
    return 0


def cmd_restore(args):
    path, old, new, missing, added = compare(args.book)
    if not missing:
        print("không có bản ghi nào bị mất")
        return 0

    print(f"sẽ dựng lại {len(missing)} bản ghi từ {os.path.basename(path)}:")
    for p in missing:
        print(f"  {p['key'] or '(không tên)'}")
    if not args.apply:
        print("\n(chưa làm gì — thêm --apply để thực hiện)")
        return 0

    tok = token()
    for p in missing:
        # Thử lấy lại bản gốc trước; chỉ tạo mới khi thật sự không còn.
        try:
            notion.unarchive_page(tok, p["id"])
            print(f"  khôi phục nguyên bản: {p['key']}")
            continue
        except notion.NotionError:
            pass
        notion.create_page(tok, old["databaseId"], writable(p["properties"]))
        print(f"  dựng lại (id mới): {p['key']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="chụp/phục hồi sổ Notion")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("save", cmd_save), ("diff", cmd_diff), ("restore", cmd_restore)):
        s = sub.add_parser(name)
        s.add_argument("book", choices=sorted(BOOKS))
        if name == "restore":
            s.add_argument("--apply", action="store_true")
        s.set_defaults(fn=fn)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
