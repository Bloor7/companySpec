#!/usr/bin/env python3
"""scheduledTrigger — cửa vào thứ hai của hệ (§12c).

Chạy 15 phút một lần bằng systemd timer. Đọc registry/schedules.yaml, xem lịch
nào tới hạn, chạy, rồi gửi kết quả về Telegram.

VÌ SAO CỬA NÀY HẸP HƠN CỬA CỦA ADMIN:
với adminMessage thì admin đang cầm điện thoại — hỏi được. Với cron thì admin
đang ngủ, nên mọi guardrail dựa trên "hỏi admin" mất tác dụng. Bù lại bằng
cách thu hẹp: chỉ đọc, chỉ lịch đã khai trước, không LLM trừ khi thật cần.

    python3 ops/scheduler.py run          # chạy lịch tới hạn (timer gọi)
    python3 ops/scheduler.py run --force morningReport   # chạy tay để thử
    python3 ops/scheduler.py list         # xem lịch và lần chạy gần nhất
"""
import argparse
import calendar
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backOffice", "src"))

import approvals  # noqa: E402
import telegram  # noqa: E402
import backoffice as bo  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "lib"))
import db  # noqa: E402

SCHEDULES = os.path.join(ROOT, "registry", "schedules.yaml")
STORE = os.path.join(ROOT, "backOffice", "store.sqlite")
TZ = timezone(timedelta(hours=7))


