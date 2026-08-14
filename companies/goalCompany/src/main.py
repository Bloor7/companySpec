#!/usr/bin/env python3
"""goalCompany — mỗi kế hoạch một BẢNG Notion riêng.

Hợp đồng (C1): taskEnvelope trên stdin → companyResult trên stdout.

VÌ SAO MỖI KẾ HOẠCH MỘT BẢNG (đổi ngày 2026-08-04):
bản đầu gộp mọi kế hoạch vào một sổ, phân biệt bằng cột "Kế hoạch". Admin mở
Notion lên, thấy một kế hoạch 6 bước đã kín trang, và nói đúng điều sắp xảy ra:
thêm kế hoạch thứ hai là không đọc nổi nữa. Bảng riêng thì mỗi mục tiêu có một
trang sạch, và bỏ một kế hoạch cũng không đụng kế hoạch khác.

Cái giá: phải nhớ kế hoạch nào ứng với bảng nào. Bản đồ đó nằm ở store.sqlite —
là CẤU HÌNH, không phải bản sao dữ liệu (các bước vẫn chỉ có một chỗ là Notion).
Mất store cũng không mất gì: sync_registry() quét lại các bảng có tiền tố "KH: ".

Company này KHÔNG nghĩ ra bước nào cả — việc đó là của CEO. Ở đây chỉ cất, đếm
và sắp thứ tự.
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

# Tiền tố nhận diện bảng kế hoạch giữa các sổ khác trên Notion.
TIEN_TO = "KH: "

# Ưu tiên của một kế hoạch. Lưu trong MÔ TẢ của database trên Notion, dạng
# "uuTien=cao" — không lưu ở sqlite, vì store là bộ nhớ đệm dựng lại được còn
# ưu tiên là thứ admin đặt ra và không được phép mất khi đổi máy.
UU_TIEN = ["cao", "vừa", "thấp"]


def doc_uu_tien(mo_ta: str) -> str:
    for phan in (mo_ta or "").split():
        if phan.startswith("uuTien="):
            gt = phan[7:].strip()
            if gt in UU_TIEN:
                return gt
    return "vừa"

# Cột của mỗi bảng kế hoạch. Không còn cột "Kế hoạch" — cả bảng LÀ một kế hoạch.
COT = {
    "Tên":        {"title": {}},
    "Thứ tự":     {"number": {"format": "number"}},
    "Trạng thái": {"select": {"options": [
        {"name": "chưa làm", "color": "default"},
        {"name": "đang làm", "color": "blue"},
        {"name": "xong", "color": "green"},
    ]}},
    "Hạn":        {"date": {}},
    "Ghi chú":    {"rich_text": {}},
}


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def parent_page() -> str:
    pid = os.environ.get("NOTION_PARENT_PAGE_ID", "")
    if not pid:
        raise notion.NotionError(
            "Thiếu NOTION_PARENT_PAGE_ID. Chạy: python3 ops/setup-notion.py")
    return pid


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
        -- Bản đồ kế hoạch → bảng Notion. Dựng lại được bằng sync_registry().
        CREATE TABLE IF NOT EXISTS keHoach (
          ten TEXT PRIMARY KEY, databaseId TEXT NOT NULL,
          hanChot TEXT, uuTien TEXT DEFAULT 'vừa', taoLuc TEXT NOT NULL
        );
        """
    )
    # Thêm dần, không phá bảng cũ: store đã tồn tại từ trước khi có ưu tiên.
    try:
        conn.execute("ALTER TABLE keHoach ADD COLUMN uuTien TEXT DEFAULT 'vừa'")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # đã có
    return conn


# ───────────────────── bản đồ kế hoạch → bảng ─────────────────────

def db_title(d: dict) -> str:
    return "".join(t.get("plain_text", "") for t in d.get("title", [])).strip()


def sync_registry(token) -> int:
    """Quét Notion tìm các bảng "KH: …" rồi ghi lại vào store.

    Chạy khi tra không thấy kế hoạch. Nhờ nó, store.sqlite chỉ là bộ nhớ đệm:
    admin đổi máy, xoá store, hay tự tạo bảng tay trên Notion thì lần gọi sau
    vẫn tìm ra — miễn tên bảng còn tiền tố.
    """
    conn = connect()
    n = 0
    for d in notion.search(token, TIEN_TO, object_type="database", page_size=50):
        ten_bang = db_title(d)
        if not ten_bang.startswith(TIEN_TO):
            continue
        ten = ten_bang[len(TIEN_TO):].strip()
        conn.execute(
            "INSERT OR REPLACE INTO keHoach (ten, databaseId, hanChot, uuTien, taoLuc) "
            "VALUES (?,?,(SELECT hanChot FROM keHoach WHERE ten=?),?,?)",
            (ten, d["id"], ten, doc_uu_tien(notion.db_description(d)), now_utc()))
        n += 1
    conn.commit()
    conn.close()
    return n


