#!/usr/bin/env python3
"""panharmonCompany — quản trị nội dung blog panharmon.

Hợp đồng (C1): taskEnvelope trên stdin → companyResult trên stdout.

Company đầu tiên chạm vào một dự án NGOÀI. Ba điều tự đặt cho mình:

  · Cấu hình dự án đọc từ registry/projects.yaml, không viết cứng ở đây. Dự án
    thứ hai đổi một khối khai báo, không đổi code.

  · Ghi xong PHẢI làm mới trang. Next.js dựng tĩnh, nên ghi vào Supabase mà quên
    revalidate thì database đúng còn trang công khai vẫn là bản cũ — hỏng im
    lặng, không lỗi nào báo.

  · dangBai đọc trạng thái CŨ trước khi đổi và khai vào sideEffects (D3). Đăng
    là việc người ngoài nhìn thấy được; không ghi lại được cái gì đã đổi thì
    không ai dựng lại được chuyện gì đã xảy ra.
"""
import json
import os
import re
import sqlite3
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "lib"))
import supabaseClient as sb  # noqa: E402
import repoClient  # noqa: E402   (dùng doc_du_an — danh mục dự án dùng chung)
import db  # noqa: E402

STORE = os.path.join(HERE, "..", "store.sqlite")
TZ = timezone(timedelta(hours=7))
DU_AN = "panharmon"


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ───────────────────────── cấu hình dự án ─────────────────────────

def cau_hinh() -> dict:
    """Khối `noiDung` của dự án, kèm khoá lấy từ biến môi trường."""
    du_an = repoClient.doc_du_an(DU_AN)
    noi_dung = du_an.get("noiDung") or {}
    if noi_dung.get("loai") != "supabase":
        raise ValueError(f"Dự án '{DU_AN}' chưa khai kho nội dung supabase")

    email = os.environ.get(noi_dung.get("bienEmail", ""), "")
    mat_khau = os.environ.get(noi_dung.get("bienMatKhau", ""), "")
    if not (email and mat_khau):
        raise sb.SupabaseError(
            f"Thiếu {noi_dung.get('bienEmail')} / {noi_dung.get('bienMatKhau')} "
            f"trong ops/.env. Đây là tài khoản bot riêng của panharmon — xem ghi "
            f"chú R-KHOÁ trong companySpec.yaml. KHÔNG dùng service_role.")

    # Đăng nhập NGAY tại đây, một lần cho cả lời gọi. Quyền của company từ giờ
    # đúng bằng những gì RLS cho tài khoản này, không hơn.
    khoa = noi_dung["khoaCongKhai"]
    return {
        "url": noi_dung["url"],
        "khoa": khoa,
        "token": sb.dang_nhap(noi_dung["url"], khoa, email, mat_khau),
        "site": du_an.get("site", ""),
        "revalidate": os.environ.get(noi_dung.get("bienRevalidate", ""), ""),
        "duongDanLamMoi": noi_dung.get("duongDanLamMoi") or [],
        "duongDanDuyet": noi_dung.get("duongDanDuyet", "/admin/posts"),
        "danhMucMacDinh": noi_dung.get("danhMucMacDinh", ""),
    }


def tim_danh_muc(cfg: dict, ten: str) -> str | None:
    """id của danh mục theo tên. Không có thì trả None, KHÔNG tự tạo mới.

    Tự tạo danh mục là việc admin không nhờ, và một lần gõ sai tên là đẻ ra
    danh mục rác nằm vĩnh viễn trong menu của site.
    """
    if not ten:
        return None
    hang = sb.chon(cfg["url"], cfg["khoa"], "categories", cot="id,name",
                   token=cfg["token"])
    for h in hang:
        if (h.get("name") or "").strip().lower() == ten.strip().lower():
            return h["id"]
    return None


# ───────────────────────── chuyển đổi nội dung ─────────────────────────

