#!/usr/bin/env python3
"""Cắm Notion cho các company dùng nó. Chạy lại được nhiều lần.

    python3 ops/setup-notion.py

Script tự tạo những sổ còn thiếu với đúng schema mà company cần, nên không phải
dựng tay và không sợ đặt sai tên cột. Sổ đã có thì giữ nguyên, không tạo trùng.

Thêm company mới dùng Notion? Thêm một mục vào BOOKS bên dưới là xong.
Token ghi vào ops/.env (chmod 600, .gitignore đã chặn) — F2.
"""
import getpass
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import notionClient as notion  # noqa: E402

ENV_FILE = os.path.join(ROOT, "ops", ".env")

# Mỗi sổ: tên hiển thị trên Notion, biến môi trường, và schema cột.
# Schema phải khớp với tên cột mà company đọc trong src/main.py.
BOOKS = [
    {
        "company": "expenseCompany",
        "title": "Chi tiêu",
        "env": "NOTION_EXPENSE_DATABASE_ID",
        "schema": {
            "Tên":      {"title": {}},
            "Số tiền":  {"number": {"format": "number_with_commas"}},
            "Danh mục": {"select": {"options": [
                {"name": "ăn uống", "color": "orange"},
                {"name": "đi lại", "color": "blue"},
                {"name": "nhà cửa", "color": "brown"},
                {"name": "sức khoẻ", "color": "green"},
                {"name": "học tập", "color": "purple"},
                {"name": "giải trí", "color": "pink"},
                {"name": "công việc", "color": "gray"},
                {"name": "khác", "color": "default"},
            ]}},
            "Ngày":    {"date": {}},
            "Ghi chú": {"rich_text": {}},
        },
    },
    {
        "company": "incomeCompany",
        "title": "Thu nhập",
        "env": "NOTION_INCOME_DATABASE_ID",
        "schema": {
            "Tên":     {"title": {}},
            "Số tiền": {"number": {"format": "number_with_commas"}},
            "Nguồn":   {"select": {"options": [
                {"name": "lương", "color": "green"},
                {"name": "freelance", "color": "blue"},
                {"name": "kinh doanh", "color": "orange"},
                {"name": "đầu tư", "color": "purple"},
                {"name": "thưởng", "color": "pink"},
                {"name": "khác", "color": "default"},
            ]}},
            "Ngày":    {"date": {}},
            "Ghi chú": {"rich_text": {}},
        },
    },
    {
        "company": "calendarCompany",
        "title": "Lịch trình",
        "env": "NOTION_CALENDAR_DATABASE_ID",
        # Xem đẹp nhất bằng Calendar view ngay trong Notion (Add view → Calendar,
        # chọn "Bắt đầu" làm cột ngày).
        "schema": {
            "Tên":      {"title": {}},
            "Bắt đầu":  {"date": {}},
            "Kết thúc": {"date": {}},
            "Loại":     {"select": {"options": [
                {"name": "công việc", "color": "blue"},
                {"name": "cá nhân", "color": "purple"},
                {"name": "sức khoẻ", "color": "green"},
                {"name": "gia đình", "color": "orange"},
                {"name": "khác", "color": "default"},
            ]}},
            "Địa điểm": {"rich_text": {}},
            "Ghi chú":  {"rich_text": {}},
        },
    },
    {
        "company": "walletCompany",
        "title": "Ví",
        "env": "NOTION_WALLET_DATABASE_ID",
        # Mỗi dòng một ví, giữ MỐC KIỂM KÊ chứ không phải số dư sống. Số hiện tại
        # được tính = mốc + thu − chi kể từ ngày kiểm kê (xem walletCompany).
        "schema": {
            "Tên":         {"title": {}},
            "Số dư":       {"number": {"format": "number_with_commas"}},
            "Kiểm kê lúc": {"date": {}},
            "Ghi chú":     {"rich_text": {}},
        },
    },
    {
        "company": "budgetCompany",
        "title": "Ngân sách",
        "env": "NOTION_BUDGET_DATABASE_ID",
        # Tháng để dạng text "2026-08": lọc equals dễ, và không đẻ ra option mới
        # mỗi tháng như select.
        "schema": {
            "Tên":      {"title": {}},
            "Tháng":    {"rich_text": {}},
            "Danh mục": {"select": {"options": [
                {"name": "ăn uống", "color": "orange"},
                {"name": "đi lại", "color": "blue"},
                {"name": "nhà cửa", "color": "brown"},
                {"name": "sức khoẻ", "color": "green"},
                {"name": "học tập", "color": "purple"},
                {"name": "giải trí", "color": "pink"},
                {"name": "công việc", "color": "gray"},
                {"name": "khác", "color": "default"},
            ]}},
            "Hạn mức":  {"number": {"format": "number_with_commas"}},
            # Thời điểm đặt hạn mức. Hạn mức tính TỪ LÚC ĐẶT, không phải từ đầu
            # tháng: admin nói "còn 3 triệu ăn uống" lúc trưa là ý từ trưa trở đi,
            # không phải trừ ngược những gì đã tiêu sáng nay.
            "Đặt lúc":  {"date": {}},
            "Ghi chú":  {"rich_text": {}},
        },
    },
    {
        "company": "journalCompany",
        "title": "Nhật ký",
        "env": "NOTION_JOURNAL_DATABASE_ID",
        "schema": {
            "Tiêu đề":  {"title": {}},
            "Ngày":     {"date": {}},
            "Chủ đề":   {"select": {"options": [
                {"name": "công việc", "color": "blue"},
                {"name": "gia đình", "color": "orange"},
                {"name": "sức khoẻ", "color": "green"},
                {"name": "học tập", "color": "purple"},
                {"name": "quan hệ", "color": "pink"},
                {"name": "suy nghĩ", "color": "brown"},
                {"name": "khác", "color": "default"},
            ]}},
            "Tâm trạng": {"select": {"options": [
                {"name": "rất tốt", "color": "green"},
                {"name": "tốt", "color": "blue"},
                {"name": "bình thường", "color": "default"},
                {"name": "mệt", "color": "yellow"},
                {"name": "căng thẳng", "color": "orange"},
                {"name": "buồn", "color": "gray"},
            ]}},
            # Trích đoạn để nhìn nhanh trong danh sách.
            # Nội dung đầy đủ nằm ở thân trang, không giới hạn 2000 ký tự.
            "Trích đoạn": {"rich_text": {}},
        },
    },
    {
        "company": "savingsCompany",
        "title": "Quỹ tiết kiệm",
        "env": "NOTION_SAVINGS_DATABASE_ID",
        # Mỗi DÒNG là một quỹ, không phải một giao dịch. "Đã có" bị sửa tại chỗ
        # mỗi lần nạp/rút; lịch sử nằm ở eventLog của savingsCompany.
        "schema": {
            "Tên":      {"title": {}},
            "Loại":     {"select": {"options": [
                {"name": "chi tiêu", "color": "orange"},
                {"name": "đầu tư", "color": "purple"},
                {"name": "dự phòng", "color": "green"},
            ]}},
            "Mục tiêu": {"number": {"format": "number_with_commas"}},
            "Đã có":    {"number": {"format": "number_with_commas"}},
            "Hạn":      {"date": {}},
            "Trạng thái": {"select": {"options": [
                {"name": "đang góp", "color": "blue"},
                {"name": "đã đạt", "color": "green"},
                {"name": "tạm dừng", "color": "gray"},
            ]}},
            "Ghi chú":  {"rich_text": {}},
        },
    },
    {
        "company": "todoCompany",
        "title": "Việc cần làm",
        "env": "NOTION_TODO_DATABASE_ID",
        # Xem tiện nhất bằng Board view theo "Ưu tiên", hoặc lọc "Xong" = chưa
        # tick. Cột "Nguồn" cho biết việc từ đâu ra — tự thêm hay kéo từ kế hoạch.
        "schema": {
            "Việc":    {"title": {}},
            "Xong":    {"checkbox": {}},
            "Ưu tiên": {"select": {"options": [
                {"name": "cao", "color": "red"},
                {"name": "thường", "color": "blue"},
                {"name": "thấp", "color": "gray"},
            ]}},
            "Hạn":     {"date": {}},
            "Nguồn":   {"rich_text": {}},
            "Ghi chú": {"rich_text": {}},
        },
    },
    {
        "company": "planCompany",
        "title": "BẢNG TỔNG QUAN 100 VIDEO",
        "env": "NOTION_PLAN_DATABASE_ID",
        # Bảng này do admin tự dựng từ trước. Ta chỉ nhận lại, KHÔNG tạo mới —
        # tạo trùng một bảng kế hoạch là hỏng nặng hơn thiếu.
        "createIfMissing": False,
        "schema": {},
    },
]