def all_plans(token) -> list:
    conn = connect()
    rows = [dict(r) for r in conn.execute(
        "SELECT ten, databaseId, hanChot, COALESCE(uuTien,'vừa') uuTien "
        "FROM keHoach ORDER BY ten")]
    conn.close()
    if not rows and sync_registry(token):
        return all_plans(token)
    return rows


def find_plan(token, ten: str):
    """Tra kế hoạch theo tên, bỏ qua hoa thường và khoảng trắng thừa.

    Trả None nếu không có — người gọi quyết định đó là lỗi (addStep) hay là điều
    kiện cần (createPlan).
    """
    chuan = " ".join(ten.split()).lower()
    for lan in range(2):                      # lần 2 chạy sau khi đồng bộ lại
        for p in all_plans(token):
            if " ".join(p["ten"].split()).lower() == chuan:
                return p
        if lan == 0:
            sync_registry(token)
    return None


def can_co(token, ten: str) -> dict:
    plan = find_plan(token, ten)
    if plan is None:
        raise ValueError(
            f'Không có kế hoạch nào tên "{ten}". Gọi listPlans để xem tên đúng.')
    return plan


# ───────────────────────── đọc bước ─────────────────────────

def row_to_step(page: dict, ke_hoach: str) -> dict:
    props = page.get("properties", {})
    return {
        "stepId": page["id"],
        "ten": notion.plain(props.get("Tên")) or "",
        "keHoach": ke_hoach,
        "thuTu": int(notion.plain(props.get("Thứ tự")) or 0),
        "trangThai": notion.plain(props.get("Trạng thái")) or "chưa làm",
        "han": notion.plain(props.get("Hạn")),
        "ghiChu": notion.plain(props.get("Ghi chú")) or "",
        "url": page.get("url", ""),
    }


def steps_of(token, plan: dict) -> list:
    pages = notion.query_database(token, plan["databaseId"], page_size=100)
    steps = [row_to_step(p, plan["ten"]) for p in pages]
    steps.sort(key=lambda s: s["thuTu"])
    return steps


def tien_do(steps: list) -> tuple:
    xong = sum(1 for s in steps if s["trangThai"] == "xong")
    pct = round(xong / len(steps) * 100, 1) if steps else 0.0
    return xong, pct


def bar(pct: float, width: int = 10) -> str:
    pct = max(0.0, min(100.0, pct or 0.0))
    filled = int(pct / 100 * width)
    if pct > 0 and filled == 0:
        filled = 1
    return "█" * filled + "░" * (width - filled)


def dau(s: dict) -> str:
    return {"xong": "✓", "đang làm": "▸"}.get(s["trangThai"], "·")


def ngay_ngan(iso) -> str:
    return f"{iso[8:10]}/{iso[5:7]}" if iso else ""


# ───────────────────────── năng lực ─────────────────────────

def list_plans(token, inp):
    plans = all_plans(token)
    if not plans:
        return {"plans": [], "count": 0}, "Chưa có kế hoạch nào.", []

    plans.sort(key=lambda p: (UU_TIEN.index(p.get("uuTien") or "vừa"),
                              p.get("hanChot") or "9999"))
    ra, dong = [], []
    for p in plans:
        steps = steps_of(token, p)
        xong, pct = tien_do(steps)
        if inp.get("chuaXong") and steps and xong == len(steps):
            continue
        hans = [s["han"] for s in steps if s["han"]]
        han = p["hanChot"] or (max(hans) if hans else None)
        ut = p.get("uuTien") or "vừa"
        ra.append({"keHoach": p["ten"], "soBuoc": len(steps), "xong": xong,
                   "phanTram": pct, "hanChot": han, "uuTien": ut})
        dong.append(f'[{ut}] {p["ten"]} {bar(pct)} {round(pct)}%\n'
                    f'{xong}/{len(steps)} bước'
                    + (f" · hạn {han}" if han else ""))

    if not ra:
        return {"plans": [], "count": 0}, "Mọi kế hoạch đều đã xong.", []
    return ({"plans": ra, "count": len(ra)},
            f"{len(ra)} kế hoạch:\n\n" + "\n\n".join(dong), [])