def tao_slug(chu: str) -> str:
    """Bỏ dấu tiếng Việt rồi rút thành slug — khớp cách app tự sinh."""
    chu = chu.replace("đ", "d").replace("Đ", "D")
    chu = unicodedata.normalize("NFD", chu)
    chu = "".join(c for c in chu if unicodedata.category(c) != "Mn")
    chu = re.sub(r"[^a-zA-Z0-9\s-]", "", chu).strip().lower()
    return re.sub(r"[\s-]+", "-", chu)[:200] or "bai-viet"


def sang_tiptap(van_ban: str) -> dict:
    """Văn bản thường → cây tài liệu TipTap.

    VÌ SAO CẦN: cột `content` của posts là JSON TipTap, không phải markdown.
    Nhét markdown thô vào thì bài hiện ra một cục chữ không xuống dòng, không
    tiêu đề — đúng cú pháp nhưng vô dụng.

    Dịch bốn thứ: tiêu đề (#, ##, ###), đoạn văn, danh sách gạch đầu dòng, và
    chữ **đậm**. Đủ đúng khuôn bài panharmon đang có — bài thật dùng cả ba.
    Không cố dịch bảng, ảnh, blockquote: dịch nửa vời còn tệ hơn không dịch, vì
    admin sẽ tưởng nó chạy đúng cho mọi thứ.
    """
    khoi = []
    for doan in re.split(r"\n\s*\n", van_ban.strip()):
        doan = doan.strip()
        if not doan:
            continue

        muc = re.match(r"^(#{1,3})\s+(.*)", doan, re.S)
        if muc:
            khoi.append({
                "type": "heading",
                "attrs": {"level": len(muc.group(1))},
                "content": _chu(muc.group(2).strip()),
            })
            continue

        dong = [d.strip() for d in doan.splitlines() if d.strip()]
        if dong and all(re.match(r"^[-*+]\s+", d) for d in dong):
            khoi.append({
                "type": "bulletList",
                "content": [
                    {"type": "listItem",
                     "content": [{"type": "paragraph",
                                  "content": _chu(re.sub(r"^[-*+]\s+", "", d))}]}
                    for d in dong
                ],
            })
            continue

        khoi.append({"type": "paragraph", "content": _chu(doan)})
    return {"type": "doc", "content": khoi or [{"type": "paragraph"}]}


def _chu(van_ban: str) -> list:
    """Cắt một đoạn thành các mẩu text, mẩu nào trong ** ** thì gắn mark đậm."""
    mau = []
    for phan in re.split(r"(\*\*[^*]+\*\*)", van_ban):
        if not phan:
            continue
        if phan.startswith("**") and phan.endswith("**") and len(phan) > 4:
            mau.append({"type": "text", "text": phan[2:-2],
                        "marks": [{"type": "bold"}]})
        else:
            mau.append({"type": "text", "text": phan})
    return mau or [{"type": "text", "text": van_ban}]


# ───────────────────────── năng lực ─────────────────────────

def list_posts(inp: dict) -> tuple[dict, str, list]:
    cfg = cau_hinh()
    loc = {}
    if inp.get("trangThai"):
        loc["status"] = f"eq.{inp['trangThai']}"
    hang = sb.chon(cfg["url"], cfg["khoa"], "posts", token=cfg["token"],
                   cot="id,title,slug,status,published_at,scheduled_at,updated_at",
                   loc=loc, sap_xep="updated_at.desc",
                   gioi_han=inp.get("gioiHan", 20))
    dong = [f"  [{h.get('status')}] {h.get('title')}" for h in hang[:10]]
    nhan = inp.get("trangThai") or "mọi trạng thái"
    return ({"posts": hang, "count": len(hang)},
            f"{len(hang)} bài ({nhan})" + ("\n" + "\n".join(dong) if dong else ""),
            [])