def page_title(pg: dict) -> str:
    """Notion để tiêu đề ở vài chỗ khác nhau tuỳ loại trang."""
    for prop in (pg.get("properties") or {}).values():
        if prop.get("type") == "title":
            text = "".join(t.get("plain_text", "") for t in prop.get("title", []))
            if text.strip():
                return text.strip()
    slug = (pg.get("url") or "").rsplit("/", 1)[-1]
    return f"(chưa đặt tên · {slug[:24]})" if slug else "(chưa đặt tên)"


def db_title(db: dict) -> str:
    return "".join(t.get("plain_text", "") for t in db.get("title", [])).strip()


def add_missing_columns(token, db: dict, book: dict) -> list:
    """Sổ đã có sẵn nhưng company vừa cần thêm cột → vá vào, giữ nguyên dữ liệu.

    CHỈ THÊM cột thiếu. Không đổi kiểu, không xoá, không đổi tên: những việc đó
    làm mất dữ liệu cũ và phải do admin tự quyết trên Notion.
    Cột kiểu title cũng bỏ qua — Notion chỉ cho phép đúng một cột title, PATCH
    thêm cái thứ hai là lỗi.
    """
    have = set(db.get("properties") or {})
    missing = {k: v for k, v in (book.get("schema") or {}).items()
               if k not in have and "title" not in v}
    if missing:
        notion.update_database(token, db["id"], missing)
    return list(missing)