def plan_steps(token, inp):
    plan = can_co(token, inp["keHoach"])
    steps = steps_of(token, plan)
    loc = ([s for s in steps if s["trangThai"] == inp["trangThai"]]
           if inp.get("trangThai") else steps)
    xong, pct = tien_do(steps)

    dong = [f'{dau(s)} {s["thuTu"]}. {s["ten"]}'
            + (f' — hạn {ngay_ngan(s["han"])}' if s["han"] else "") for s in loc]
    return ({"steps": loc, "count": len(loc), "keHoach": plan["ten"],
             "xong": xong, "phanTram": pct},
            f'{plan["ten"]} {bar(pct)} {round(pct)}% ({xong}/{len(steps)})\n'
            + "\n".join(dong), [])


def due_steps(token, inp):
    """Bước tới hạn trong N ngày, gộp MỌI kế hoạch. Bước đã xong thì bỏ qua —
    quá hạn một việc đã làm xong không phải tin tức."""
    ngay = inp.get("trongNgay", 7)
    hom_nay = today()
    han_cuoi = (datetime.now(TZ) + timedelta(days=ngay)).strftime("%Y-%m-%d")

    tat = []
    for p in all_plans(token):
        tat += [s for s in steps_of(token, p)
                if s["trangThai"] != "xong" and s["han"] and s["han"] <= han_cuoi]

    qua_han = sorted([s for s in tat if s["han"] < hom_nay],
                     key=lambda s: (s["keHoach"], s["han"]))
    sap_toi = sorted([s for s in tat if s["han"] >= hom_nay],
                     key=lambda s: (s["keHoach"], s["han"]))
    ca_hai = qua_han + sap_toi

    out = {"steps": ca_hai, "count": len(ca_hai), "quaHan": len(qua_han),
           "trongNgay": ngay}
    if not ca_hai:
        # Rỗng = không có gì để nói; scheduler đọc quy ước này để giữ im lặng.
        return out, ("" if inp.get("chiKhiCo")
                     else f"Không có bước nào tới hạn trong {ngay} ngày tới."), []

    def khoi(tieu_de, items):
        """Gộp theo kế hoạch, tên kế hoạch in MỘT lần — lặp ở mỗi dòng thì đọc
        trên điện thoại chỉ thấy một khối chữ giống nhau."""
        ra, hien_tai = [tieu_de], None
        for s in items:
            if s["keHoach"] != hien_tai:
                hien_tai = s["keHoach"]
                ra.append(f"  {hien_tai}")
            ra.append(f'    {ngay_ngan(s["han"])}  {s["ten"]}')
        return ra

    dong = []
    if qua_han:
        dong += khoi(f"Quá hạn ({len(qua_han)}):", qua_han)
    if sap_toi:
        dong += khoi(f"Tới hạn trong {ngay} ngày:", sap_toi)
    return out, "\n".join(dong), []


def create_plan(token, inp):
    """Tạo BẢNG mới rồi đổ các bước vào — một lời gọi, một lần duyệt."""
    ten = " ".join(inp["ten"].split())
    if find_plan(token, ten):
        raise ValueError(
            f'Đã có kế hoạch tên "{ten}" rồi. Đặt tên khác, hoặc dùng addStep '
            "để thêm bước vào kế hoạch cũ.")

    ut = inp.get("uuTien") or "vừa"
    db_moi = notion.create_database(token, parent_page(), TIEN_TO + ten, COT)
    dbid = db_moi["id"]
    notion.set_database_description(token, dbid, f"uuTien={ut}")
    side = [{"type": "notion.createDatabase", "target": dbid,
             "idempotencyKey": f"bang|{ten}", "reversible": True}]

    conn = connect()
    conn.execute("INSERT OR REPLACE INTO keHoach (ten, databaseId, hanChot, uuTien, taoLuc) "
                 "VALUES (?,?,?,?,?)", (ten, dbid, inp.get("hanChot"), ut, now_utc()))
    conn.commit()
    conn.close()

    tao = []
    for i, buoc in enumerate(inp["cacBuoc"], 1):
        props = {
            "Tên":        notion.title_prop(buoc["ten"]),
            "Thứ tự":     notion.number_prop(i),
            "Trạng thái": notion.select_prop("chưa làm"),
            "Ghi chú":    notion.text_prop(buoc.get("ghiChu", "")),
        }
        # Bước không có hạn riêng thì lấy hạn chót chung — không hạn nào thì kế
        # hoạch trôi vô định, mà thứ trôi vô định thì không nhắc được.
        han = buoc.get("han") or inp.get("hanChot")
        if han:
            props["Hạn"] = notion.date_prop(han)
        page = notion.create_page(token, dbid, props)
        tao.append({"stepId": page["id"], "thuTu": i, "ten": buoc["ten"],
                    "han": han, "url": page.get("url", "")})
        side.append({"type": "notion.createPage", "target": page["id"],
                     "idempotencyKey": f'{ten}|{i}|{buoc["ten"]}',
                     "reversible": True})

    dong = [f'{b["thuTu"]}. {b["ten"]}'
            + (f' — hạn {ngay_ngan(b["han"])}' if b["han"] else "") for b in tao]
    return (
        {"keHoach": ten, "soBuoc": len(tao), "hanChot": inp.get("hanChot"),
         "uuTien": ut, "url": db_moi.get("url", ""), "steps": tao},
        f'Đã tạo bảng riêng "{TIEN_TO}{ten}" trên Notion, {len(tao)} bước'
        + (f', hạn chót {inp["hanChot"]}' if inp.get("hanChot") else "") + ":\n"
        + "\n".join(dong),
        side,
    )