def doc_noi_dung(inp: dict) -> str:
    """Nội dung bài: hoặc gửi thẳng, hoặc đọc từ file writerCompany vừa viết.

    Chỉ nhận file trong thư mục `out/` của một company. Đường dẫn tuỳ ý là cửa
    để đọc trộm bất cứ file nào trên máy — kể cả ops/.env — chỉ bằng cách bảo
    CEO "tạo bài nháp từ file này".
    """
    if inp.get("noiDung"):
        return inp["noiDung"]

    duong_dan = os.path.abspath(inp["baiVietPath"])
    goc = os.path.abspath(os.path.join(HERE, "..", ".."))       # companies/
    hop_le = (os.path.commonpath([duong_dan, goc]) == goc
              and os.sep + "out" + os.sep in duong_dan)
    if not hop_le:
        raise ValueError(
            f"Chỉ đọc được bài trong thư mục out/ của một company. "
            f"'{inp['baiVietPath']}' nằm ngoài đó.")
    try:
        with open(duong_dan, encoding="utf-8") as fh:
            noi_dung = fh.read().strip()
    except FileNotFoundError:
        raise ValueError(f"Không có file '{inp['baiVietPath']}'. Viết lại bài rồi thử.")
    if not noi_dung:
        raise ValueError(f"File '{inp['baiVietPath']}' rỗng.")
    return noi_dung


def tao_bai_nhap(inp: dict) -> tuple[dict, str, list]:
    cfg = cau_hinh()
    noi_dung = doc_noi_dung(inp)
    slug = tao_slug(inp.get("slug") or inp["tieuDe"])

    # Trùng slug thì Supabase sẽ từ chối (hoặc tệ hơn: đẻ bài trùng đường dẫn).
    # Bắt trước để báo cho CEO bằng tiếng người, thay vì ném lỗi ràng buộc.
    if sb.chon(cfg["url"], cfg["khoa"], "posts", cot="id",
                loc={"slug": f"eq.{slug}"}, token=cfg["token"]):
        raise ValueError(f"Đã có bài dùng đường dẫn '{slug}'. Đặt slug khác.")

    ban_ghi = {
        "title": inp["tieuDe"],
        "slug": slug,
        "excerpt": inp.get("tomTat") or None,
        "content": sang_tiptap(noi_dung),
        "status": "draft",
        # Không có danh mục thì trang công khai hiện không tag nào. Chỉ có một
        # danh mục nên mặc định luôn thay vì bắt CEO đoán uuid.
        "category_id": (inp.get("danhMucId")
                        or tim_danh_muc(cfg, cfg["danhMucMacDinh"])),
        # Bài nháp KHÔNG có ngày đăng. Đặt sẵn published_at cho bài nháp là để
        # lại một quả mìn: đổi status sang published là nó lộ ra với ngày cũ.
        "published_at": None,
        "scheduled_at": None,
        "updated_at": now_utc(),
    }
    moi = sb.them(cfg["url"], cfg["khoa"], "posts", ban_ghi, token=cfg["token"])
    post_id = str(moi.get("id", ""))
    link_duyet = (f"{cfg['site'].rstrip('/')}"
                  + cfg["duongDanDuyet"].replace("{postId}", post_id))

    return (
        {"postId": post_id, "slug": slug, "trangThai": "draft",
         "linkDuyet": link_duyet, "soKyTu": len(noi_dung)},
        # Nói rõ đường công khai KHÔNG mở được. Không nói thì admin tự ghép
        # /giai-ma/<slug> rồi gặp 404 và tưởng hệ hỏng — đã xảy ra hai lần.
        f"Đã tạo bài nháp '{inp['tieuDe']}' ({len(noi_dung)} ký tự). "
        f"Bài nháp KHÔNG mở được bằng link công khai (sẽ 404) — xem tại "
        f"{link_duyet}",
        [{"type": "record.create", "target": f"panharmon/posts/{post_id}",
          "reversible": True}],
    )