def now_local() -> datetime:
    return datetime.now(TZ)


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def store():
    conn = db.connect(STORE)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS scheduleRun (
          runId INTEGER PRIMARY KEY AUTOINCREMENT,
          scheduleId TEXT NOT NULL, traceId TEXT NOT NULL,
          status TEXT NOT NULL, summary TEXT, sentToAdmin INTEGER NOT NULL DEFAULT 0,
          createdAt TEXT NOT NULL)"""
    )
    conn.commit()
    return conn


def load_schedules() -> list:
    if not os.path.isfile(SCHEDULES):
        return []
    data = yaml.safe_load(open(SCHEDULES, encoding="utf-8")) or {}
    return [s for s in (data.get("schedules") or []) if s.get("enabled", True)]


def last_run(conn, schedule_id: str):
    row = conn.execute(
        "SELECT createdAt FROM scheduleRun WHERE scheduleId=? AND status!='skipped' "
        "ORDER BY runId DESC LIMIT 1", (schedule_id,)).fetchone()
    if not row:
        return None
    return datetime.strptime(row["createdAt"], "%Y-%m-%dT%H:%M:%SZ") \
        .replace(tzinfo=timezone.utc)


def is_due(sched: dict, prev, now: datetime) -> bool:
    """Tới hạn chưa. Bộ chạy 15 phút/lần nên phải chịu được lệch vài phút."""
    if "everyHours" in sched:
        if prev is None:
            return True
        gap = (datetime.now(timezone.utc) - prev).total_seconds() / 3600
        return gap >= sched["everyHours"] - 0.1

    at = sched.get("at")
    if not at:
        return False
    hh, mm = (int(x) for x in at.split(":"))
    # isoweekday: 1=Hai … 7=CN. Cấu hình dùng 2..8 cho quen mắt người Việt.
    if sched.get("days") and (now.isoweekday() + 1) not in sched["days"]:
        return False

    # Nhịp tháng. Khai `dayOfMonth: 5` là mùng 5 hằng tháng.
    #
    # Ngày khai lớn hơn số ngày của tháng thì chạy vào ngày CUỐI tháng: khai 31
    # mà tháng 2 bỏ qua thì lịch im lặng mất một tháng, và loại im lặng đó không
    # ai phát hiện ra cho tới lúc cần nó nhất.
    dom = sched.get("dayOfMonth")
    if dom:
        last = calendar.monthrange(now.year, now.month)[1]
        if now.day != min(dom, last):
            return False
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if now < target:
        return False
    # Đã chạy sau mốc hôm nay rồi thì thôi.
    return prev is None or prev < target.astimezone(timezone.utc)


# ───────────────────────── nội dung báo cáo ─────────────────────────

def tien(x) -> str:
    return f"{x:,.0f}đ".replace(",", ".")


def section_quota() -> tuple[str, bool]:
    """Chi phí đã tiêu, và những lần THẬT SỰ chạm trần.

    Bản cũ so chi phí với một ngưỡng đoán rồi kêu "sắp chạm trần". Bỏ ngày
    2026-08-16: con số đó hệ tự cộng từ bảng giá token, không phải hạn mức
    thật của gói Pro — nên lời cảnh báo vừa không đáng tin vừa làm admin lo
    hão. Giờ chỉ nói số đã tiêu (thông tin), và chỉ ĐÁNG BÁO khi Anthropic
    thật sự đã chặn (lib/quotaSignal.py bắt được).
    """
    q = bo.chi_phi_gan_day()
    w5, wk = q["window5h"], q["week"]
    body = (f"Đã tiêu 5 tiếng qua: ${w5['total']:.2f}\n"
            f"Tuần này: ${wk['total']:.2f}")
    hits = [h for h in q["hits"]
            if h["createdAt"] >= (datetime.now(timezone.utc) - timedelta(days=1))
            .strftime("%Y-%m-%dT%H:%M:%SZ")]
    if hits:
        h = hits[0]
        return (f"⛔ Hết hạn mức {h['loai']} lúc {h['createdAt'][11:16]} hôm qua"
                + (f", mở lại {h['resetLuc']}" if h["resetLuc"] else "")
                + f" ({len(hits)} lần trong 24h).\n" + body), True
    return body, False   # bình thường thì không có gì đáng báo


def section_activity() -> tuple[str, bool]:
    """Hoạt động 24h, TÁCH theo loại kết cục.

    Bản đầu in "2/4 thành công" — đếm status='ok' trên tổng lời gọi. Nhưng
    `needsApproval` là luồng BÌNH THƯỜNG: nó nghĩa là hệ đã dừng đúng chỗ và
    đang chờ admin bấm nút. Gộp nó vào "không thành công" khiến một ngày làm
    việc trơn tru trông như hỏng liên tục — admin đọc xong hoang mang mà không
    có gì để sửa. Đo được 2026-08-04: 83 lần chờ duyệt bị đếm là thất bại.

    Chỉ `failed` mới đáng đánh thức admin; `rejected` là guardrail làm đúng việc.
    """
    conn = store()
    since = (datetime.now(timezone.utc) - timedelta(days=1)) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = list(conn.execute(
        "SELECT companyId, "
        "SUM(status='ok') xong, SUM(status='needsApproval') cho, "
        "SUM(status IN ('rejected','needsInput')) chan, SUM(status='failed') hong "
        "FROM taskLog WHERE startedAt >= ? GROUP BY 1 "
        "ORDER BY xong+cho+chan+hong DESC", (since,)))
    conn.close()
    if not rows:
        return "Hôm qua không có việc nào.", False

    lines, co_hong = [], False
    for r in rows:
        phan = [f"{r['xong']} xong"]
        if r["cho"]:
            phan.append(f"{r['cho']} chờ duyệt")
        if r["chan"]:
            phan.append(f"{r['chan']} bị chặn")
        if r["hong"]:
            phan.append(f"{r['hong']} HỎNG")
            co_hong = True
        lines.append(f"  {r['companyId']}: " + " · ".join(phan))
    ghi_chu = ("" if co_hong else
               "\n(chờ duyệt là bình thường — hệ dừng đúng chỗ để hỏi đại ca)")
    return "24 giờ qua:\n" + "\n".join(lines) + ghi_chu, co_hong


def section_approvals() -> tuple[str, bool]:
    conn = approvals.store()
    rows = list(conn.execute(
        "SELECT approvalId, companyId, capability, consequence FROM approvalRequest "
        "WHERE status='pending' ORDER BY rowid"))
    conn.close()
    if not rows:
        return "", False
    lines = [f"  {r['companyId']}.{r['capability']}" for r in rows[:5]]
    return (f"⏳ {len(rows)} việc đang chờ đại ca duyệt:\n" + "\n".join(lines)
            + "\nNhắn lại việc đó để em hỏi duyệt lần nữa."), True


def section_permissions() -> tuple[str, bool]:
    soon, unused = [], []
    conn = store()
    for r in approvals.active_rules():
        days = (approvals.parse(r["expiresAt"]) - approvals.now_dt()).days
        used = conn.execute(
            "SELECT COUNT(*) FROM taskLog WHERE companyId=? AND capability=? "
            "AND status='ok' AND startedAt >= ?",
            (r["companyId"], r["capability"], r["createdAt"])).fetchone()[0]
        scope = ", ".join(str(v) for v in r["scope"].values() if v)
        if days <= 14:
            soon.append(f"  {r['capability']} ({scope}) còn {days} ngày")
        elif used == 0:
            unused.append(f"  {r['capability']} ({scope}) chưa dùng lần nào")
    conn.close()
    parts = []
    if soon:
        parts.append("Quyền sắp hết hạn:\n" + "\n".join(soon))
    if unused:
        parts.append("Quyền cấp rồi chưa dùng — cân nhắc thu hồi:\n" + "\n".join(unused))
    return "\n\n".join(parts), bool(parts)


def section_agenda() -> tuple[str, bool]:
    """Lịch hôm nay, đặt ĐẦU tin sáng: đó là thứ admin cần biết trước tiên khi
    vừa dậy, trước cả hạn mức hay tiến độ video."""
    res = call_company("calendarCompany", "todayAgenda", {})
    if res.get("status") != "ok":
        return "", False
    sm = res.get("summary", "")
    # "không có lịch gì" vẫn đáng in trong báo cáo sáng, nhưng không tính là
    # chuyện đáng để đánh thức admin (notable=False).
    return sm, (res.get("output", {}) or {}).get("count", 0) > 0


def section_tienbac() -> tuple[str, bool]:
    """Báo cáo tiền cuối ngày — ghép năm company thành một bức tranh.

    ĐÂY là chỗ đúng để tổng hợp. Company không được đọc sổ của nhau (C3), nhưng
    scheduler đứng trên tất cả và được phép gọi từng cái rồi tự cộng trừ — bằng
    code cứng nên không tốn một đồng hạn mức nào.

    Việc quan trọng nhất ở đây KHÔNG phải in số dư, mà là ĐỐI CHIẾU: ví nói một
    đằng, sổ thu chi nói một nẻo thì phải kêu lên trong 24 giờ. Ví cộng trừ thủ
    công nên sai sót là chuyện sẽ xảy ra; cái không được phép xảy ra là sai sót
    tích luỹ âm thầm hàng tháng rồi không ai lần ra nữa.
    """
    vi = call_company("walletCompany", "getBalance", {})
    if vi.get("status") != "ok":
        return "", False
    vo = vi.get("output") or {}
    if not (vo.get("vi") or []):
        return ("Chưa có ví nào — nhắn em số tiền đang có để bắt đầu theo dõi."), True

    hom_nay = now_local().strftime("%Y-%m-%d")
    dau_thang = now_local().strftime("%Y-%m-01")

    parts = ["Đang có: " + " · ".join(
        f'{v["vi"]} {tien(v["soTien"])}' for v in vo["vi"])
        + f'\nTổng: {tien(vo.get("tong", 0))}']

    # Tên trường phải khớp inputSchema của company: `tuNgay`/`denNgay`, KHÔNG
    # phải `from`/`to`. Cả hai sổ khai `additionalProperties: false`, nên gửi
    # `from` bị dispatcher trả `rejected` chứ không phải lọc sai — và đoạn code
    # cũ nuốt lỗi bằng `or {}` rồi in ra 0đ.
    # Đo được 2026-08-13: `--input '{"from":"2026-08-13"}'` →
    # "C2.3 — input sai schema: input.from: trường không được khai báo".
    # Báo cáo tối nào cũng nói "thu 0 · chi 0" và mọi hạn mức đứng ở 0%, trong
    # khi hỏi lại CEO thì đúng — vì CEO gọi bằng đúng tên trường trong hợp đồng.
    loi: list = []
    thu_ngay = doc_output("incomeCompany", "sumIncomes", {"tuNgay": hom_nay}, loi)
    chi_ngay = doc_output("expenseCompany", "sumExpenses", {"tuNgay": hom_nay}, loi)
    parts.append(f"Hôm nay: thu {tien(thu_ngay.get('total') or 0)}"
                 f" · chi {tien(chi_ngay.get('total') or 0)}")

    # Ngân sách tháng: ghép hạn mức (budgetCompany) với thực tế (expenseCompany).
    ns = doc_output("budgetCompany", "getBudget", {}, loi)
    han = ns.get("hanMuc") or {}
    dat_luc = ns.get("datLuc") or {}
    if han:
        canh, on, con = [], [], 0
        for dm, muc in sorted(han.items(), key=lambda kv: -kv[1]):
            # Đếm chi tiêu TỪ LÚC ĐẶT HẠN MỨC, không phải từ đầu tháng.
            # Admin đặt "ăn uống 3 triệu" lúc 12:49 là nói về phần còn lại của
            # tháng; trừ ngược những gì đã tiêu buổi sáng là hiểu sai ý và làm
            # hạn mức trông như đã dùng hết trong khi chưa tiêu đồng nào.
            tu = dat_luc.get(dm) or dau_thang
            o = doc_output("expenseCompany", "sumExpenses", {"tuNgay": tu}, loi)
            da = (o.get("byCategory") or {}).get(dm, 0)
            con += muc - da
            pct = round(da / muc * 100) if muc else 0
            moc = f" (từ {tu[8:10]}/{tu[5:7]})" if tu != dau_thang else ""
            (canh if pct >= 80 else on).append(
                f"  {dm}: {tien(da)}/{tien(muc)} ({pct}%){moc}")
        if canh:
            parts.append("⚠ Sắp/đã vượt hạn mức:\n" + "\n".join(canh))
        if on:
            parts.append("Trong hạn mức:\n" + "\n".join(on))
        parts.append(f"Ngân sách còn: {tien(con)}")

    quy = doc_output("savingsCompany", "fundProgress", {}, loi)
    if quy.get("canMoiThang"):
        parts.append(f"Quỹ cần nạp: {tien(quy['canMoiThang'])}/tháng")

    # O3 — hỏng thì hỏng TO. Một con số 0 trông y hệt "hôm nay không tiêu gì",
    # nên lời gọi hỏng mà im lặng là kiểu sai tệ nhất: báo cáo vẫn đẹp, vẫn gửi
    # đúng giờ, và admin tin nó suốt nhiều tuần. Thà nói thẳng là số này không
    # đọc được còn hơn đưa ra một con số bịa.
    if loi:
        parts.append("⚠ Có số em KHÔNG đọc được, đừng tin con số phía trên:\n"
                     + "\n".join("  " + d for d in loi))

    return "\n\n".join(parts), True


def _nhip(nguon: str, xong: int) -> str:
    """Ghi tiến độ hôm nay, trả về câu mô tả NHÚC NHÍCH so với hôm trước.

    VÌ SAO: báo cáo cũ chỉ in trạng thái ("0/90"), mà trạng thái không đổi thì
    câu chữ cũng không đổi — sáng thứ ba là admin lướt qua không đọc nữa. Thứ
    admin cần cảm nhận là TIẾN hay LÙI, và cái đó chỉ hiện ra khi so với hôm
    qua. Hệ trước đây không nhớ hôm qua bao nhiêu, nên phải tự ghi lấy.

    Ghi theo NGÀY (giờ VN), khoá trùng thì đè: báo cáo chạy lại hai lần trong
    cùng một ngày không được đẻ ra hai mốc, nếu không số ngày đứng im sẽ sai.
    """
    hom_nay = now_local().strftime("%Y-%m-%d")
    conn = db.connect(STORE)
    conn.execute("""CREATE TABLE IF NOT EXISTS progressHistory (
        ngay TEXT, nguon TEXT, xong INTEGER, PRIMARY KEY (ngay, nguon))""")

    # Các mốc CŨ HƠN hôm nay. Không lấy mốc hôm nay: nó chính là cái ta sắp ghi.
    truoc = conn.execute(
        "SELECT ngay, xong FROM progressHistory WHERE nguon=? AND ngay<? "
        "ORDER BY ngay DESC", (nguon, hom_nay)).fetchall()
    conn.execute("INSERT OR REPLACE INTO progressHistory (ngay, nguon, xong) "
                 "VALUES (?,?,?)", (hom_nay, nguon, xong))
    conn.commit()
    conn.close()

    if not truoc:
        return "bắt đầu đếm từ hôm nay"
    if truoc[0]["xong"] != xong:
        chenh = xong - truoc[0]["xong"]
        return f"+{chenh} từ lần trước" if chenh > 0 else f"{chenh} từ lần trước"

    # Đứng im: lùi về mốc XA NHẤT còn giữ nguyên con số này, đó là lúc nó dừng.
    dung = truoc[0]["ngay"]
    for r in truoc:
        if r["xong"] != xong:
            break
        dung = r["ngay"]
    ngay_im = (now_local().date() - datetime.strptime(dung, "%Y-%m-%d").date()).days
    return f"{ngay_im} ngày chưa nhúc nhích" if ngay_im else "chưa nhúc nhích"


def _ten_ngan(ten: str, gioi_han: int = 34) -> str:
    """Tên kế hoạch đủ ngắn để lọt một dòng điện thoại, cắt ở ranh giới từ.

    Admin đặt tên dài kèm mô tả ("Học tiếng Anh giao tiếp 3 tháng - mất gốc -
    1 tiếng mỗi ngày"). Cắt cứng theo ký tự ra "mất gố" — đọc như lỗi hiển thị.
    """
    ten = ten.split(" - ")[0].strip()          # phần trước gạch là tên thật
    if len(ten) <= gioi_han:
        return ten
    return ten[:gioi_han].rsplit(" ", 1)[0] + "…"


def section_plan() -> tuple[str, bool]:
    """Tiến độ mọi thứ admin đang theo đuổi, kèm nhịp tiến/lùi.

    Gộp cả planCompany (90 video) lẫn goalCompany (các kế hoạch khác): trước đây
    mục này chỉ có video, nên kế hoạch học tiếng Anh và KDP không hề xuất hiện
    trong báo cáo hằng ngày — chúng chỉ nằm ở goalNudge sáng thứ Hai.
    """
    dong = []

    # Video đo bằng SỐ VIDEO ĐÃ ĐĂNG (0/90), không phải số bước chuẩn bị (0/4)
    # mà goalCompany giữ. Cùng một mục tiêu, hai thước đo — in cả hai thì admin
    # đọc ra hai con số đá nhau. Lấy thước đo có ý nghĩa hơn, bỏ cái kia.
    video = call_company("planCompany", "progressReport", {})
    if video.get("status") == "ok":
        o = video.get("output", {}) or {}
        xong, tong = int(o.get("done", 0)), int(o.get("total", 0))
        dong.append(f"Video: {xong}/{tong} đã đăng · {_nhip('video', xong)}")

    kh = call_company("goalCompany", "listPlans", {})
    if kh.get("status") == "ok":
        for p in (kh.get("output", {}) or {}).get("plans", []):
            ten, xong, tong = p["keHoach"], int(p["xong"]), int(p["soBuoc"])
            # Kế hoạch video đã có dòng riêng ở trên. Nếu admin đổi tên làm mất
            # chữ "video" thì cùng lắm là thừa một dòng, không sai số liệu.
            if dong and "video" in ten.lower():
                continue
            dong.append(f"{_ten_ngan(ten)}: {xong}/{tong} bước · "
                        f"{_nhip('goal:' + ten, xong)}")

    if not dong:
        return "", False
    return "Tiến độ:\n  " + "\n  ".join(dong), True


SECTIONS = {"agenda": section_agenda, "tienbac": section_tienbac,
            "quota": section_quota,
            "activity": section_activity, "approvals": section_approvals,
            "permissions": section_permissions, "plan": section_plan}


# ───────────────────────── chạy ─────────────────────────

def call_company(company_id: str, capability: str, inp: dict) -> dict:
    """S1/S3 — đi qua dispatcher như mọi lời gọi khác, nhưng khai issuedBy là
    scheduledTrigger. Dispatcher tự chặn nếu năng lực đó là write."""
    trace = "trc_cron_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "ops", "dispatch.py"), "call",
         "--company", company_id, "--capability", capability,
         "--input", json.dumps(inp, ensure_ascii=False),
         "--trace", trace, "--issued-by", "scheduledTrigger"],
        capture_output=True, text=True, cwd=ROOT, timeout=300)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"status": "failed", "summary": proc.stderr.strip()[:200]}


def doc_output(company_id: str, capability: str, inp: dict, loi: list) -> dict:
    """Như call_company nhưng CHỈ trả output khi status là ok, còn lại ghi vào `loi`.

    VÌ SAO PHẢI CÓ: `call_company(...).get("output") or {}` biến mọi thất bại
    thành một dict rỗng, và dict rỗng đi qua `.get('total') or 0` thành số 0.
    Số 0 đó không phân biệt được với "hôm nay không tiêu gì" — nên báo cáo tối
    vẫn gửi đúng giờ, vẫn đẹp, và vẫn sai suốt nhiều tuần mà không ai biết.
    Đo được 2026-08-13: sumIncomes/sumExpenses bị `rejected` vì sai tên trường,
    mà báo cáo không hề hé một chữ nào về chuyện đó.
    """
    r = call_company(company_id, capability, inp)
    if r.get("status") == "ok":
        return r.get("output") or {}
    loi.append(f'{company_id}.{capability}: {r.get("status")} — '
               f'{(r.get("summary") or r.get("error") or "")[:120]}')
    return {}


def run_one(sched: dict, conn) -> tuple[str, str]:
    """Trả (nội dung gửi admin, trạng thái). Nội dung rỗng = không gửi gì."""
    parts, anything = [], False

    if sched["kind"] == "digest":
        for name in sched.get("sections", []):
            fn = SECTIONS.get(name)
            if fn is None:
                continue
            text, notable = fn()
            if text:
                parts.append(text)
            anything = anything or notable

    elif sched["kind"] == "companyCall":
        res = call_company(sched["companyId"], sched["capability"],
                           sched.get("input", {}))
        if res.get("status") == "ok":
            parts.append(res.get("summary", ""))
            # Company trả summary rỗng = "không có gì để nói". Nhờ quy ước này,
            # `quietIfEmpty` dùng được cho companyCall chứ không chỉ cho digest:
            # lịch nhắc mà tháng nào cũng nhắn kể cả khi không có việc thì admin
            # sẽ ngừng đọc, và lúc có việc thật cũng không ai để ý (S7).
            anything = bool(res.get("summary", "").strip())
        else:
            parts.append(f"Không chạy được {sched['companyId']}."
                         f"{sched['capability']}: {res.get('summary', '')[:150]}")
            anything = True
    else:
        return "", "failed"

    if sched.get("quietIfEmpty") and not anything:
        return "", "skipped"

    header = f"— {sched['displayName']} —"
    return header + "\n\n" + "\n\n".join(p for p in parts if p), "ok"


def cmd_run(args):
    admin = os.environ.get("COMPANYSPEC_ADMIN_CHAT_ID", "")
    if not admin:
        print("Thiếu COMPANYSPEC_ADMIN_CHAT_ID (F6).", file=sys.stderr)
        return 1

    conn = store()
    now = now_local()
    ran = 0

    for sched in load_schedules():
        sid = sched["scheduleId"]
        if args.force and sid != args.force:
            continue
        if not args.force and not is_due(sched, last_run(conn, sid), now):
            continue

        try:
            text, status = run_one(sched, conn)
        except Exception as exc:
            text, status = f"— {sched['displayName']} —\n\nLỗi: {exc}", "failed"

        sent = 0
        if text:
            res = telegram.send_message(admin, text)
            sent = 1 if res.get("ok") else 0

        conn.execute(
            "INSERT INTO scheduleRun (scheduleId, traceId, status, summary, "
            "sentToAdmin, createdAt) VALUES (?,?,?,?,?,?)",
            (sid, "trc_cron_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
             status, (text or "")[:400], sent, now_utc()))
        conn.commit()
        ran += 1
        print(f"[scheduler] {sid}: {status}" + (" (đã gửi)" if sent else ""))

    conn.close()
    if ran == 0:
        print("[scheduler] không có lịch nào tới hạn")
    return 0


def cmd_list(args):
    conn = store()
    now = now_local()
    print(f"Bây giờ: {now:%Y-%m-%d %H:%M} (giờ VN)\n")
    for sched in load_schedules():
        prev = last_run(conn, sched["scheduleId"])
        when = sched.get("at") or f"mỗi {sched.get('everyHours')} tiếng"
        if sched.get("dayOfMonth"):
            when += f" mùng {sched['dayOfMonth']}"
        due = "TỚI HẠN" if is_due(sched, prev, now) else "chưa"
        prev_s = prev.astimezone(TZ).strftime("%d/%m %H:%M") if prev else "chưa bao giờ"
        print(f"  {sched['scheduleId']:<16}{when:<18}lần cuối {prev_s:<14}{due}")
    conn.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="scheduledTrigger — việc định kỳ")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--force", help="chạy thẳng một scheduleId, bỏ qua kiểm tới hạn")
    r.set_defaults(fn=cmd_run)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