def set_priority(token, inp):
    """Đổi thứ tự ưu tiên của một kế hoạch.

    Ưu tiên quyết định thứ tự trong mọi bản liệt kê và trong bức tranh CEO đọc
    mỗi lượt — nên nó là cách admin nói "cái này quan trọng hơn cái kia" một lần
    thay vì nhắc lại mỗi lần trò chuyện.
    """
    plan = can_co(token, inp["keHoach"])
    cu = plan.get("uuTien") or "vừa"
    if cu == inp["uuTien"]:
        raise ValueError(f'"{plan["ten"]}" đã ở mức ưu tiên {cu} rồi.')

    notion.set_database_description(token, plan["databaseId"],
                                    f'uuTien={inp["uuTien"]}')
    conn = connect()
    conn.execute("UPDATE keHoach SET uuTien=? WHERE ten=?",
                 (inp["uuTien"], plan["ten"]))
    conn.commit()
    conn.close()
    return (
        {"keHoach": plan["ten"], "uuTien": inp["uuTien"], "previous": cu},
        f'"{plan["ten"]}": ưu tiên {cu} → {inp["uuTien"]}.',
        [{"type": "notion.updateDatabase", "target": plan["databaseId"],
          "idempotencyKey": f'uutien|{plan["ten"]}|{inp["uuTien"]}',
          "reversible": True, "previousValue": f"uuTien={cu}"}],
    )


def add_step(token, inp):
    plan = can_co(token, inp["keHoach"])
    steps = steps_of(token, plan)
    thu_tu = (max(s["thuTu"] for s in steps) + 1) if steps else 1

    props = {
        "Tên":        notion.title_prop(inp["ten"]),
        "Thứ tự":     notion.number_prop(thu_tu),
        "Trạng thái": notion.select_prop("chưa làm"),
        "Ghi chú":    notion.text_prop(inp.get("ghiChu", "")),
    }
    if inp.get("han"):
        props["Hạn"] = notion.date_prop(inp["han"])

    page = notion.create_page(token, plan["databaseId"], props)
    return (
        {"stepId": page["id"], "keHoach": plan["ten"], "ten": inp["ten"],
         "thuTu": thu_tu, "han": inp.get("han"), "url": page.get("url", "")},
        f'Đã thêm bước {thu_tu} vào "{plan["ten"]}": {inp["ten"]}'
        + (f' — hạn {ngay_ngan(inp["han"])}' if inp.get("han") else "") + ".",
        [{"type": "notion.createPage", "target": page["id"],
          "idempotencyKey": f'{plan["ten"]}|{thu_tu}|{inp["ten"]}',
          "reversible": True}],
    )


def _doi_chieu(token, inp):
    """D7 — id thì đúng máy nhưng không đọc được; tên thì đọc được nhưng trùng
    được. Bắt cả hai khớp thì không sửa nhầm được thứ admin vừa duyệt."""
    page = notion.get_page(token, inp["stepId"])
    if page.get("archived"):
        raise ValueError("Bước này đã bị xoá trước đó rồi.")
    cur = row_to_step(page, "")
    if cur["ten"].strip().lower() != " ".join(inp["ten"].split()).lower():
        raise ValueError(
            f'Không khớp: bước đó là "{cur["ten"]}", không phải "{inp["ten"]}". '
            "Em không đụng vào.")
    return cur, page


def _plan_of_page(token, page: dict) -> dict:
    """Bước thuộc kế hoạch nào — suy từ bảng chứa nó, không cần hỏi CEO."""
    goc = (page.get("parent") or {}).get("database_id", "").replace("-", "")
    for p in all_plans(token):
        if p["databaseId"].replace("-", "") == goc:
            return p
    return {"ten": "(không rõ kế hoạch)", "databaseId": "", "hanChot": None}