def dang_bai(inp: dict) -> tuple[dict, str, list]:
    cfg = cau_hinh()
    post_id = inp["postId"]

    cu = sb.chon(cfg["url"], cfg["khoa"], "posts", cot="id,title,slug,status",
                 loc={"id": f"eq.{post_id}"}, token=cfg["token"])
    if not cu:
        raise ValueError(f"Không có bài nào mang id '{post_id}'. Gọi listPosts để tra.")
    cu = cu[0]

    # D7 — đối chiếu tiêu đề. Nhầm một ký tự trong uuid mà cứ thế đăng thì admin
    # chỉ phát hiện khi bài đã nằm trên internet.
    if cu.get("title", "").strip() != inp["tieuDe"].strip():
        raise ValueError(
            f"Tiêu đề không khớp. id '{post_id}' đang là '{cu.get('title')}', "
            f"không phải '{inp['tieuDe']}'. Dừng lại để khỏi đăng nhầm bài.")

    hen = (inp.get("henGio") or "").strip()
    thay_doi = {
        "status": "scheduled" if hen else "published",
        "published_at": None if hen else now_utc(),
        "scheduled_at": hen or None,
        "updated_at": now_utc(),
    }
    sb.sua(cfg["url"], cfg["khoa"], "posts", {"id": f"eq.{post_id}"},
           thay_doi, token=cfg["token"])

    # Làm mới trang tĩnh. Ghi được mà không làm mới thì coi như chưa đăng.
    da_lam_moi = False
    if cfg["revalidate"] and cfg["site"]:
        for duong_dan in [*cfg["duongDanLamMoi"], f"/blog/{cu.get('slug')}",
                          f"/giai-ma/{cu.get('slug')}"]:
            sb.lam_moi_trang(cfg["site"], cfg["revalidate"], duong_dan)
        da_lam_moi = True

    link = f"{cfg['site'].rstrip('/')}/blog/{cu.get('slug')}"
    trang_thai = thay_doi["status"]
    return (
        {"postId": post_id, "trangThai": trang_thai, "link": link,
         "daLamMoi": da_lam_moi},
        (f"Đã hẹn đăng '{cu.get('title')}' lúc {hen}." if hen
         else f"Đã đăng '{cu.get('title')}' — {link}")
        + ("" if da_lam_moi else " CẢNH BÁO: chưa làm mới được trang, "
                                "bản công khai có thể còn là bản cũ."),
        [{"type": "record.update", "target": f"panharmon/posts/{post_id}",
          "reversible": False, "previousValue": cu.get("status")}],
    )


HANDLERS = {"listPosts": list_posts, "taoBaiNhap": tao_bai_nhap,
            "dangBai": dang_bai}


# ───────────────────────── khung chạy ─────────────────────────

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
            raise ValueError(f"panharmonCompany không có năng lực '{cap}'")

        if dry_run:  # W2
            result.update(status="ok", output=None,
                          summary=f"[dryRun] Sẽ chạy {cap} với "
                                  f"{json.dumps(inp, ensure_ascii=False)[:180]}")
        else:
            output, summary, side_effects = handler(inp)
            result.update(status="ok", output=output, summary=summary,
                          sideEffects=side_effects)

    except sb.SupabaseError as exc:
        result.update(status="failed", error=str(exc),
                      summary=f"Panharmon không phản hồi đúng: {exc}")
    except repoClient.RepoError as exc:
        result.update(status="failed", error=str(exc),
                      summary=f"Cấu hình dự án hỏng: {exc}")
    except ValueError as exc:
        # Lỗi do dữ liệu đưa vào — nói rõ để CEO hỏi lại, đừng đoán.
        result.update(status="needsInput", error=str(exc), summary=str(exc))
    except Exception as exc:  # O3
        result.update(status="failed", error=f"{type(exc).__name__}: {exc}",
                      summary=f"panharmonCompany hỏng khi chạy {cap}.")

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