def read_env() -> dict:
    out = {}
    if os.path.isfile(ENV_FILE):
        for line in open(ENV_FILE, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k] = v
    return out


def write_env(values: dict):
    keys = ["TELEGRAM_BOT_TOKEN", "COMPANYSPEC_ADMIN_CHAT_ID",
            "COMPANYSPEC_GATEWAY_TOKEN", "NOTION_TOKEN", "NOTION_PARENT_PAGE_ID"]
    keys += [b["env"] for b in BOOKS]
    lines = ["# Sinh bởi ops/setup-bot.sh và ops/setup-notion.py",
             "# KHÔNG commit (.gitignore đã chặn, chmod 600).", ""]
    for key in keys:
        if values.get(key):
            lines.append(f"{key}={values[key]}")
    with open(ENV_FILE, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    os.chmod(ENV_FILE, 0o600)


def is_real_page(pg: dict) -> bool:
    """Loại bỏ các DÒNG trong database.

    Mỗi bản ghi Notion cũng là một page, nên search() trả về cả chúng. Không lọc
    thì danh sách chọn trang cha lẫn cả "Bún bò" (một khoản chi tiêu) — và sổ
    Nhật ký từng bị tạo nằm trong đó thật.
    Trang thật thì cha là workspace hoặc một page khác, không phải database.
    """
    return (pg.get("parent") or {}).get("type") in ("workspace", "page_id")


def pick_parent(token, env) -> dict | None:
    # Đã chọn trang cha lần trước thì dùng lại — mọi sổ phải nằm cùng một chỗ.
    saved = env.get("NOTION_PARENT_PAGE_ID")
    if saved:
        try:
            pg = notion._request("GET", f"/pages/{saved.replace('-', '')}", token)
            print(f"\n→ Dùng lại trang cha đã chọn lần trước: {page_title(pg)}")
            return pg
        except notion.NotionError:
            print("\n→ Trang cha cũ không truy cập được nữa, chọn lại.")

    print("\n→ Những trang cậu đã chia sẻ cho integration:")
    pages = [p for p in notion.search(token, object_type="page") if is_real_page(p)]
    if not pages:
        print("  Không thấy trang nào.")
        print("  Quay lại Notion, mở trang cần dùng → ⋯ → Connections →")
        print("  chọn integration, rồi chạy lại script này.")
        return None
    for i, pg in enumerate(pages[:10], 1):
        print(f"  [{i}] {page_title(pg)}")
        if pg.get("url"):
            print(f"      {pg['url']}")
    try:
        pick = int(input("\nChọn trang chứa các sổ [1]: ") or "1")
        parent = pages[pick - 1]
    except (ValueError, IndexError):
        print("Chọn không hợp lệ — dừng.")
        return None
    env["NOTION_PARENT_PAGE_ID"] = parent["id"]
    return parent


def main() -> int:
    print("═" * 62)
    print(" Cắm Notion cho companySpec")
    print("═" * 62)
    print()
    print("Chưa có integration? Làm 2 việc này trên Notion:")
    print()
    print("  1. https://www.notion.so/my-integrations → New integration")
    print("     Copy 'Internal Integration Secret' (ntn_… hoặc secret_…)")
    print()
    print("  2. Mở trang Notion muốn chứa các sổ → ⋯ → Connections →")
    print("     chọn integration vừa tạo.")
    print()
    print("  Integration CHỈ thấy trang cậu chia sẻ — không thấy gì khác.")
    print()

    env = read_env()
    existing = env.get("NOTION_TOKEN", "")
    prompt = "Dán token Notion (Enter để giữ token cũ): " if existing \
        else "Dán token Notion: "
    token = getpass.getpass(prompt).strip() or existing
    if not token:
        print("Không có token — dừng.")
        return 1

    print("\n→ Kiểm tra token…")
    try:
        me = notion.whoami(token)
    except notion.NotionError as exc:
        print(f"  {exc}")
        return 1
    print(f"  hợp lệ · integration: {me.get('name') or '(không tên)'}")
    env["NOTION_TOKEN"] = token

    # Sổ nào đã có thì nhận lại, không tạo trùng.
    print("\n→ Kiểm tra các sổ:")
    missing = []
    for book in BOOKS:
        found = None
        try:
            for cand in notion.search(token, book["title"], object_type="database"):
                if db_title(cand) == book["title"]:
                    found = cand
                    break
        except notion.NotionError as exc:
            print(f"  {exc}")
            return 1
        if found:
            env[book["env"]] = found["id"]
            try:
                them = add_missing_columns(token, found, book)
            except notion.NotionError as exc:
                print(f"  ! {book['title']:<10} không thêm được cột: {exc}")
                them = []
            print(f"  ✓ {book['title']:<10} đã có  ({book['company']})"
                  + (f" · thêm cột: {', '.join(them)}" if them else ""))
        elif book.get("createIfMissing") is False:
            print(f"  ! {book['title']:<10} KHÔNG THẤY — chia sẻ bảng này cho "
                  f"integration rồi chạy lại ({book['company']})")
        else:
            missing.append(book)
            print(f"  · {book['title']:<10} chưa có ({book['company']})")

    if missing:
        parent = pick_parent(token, env)
        if parent is None:
            return 1
        for book in missing:
            print(f"\n→ Tạo sổ '{book['title']}'…")
            try:
                db = notion.create_database(token, parent["id"],
                                            book["title"], book["schema"])
            except notion.NotionError as exc:
                print(f"  {exc}")
                return 1
            env[book["env"]] = db["id"]
            print(f"  xong: {db.get('url', db['id'])}")

    write_env(env)
    print("\n  đã ghi ops/.env (chmod 600)")

    print()
    print("═" * 62)
    print(" Xong. Nạp lại cấu hình:")
    print()
    print("   systemctl --user restart companyspec-gateway")
    print()
    print(" Rồi thử nhắn bot:")
    print('   "ghi chi tiêu bún bò 50k"')
    print('   "ghi nhật ký: hôm nay họp căng nhưng chốt được việc"')
    print("═" * 62)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nDừng.")
        sys.exit(1)