def update_step(token, inp):
    cur, page = _doi_chieu(token, inp)
    if cur["trangThai"] == inp["trangThai"]:
        raise ValueError(f'Bước này đã ở trạng thái "{inp["trangThai"]}" rồi.')

    notion.update_page(token, inp["stepId"],
                       {"Trạng thái": notion.select_prop(inp["trangThai"])})

    plan = _plan_of_page(token, page)
    anh_em = steps_of(token, plan) if plan["databaseId"] else []
    xong, pct = tien_do(anh_em)

    return (
        {"stepId": inp["stepId"], "keHoach": plan["ten"], "ten": cur["ten"],
         "trangThai": inp["trangThai"], "previousTrangThai": cur["trangThai"],
         "phanTram": pct},
        f'"{cur["ten"]}": {cur["trangThai"]} → {inp["trangThai"]}. '
        + (f'{plan["ten"]} {bar(pct)} {round(pct)}% ({xong}/{len(anh_em)} bước).'
           if anh_em else "")
        + (" Xong cả kế hoạch rồi!" if anh_em and xong == len(anh_em) else ""),
        # D5 — ghi đè thì phải chép lại giá trị cũ, nếu không thì không đổi lại được.
        [{"type": "notion.updatePage", "target": inp["stepId"],
          "idempotencyKey": f'{inp["stepId"]}|{inp["trangThai"]}',
          "reversible": True,
          "previousValue": f'Trạng thái={cur["trangThai"]}'}],
    )


def delete_step(token, inp):
    cur, page = _doi_chieu(token, inp)
    plan = _plan_of_page(token, page)
    notion.archive_page(token, inp["stepId"])
    return (
        {"stepId": inp["stepId"], "keHoach": plan["ten"], "ten": cur["ten"]},
        f'Đã bỏ bước "{cur["ten"]}" khỏi "{plan["ten"]}". '
        "Notion giữ trong thùng rác 30 ngày.",
        [{"type": "notion.archivePage", "target": inp["stepId"],
          "idempotencyKey": f'delete|{inp["stepId"]}', "reversible": True,
          "previousValue": f'{plan["ten"]}|{cur["thuTu"]}|{cur["ten"]}'
                           f'|{cur["trangThai"]}'}],
    )


def archive_plan(token, inp):
    """Bỏ CẢ bảng vào thùng rác Notion.

    Đối chiếu cả tên lẫn SỐ BƯỚC: admin duyệt câu "bỏ kế hoạch X, 6 bước". Con
    số không khớp nghĩa là kế hoạch đã đổi từ lúc admin nhìn thấy, và cái sắp
    mất không còn là cái admin đồng ý bỏ.
    """
    plan = can_co(token, inp["keHoach"])
    steps = steps_of(token, plan)
    if len(steps) != inp["soBuoc"]:
        raise ValueError(
            f'Không khớp: "{plan["ten"]}" đang có {len(steps)} bước, không phải '
            f'{inp["soBuoc"]}. Em không xoá.')

    notion.archive_database(token, plan["databaseId"])
    conn = connect()
    conn.execute("DELETE FROM keHoach WHERE ten=?", (plan["ten"],))
    conn.commit()
    conn.close()

    return (
        {"keHoach": plan["ten"], "soBuoc": len(steps)},
        f'Đã bỏ cả kế hoạch "{plan["ten"]}" ({len(steps)} bước) vào thùng rác. '
        "Notion giữ 30 ngày, khôi phục được.",
        [{"type": "notion.archiveDatabase", "target": plan["databaseId"],
          "idempotencyKey": f'archivePlan|{plan["ten"]}', "reversible": True,
          "previousValue": f'{plan["ten"]}|{len(steps)} bước'}],
    )


HANDLERS = {"listPlans": list_plans, "planSteps": plan_steps,
            "dueSteps": due_steps, "createPlan": create_plan,
            "setPriority": set_priority,
            "addStep": add_step, "updateStep": update_step,
            "deleteStep": delete_step, "archivePlan": archive_plan}


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
    conn.close()

    try:
        handler = HANDLERS.get(cap)
        if handler is None:
            raise ValueError(f"goalCompany không có năng lực '{cap}'")

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
                      summary=f"goalCompany hỏng khi chạy {cap}.")

    duration = int((time.time() - started) * 1000)
    result["usage"] = {"steps": 1, "durationMs": duration, "costUsd": 0.0}

    conn = connect()
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
