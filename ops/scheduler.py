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


def trang_thai_truoc(conn, schedule_id: str):
    """Kết cục lần chạy gần nhất. Bỏ qua 'skipped' — im vì không có gì để nói
    thì không phải một kết cục, và nó không được xoá dấu vết lần hỏng trước đó."""
    row = conn.execute(
        "SELECT status FROM scheduleRun WHERE scheduleId=? AND status!='skipped' "
        "ORDER BY runId DESC LIMIT 1", (schedule_id,)).fetchone()
    return row["status"] if row else None


def so_lan_hong_lien_tiep(conn, schedule_id: str) -> int:
    """Đếm ngược từ lần gần nhất, dừng khi gặp một lần không hỏng."""
    n = 0
    for r in conn.execute(
            "SELECT status FROM scheduleRun WHERE scheduleId=? AND status!='skipped' "
            "ORDER BY runId DESC LIMIT 200", (schedule_id,)):
        if r["status"] != "failed":
            break
        n += 1
    return n


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
    # Nói rõ phần ca thử khi có. Không nói thì một đêm chạy eval trông y hệt
    # một đêm admin dùng nhiều, và admin sẽ đi tìm nguyên nhân không tồn tại.
    if wk.get("caThu"):
        body += f" (trong đó ca thử ${wk['caThu']:.2f})"

    # TIỀN THẬT (L8) — chỉ nói khi có, nhưng nói TRƯỚC phần hạn mức Pro: đây là
    # tiền trừ vào thẻ admin, còn phần kia là hạn mức dùng hết thì thôi.
    t = bo.tien_that_thang()
    if t["tong"]:
        pct = (t["tong"] / t["tran"] * 100) if t["tran"] else 0
        dong = f"Tiền thật tháng này: {t['tong']:,.0f}đ / {t['tran']:,.0f}đ ({pct:.0f}%)"
        if pct >= t["canhBaoTaiPhanTram"]:
            return (f"⚠ {dong} — sắp chạm trần, chạm là hệ ngừng gọi API tính tiền.\n"
                    + body), True
        body = dong + "\n" + body
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
        # ĐẾM CẢ THÁNG, không đếm từ lúc đặt hạn mức.
        #
        # Bản cũ lọc theo `datLuc` với lý do: admin đặt "ăn uống 3 triệu" lúc
        # trưa là nói về phần còn lại của tháng, trừ ngược buổi sáng là hiểu sai
        # ý. Lý do đó nghe được, nhưng nó MÂU THUẪN VỚI CHÍNH CÁI TÊN: trường
        # đầu vào là `thang`, nhãn in ra là "Hạn mức tháng". Đã gọi là hạn mức
        # tháng thì phải đếm cả tháng.
        #
        # Đo được 2026-08-18/19, hạn mức ăn uống 5 triệu đặt lúc 16/08 20:16:
        #   · đếm từ mốc  →  đã tiêu 211.000đ  →  báo "còn 4.789.000đ"
        #   · đếm cả tháng → đã tiêu 3.908.846đ → đúng phải là "còn 1.091.154đ"
        # Admin phát hiện vì CEO khi ĐƯỢC HỎI thì tính cả tháng và ra số đúng,
        # còn báo cáo tối thì ra số kia — hai nơi trong cùng một hệ nói hai con
        # số khác nhau về cùng một thứ, và admin không có cách nào biết tin cái
        # nào. Sai theo hướng TRẤN AN: báo còn 4,7 triệu trong khi ví có 23.020đ.
        #
        # `datLuc` vẫn giữ, nhưng làm GHI CHÚ chứ không làm bộ lọc — admin nhìn
        # thấy hạn mức đặt ngày nào là đủ để tự hiểu, không cần hệ âm thầm đổi
        # mẫu số hộ.
        for dm, muc in sorted(han.items(), key=lambda kv: -kv[1]):
            o = doc_output("expenseCompany", "sumExpenses",
                           {"tuNgay": dau_thang}, loi)
            da = (o.get("byCategory") or {}).get(dm, 0)
            con += muc - da
            pct = round(da / muc * 100) if muc else 0
            dl = dat_luc.get(dm) or ""
            moc = f" (đặt {dl[8:10]}/{dl[5:7]})" if dl[:10] > dau_thang else ""
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


GIAO_TRINH = os.path.join(ROOT, "registry", "giaotrinh-ngoaingu.yaml")


def _bai_hom_nay():
    """(giáo trình, bài đang học, câu báo lỗi, đã học hết chưa).

    Bài nào là bài HÔM NAY do TIẾN ĐỘ ADMIN TÍCH quyết định, không do lịch:
    hỏi goalCompany bước nào chưa "xong", bước đầu tiên chưa xong chính là bài
    đang học. Admin bảo "xong bài 1 rồi" thì CEO tích, hôm sau tự sang bài 2.

    VÌ SAO BỎ CÁCH TÍNH THEO NGÀY (2026-08-20): học nhanh chậm tuỳ hôm, mà
    lịch thì không biết điều đó. Lịch đi trước tiến độ thì admin nhận bài mới
    trong khi bài cũ chưa thuộc; lịch đi sau thì nhận lại bài đã thuộc rồi.
    Bản trước phải khai `soNgayMoiBai` để chỉnh tay, và mỗi lần đổi nhịp là
    một lần phải nhớ sửa. Tiến độ tự nó không bao giờ lệch.

    Cái giá: mỗi lần gửi tin phải hỏi Notion một câu (`read`, S3 cho phép,
    không tốn hạn mức LLM). Đổi lại không còn con số nào phải chỉnh tay.
    """
    try:
        with open(GIAO_TRINH, encoding="utf-8") as fh:
            gt = yaml.safe_load(fh) or {}
    except OSError as e:
        # O10 — thiếu giáo trình là chuyện phải BIẾT, không im lặng bỏ qua.
        return None, None, f"Không đọc được giáo trình ({e.__class__.__name__}).", False

    bai = gt.get("bai") or []
    ke_hoach = (gt.get("keHoach") or "").strip()
    if not bai:
        return gt, None, None, False
    if not ke_hoach:
        return gt, None, "Giáo trình chưa khai `keHoach` nên em không tra được tiến độ.", False

    loi: list = []
    o = doc_output("goalCompany", "planSteps", {"keHoach": ke_hoach}, loi)
    if loi:
        # KHÔNG đoán bài. Tra hỏng mà vẫn gửi bài nào đó thì admin học nhầm bài
        # và không có cách nào biết — im lặng sai còn tệ hơn không gửi.
        return gt, None, f"Chưa tra được tiến độ ({loi[0]}).", False

    steps = o.get("steps") or []
    if not steps:
        return gt, None, (f'Chưa thấy kế hoạch "{ke_hoach}" trên Notion, '
                          "hoặc nó chưa có bước nào."), False

    # Số bước phải BẰNG số bài, không phải chỉ "đủ dùng". Bảng Notion được
    # sinh ra từ chính file giáo trình nên lệch nghĩa là một bên đã đổi mà bên
    # kia chưa. Ít bước hơn số bài là kiểu lệch nguy nhất: admin tích hết bảng,
    # hệ báo "xong cả giáo trình", mà mấy bài cuối chưa từng được gửi — sai mà
    # trông y hệt đúng. Bản đầu chỉ chặn chiều ngược lại; thử ra mới thấy.
    if len(steps) != len(bai):
        return gt, None, (f"Kế hoạch trên Notion có {len(steps)} bước nhưng giáo "
                          f"trình có {len(bai)} bài — hai bên lệch nhau nên em "
                          "chưa dám gửi. Dựng lại bảng cho khớp đã."), False

    chua = [x for x in steps if (x.get("trangThai") or "") != "xong"]
    if not chua:
        return gt, None, None, True                 # đã tích hết

    stt = min(int(x.get("thuTu") or 0) for x in chua) - 1
    if not 0 <= stt < len(bai):
        return gt, None, (f"Bước có thứ tự {stt + 1}, ngoài khoảng 1–{len(bai)} "
                          "của giáo trình. Em chưa dám gửi."), False
    b = dict(bai[stt])
    b["_xong"] = len(steps) - len(chua)
    b["_tong"] = len(steps)
    return gt, b, None, False


# Số câu ĐẠI CA TỰ THÊM gửi kèm mỗi ngày. Bốn — bằng khoảng một phần ba số câu
# của một bài giáo trình, đủ để có mặt mà không đẩy bài chính xuống dưới.
CAU_MOI_NGAY = 4
# Bản ôn gọn gửi bốn lần trong ngày nên lấy ít hơn, và lấy ĐÚNG mấy câu đầu của
# cửa sổ buổi sáng — ôn là gặp lại thứ sáng nay đã học, không phải thứ mới.
CAU_ON_LAI = 3


def _cau_cua_toi(so_cau: int) -> tuple[list, str]:
    """(câu admin tự thêm cho hôm nay, câu báo lỗi nếu tra hỏng).

    XOAY VÒNG THEO NGÀY chứ không gửi cả sổ: sổ này chỉ có lớn lên, và một tin
    dài thêm mỗi tuần thì đến tháng sau admin thôi đọc — cùng cái bẫy đã khiến
    bản nhắc lại trong ngày phải rút gọn hôm 20/08.

    KHÔNG ghi lại "hôm qua đã ôn câu nào": cron chỉ được ĐỌC (S3), nên trí nhớ
    giữa các lần gửi không thể là một cột trong sổ. Cửa sổ trượt theo ngày trong
    năm giải đúng bài toán đó mà không cần nhớ gì — trong cùng một ngày thì năm
    tin nhắn trùng nhau (đúng ý: đó là ôn), sang ngày mới tự sang câu khác, và
    hết vòng thì quay lại từ đầu.

    Sổ rỗng thì trả về rỗng và IM — admin chưa thêm câu nào là chuyện bình
    thường, không phải chuyện phải báo. Còn tra HỎNG thì nói ra (O10): im ở đây
    nghĩa là mấy câu admin tự thêm lặng lẽ biến mất khỏi bài học và không ai hay.
    """
    loi: list = []
    o = doc_output("ngoaiNguCompany", "dsCau", {"trangThai": "đang học"}, loi)
    if loi:
        return [], f"(Chưa lấy được sổ câu đại ca tự thêm — {loi[0]})"
    cau = o.get("cau") or []
    if not cau:
        return [], ""
    dau = (now_local().timetuple().tm_yday * CAU_MOI_NGAY) % len(cau)
    return [cau[(dau + i) % len(cau)] for i in range(min(so_cau, len(cau)))], ""


def _khoi_cau_day() -> str:
    """Khối câu tự thêm, dạng ĐẦY ĐỦ — cùng hình với phần `tu` của bài giáo
    trình, để mắt đọc theo một thói quen chứ không phải học lại cách đọc."""
    cau, canh = _cau_cua_toi(CAU_MOI_NGAY)
    if canh:
        return canh
    if not cau:
        return ""
    d = ["CÂU CỦA ĐẠI CA — tự thêm trong lúc nhắn với em", ""]
    for t in cau:
        d.append(t["vi"] + (f"   ({t['khi']})" if t.get("khi") else ""))
        d.append(f"   EN  {t['en']}")
        d.append(f"       đọc: {t['enDoc']}")
        d.append(f"   中  {t['zh']}  {t['py']}")
        d.append(f"       đọc: {t['zhDoc']}")
        d.append("")
    d.append("Thêm câu mới: cứ nhắn em “học câu: <câu tiếng Việt>”.")
    return "\n".join(d).strip()


def _khoi_cau_gon() -> str:
    """Bản GỌN cho bốn lần nhắc trong ngày — mỗi câu một dòng, đủ ba thứ tiếng.

    Tra hỏng thì ở ĐÂY im, khác `_khoi_cau_day`. Không phải nuốt lỗi (O10): tin
    05:30 đã nói ra rồi, và bản này gửi bốn lần một ngày — lặp lại cùng một câu
    báo lỗi bốn lần chính là cách dạy admin bỏ qua thông báo.
    """
    cau, _canh = _cau_cua_toi(CAU_ON_LAI)
    if not cau:
        return ""
    d = ["Câu của đại ca:"]
    for t in cau:
        d.append(t["vi"])
        d.append(f"   {t['en']} ({t['enDoc']})  ·  {t['zh']} {t['py']} ({t['zhDoc']})")
    return "\n".join(d)


def section_hocsang() -> tuple[str, bool]:
    """Bài học ngoại ngữ của hôm nay, gửi TRỌN VẸN vào Telegram.

    VÌ SAO KHÔNG CHỈ GỬI CÁI LINK: admin học lúc 5h30 vừa mở cửa khách sạn,
    tay còn bận. Bắt mở trình duyệt mới đọc được bài là thêm một bậc thềm, và
    bậc thềm nào cũng là chỗ để bỏ dở — kế hoạch tiếng Anh cũ nằm ở 0/6 suốt
    ba tháng đúng vì thế. Chữ thì Telegram chở được hết; chỉ có TIẾNG là không,
    nên link để ở cuối cho lúc muốn nghe phát âm.

    Không gọi model (RP1): đọc thẳng registry/giaotrinh-ngoaingu.yaml nên tin
    này tốn 0đ mỗi sáng, và vẫn tới kể cả khi hết hạn mức Claude — ngày hết hạn
    mức đúng là ngày dễ bỏ học nhất.
    """
    gt, b, loi, het = _bai_hom_nay()
    if loi:
        # Giáo trình tra hỏng thì sổ câu riêng VẪN gửi được: nó nằm trong máy,
        # không dính Notion. Trả về mỗi câu báo lỗi là để một sự cố ở phía kia
        # cướp luôn phần bài học không hề phụ thuộc vào nó.
        khoi = _khoi_cau_day()
        return (loi + " Em chưa gửi bài giáo trình được."
                + (f"\n\n{khoi}" if khoi else "")), True
    if het:
        # Hết bài thì KHÔNG im lặng biến mất — nói rõ và chỉ việc tiếp theo.
        # Câu tự thêm vẫn gửi: sổ đó không hết bao giờ, và đây đúng là lúc nó
        # thành phần chính của tin buổi sáng thay vì phần phụ.
        khoi = _khoi_cau_day()
        return ("Đã tích xong cả " + str(len(gt["bai"])) + " bài giáo trình Anh–Trung.\n"
                "Giờ quay lại từ Bài 1, mỗi ngày ôn hai bài, và lần này đừng "
                "nhìn cột tiếng Việt. Vòng hai mới là vòng khắc vào trí nhớ.\n"
                + (gt.get("lienKet") or "")
                + (f"\n\n{khoi}" if khoi else "")), True
    if b is None:
        return "", False

    d = [f"Bài {b['ngay']}/{b['_tong']} — {b['ten']}   (đã xong {b['_xong']})",
         b.get("khi", ""),
         "Thuộc rồi thì nhắn em \u201cxong bài này\u201d, mai em gửi bài kế tiếp. "
         "Chưa thuộc thì cứ để nguyên, em gửi lại bài này.", ""]
    for t in b.get("tu") or []:
        d.append(t["vi"])
        d.append(f"   EN  {t['en']}")
        d.append(f"       đọc: {t['enDoc']}")
        d.append(f"   中  {t['zh']}  {t['py']}")
        d.append(f"       đọc: {t['zhDoc']}")
        d.append("")
    for m in b.get("mau") or []:
        d.append("MẪU LẮP GHÉP — thay từ vào chỗ ___")
        d.append(f"   {m['vi']}")
        d.append(f"   {m['en']}")
        d.append(f"   {m['zh']}")
        for x in m.get("thay") or []:
            d.append(f"     · {x}")
        d.append("")
    d.append("MÓC NHỚ")
    for x in b.get("moc") or []:
        d.append(f"   · {x}")
    d.append("")
    d.append(f"Dùng ngay: {b.get('dungNgay', '')}")
    khoi = _khoi_cau_day()
    if khoi:
        d.append("")
        d.append(khoi)
    if gt.get("lienKet"):
        d.append("")
        d.append(f"Bấm để NGHE đọc từng câu: {gt['lienKet']}")
    return "\n".join(d).strip(), True


def section_hocnhac() -> tuple[str, bool]:
    """Nhắc lại bài trong ngày — bản GỌN, gửi bốn lần sau buổi sáng.

    VÌ SAO CÓ: admin nói cả ngày còn nhắn nhiều việc khác nên bài buổi sáng bị
    TRÔI lên trên, lúc rảnh muốn ôn thì phải cuộn đi tìm.

    VÌ SAO GỌN CHỨ KHÔNG GỬI LẠI Y HỆT: bản đầy đủ dài 2.500 ký tự. Đẩy nguyên
    nó năm lần một ngày thì Telegram thành một bức tường và mọi tin khác bị
    chôn — đúng cái admin đang than, chỉ đảo chiều. Bản này bỏ phần GIẢNG (mẫu
    lắp ghép, móc nhớ) và giữ phần ÔN: đủ ba thứ tiếng cộng phiên âm, liếc một
    cái là nhớ lại được.

    Hợp với chính luật trong giáo trình: nhớ lại mạnh hơn đọc lại. Lần thứ hai
    trong ngày không cần dạy lại, chỉ cần cho admin cái để tự kiểm.
    """
    gt, b, loi, het = _bai_hom_nay()
    if loi:
        khoi = _khoi_cau_gon()      # cùng lý lẽ với section_hocsang
        return (loi + " Em chưa nhắc bài giáo trình được."
                + (f"\n\n{khoi}" if khoi else "")), True
    if b is None:
        # Hết bài, hoặc chưa tra được — mục sáng đã nói rồi, ở đây im cho gọn.
        # Nhưng sổ câu tự thêm thì KHÔNG hết bao giờ: hết giáo trình mà tắt
        # luôn bốn lần nhắc là bỏ đi đúng phần admin tự chọn để học.
        khoi = _khoi_cau_gon()
        return (khoi, True) if khoi else ("", False)
    d = [f"Ôn lại — Bài {b['ngay']}: {b['ten']}", ""]
    for t in b.get("tu") or []:
        d.append(t["vi"])
        d.append(f"   {t['en']} ({t['enDoc']})  ·  {t['zh']} {t['py']} ({t['zhDoc']})")
    khoi = _khoi_cau_gon()
    if khoi:
        d.append("")
        d.append(khoi)
    if gt.get("lienKet"):
        d.append("")
        d.append(f"Nghe đọc: {gt['lienKet']}")
    return "\n".join(d), True


SECTIONS = {"agenda": section_agenda, "tienbac": section_tienbac,
            "hocsang": section_hocsang, "hocnhac": section_hocnhac,
            "quota": section_quota,
            "activity": section_activity, "approvals": section_approvals,
            "permissions": section_permissions, "plan": section_plan}


# ───────────────────────── chạy ─────────────────────────

def nhac_den_han(conn) -> list:
    """Lời nhắc tới giờ. Trả danh sách câu cần nhắn.

    Trí nhớ "đã nhắc rồi" nằm ở sổ của SCHEDULER, không nằm trong nhacCompany —
    vì cron chỉ được ĐỌC (S3) nên nó không ghi được vào sổ của company. Cùng
    cách ngoaiNguCompany giải bài toán này hồi 24/08.

    Không có phần nhớ đó thì mỗi phút một tiếng chuông cho tới khi lời nhắc quá
    hạn — đúng thứ admin vừa bảo là ĐỪNG làm ("chỉ thông báo một lần thôi").
    """
    conn.execute("""CREATE TABLE IF NOT EXISTS nhacDaGui (
                      nhacId TEXT PRIMARY KEY, guiLuc TEXT NOT NULL)""")
    kq = call_company("nhacCompany", "dsNhac",
                      {"gioiHan": 50, "gomDenHan": True})
    if kq.get("status") != "ok":
        return []
    bay_gio = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tin = []
    for n in (kq.get("output") or {}).get("cacNhac") or []:
        # dsNhac chỉ trả lời nhắc CHƯA tới giờ, nên "đến hạn" ở đây là những
        # cái vừa rơi qua mốc giữa hai lần chạy. Lấy theo `conBaoLau` thì mong
        # manh; hỏi thẳng giờ VN rồi so là chắc hơn.
        try:
            moc = datetime.strptime(n["khiNao"][:16], "%Y-%m-%dT%H:%M").replace(
                tzinfo=timezone(timedelta(hours=7)))
        except (ValueError, KeyError):
            continue
        if moc > datetime.now(timezone.utc):
            continue
        if conn.execute("SELECT 1 FROM nhacDaGui WHERE nhacId=?",
                        (n["nhacId"],)).fetchone():
            continue
        conn.execute("INSERT INTO nhacDaGui (nhacId, guiLuc) VALUES (?,?)",
                     (n["nhacId"], bay_gio))
        conn.commit()
        tin.append(f"⏰ {n['khiNao']} — {n['noiDung']}")
    return tin


def chay_hen_den_han() -> list:
    """Mở những phiếu HẸN admin đã ký và đã tới giờ. Trả danh sách tin cần gửi.

    ĐÂY LÀ CHỖ DUY NHẤT cron được phép làm việc `write`, và nó không phải một
    quyền: mỗi lần chạy là mở đúng một chữ ký admin đã đặt sẵn cho đúng một nội
    dung. Dispatcher vẫn kiểm hash (G4), vẫn dùng một lần, vẫn từ chối nếu chưa
    tới giờ hoặc quá cửa sổ. Chi tiết vì sao mở khe này: PRINCIPLES.md, S3.

    LUÔN BÁO LẠI, kể cả khi chạy trót lọt. Một việc tự xảy ra lúc admin ngủ mà
    không để lại tiếng nào thì lần sau admin sẽ không dám hẹn nữa — và tệ hơn,
    họ không có cách biết nó đã chạy hay chưa.
    """
    tin = []
    for r in approvals.hen_den_han():
        try:
            inp = json.loads(r["inputJson"])
        except ValueError:
            tin.append(f"Hẹn {r['approvalId']} hỏng: nội dung không đọc được.")
            continue
        kq = call_company(r["companyId"], r["capability"], inp,
                          approval_id=r["approvalId"])
        ten = f"{r['companyId']}.{r['capability']}"
        if kq.get("status") == "ok":
            tin.append(f"Tới giờ hẹn, em đã chạy {ten}. "
                       + str(kq.get("summary") or "")[:300])
        else:
            # Hỏng thì nói TO. Việc hẹn hỏng mà im lặng là kiểu tệ nhất: admin
            # tưởng đã xong, và chỉ phát hiện khi đi tìm kết quả không có.
            tin.append(f"Tới giờ hẹn nhưng {ten} KHÔNG chạy được "
                       f"({kq.get('status')}): {str(kq.get('summary') or '')[:200]}")
    return tin


def call_company(company_id: str, capability: str, inp: dict,
                 approval_id: str = None) -> dict:
    """S1/S3 — đi qua dispatcher như mọi lời gọi khác, nhưng khai issuedBy là
    scheduledTrigger. Dispatcher tự chặn nếu năng lực đó là write."""
    trace = "trc_cron_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "ops", "dispatch.py"), "call",
         "--company", company_id, "--capability", capability,
         "--input", json.dumps(inp, ensure_ascii=False),
         "--trace", trace, "--issued-by", "scheduledTrigger"]
        + (["--approval-id", approval_id] if approval_id else []),
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
            # Trả 'failed' chứ không phải 'ok': cmd_run cần phân biệt được "lịch
            # có tin cho admin" với "lịch hỏng", để không nhắn lại cùng một sự
            # cố mỗi 15 phút. Trước đây cả hai đều là 'ok' nên trong sổ nhìn
            # giống hệt nhau.
            return (f"— {sched['displayName']} —\n\n" + "\n\n".join(parts)), "failed"
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

    # Hẹn giờ KHÔNG chạy ở đây — nó có timer riêng nhịp 1 phút (`scheduler.py
    # hen`). Để chung thì cái hẹn 3h sáng kêu lúc 3h14, mà đó đúng là thứ cần
    # sửa. Vẫn gọi một lần ở đây làm lưới đỡ: timer 1 phút chết thì ít nhất
    # mỗi 15 phút còn có người mở phiếu hẹn ra xem.
    for loi_nhan in nhac_den_han(conn) + chay_hen_den_han():
        res = telegram.send_message(admin, loi_nhan)
        ran += 1
        print(("gửi được: " if res.get("ok") else "gửi HỎNG: ") + loi_nhan[:80])

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

        # S7 mở rộng — SỰ CỐ KÉO DÀI CHỈ NHẮN MỘT LẦN.
        #
        # calendarWatch chạy mỗi 15 phút. Đo 2026-08-16: đêm 15/08 mạng không
        # bắt tay được với Notion suốt 6 tiếng, lịch dựng ra 21 tin lỗi giống
        # hệt nhau. Đêm đó admin không nhận cái nào vì Telegram cũng đứt cùng
        # lúc — nhưng nếu chỉ Notion hỏng thì đó là 21 lần đánh thức lúc nửa
        # đêm cho MỘT sự cố. Tin thứ hai trở đi không thêm thông tin gì, chỉ
        # dạy admin bỏ qua thông báo của hệ.
        #
        # Nên: lỗi lần đầu thì nhắn, lỗi lặp lại thì im và vẫn ghi sổ, khỏi rồi
        # thì nhắn một câu báo đã chạy lại được. Im lặng ở giữa KHÔNG phải nuốt
        # lỗi (O10): mọi lần đều nằm trong scheduleRun, `backoffice report` vẫn
        # đếm đủ.
        truoc = trang_thai_truoc(conn, sid)
        im = status == "failed" and truoc == "failed"
        if status == "ok" and truoc == "failed":
            n = so_lan_hong_lien_tiep(conn, sid)
            text = (f"— {sched['displayName']} —\n\nĐã chạy lại được"
                    + (f" (hỏng {n} lần liên tiếp trước đó)." if n else ".")
                    + ("\n\n" + text.split("\n\n", 1)[1] if "\n\n" in text else ""))

        sent = 0
        if text and not im:
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


def cmd_hen(args):
    """Chỉ lo HẸN GIỜ: lời nhắc tới giờ, và phiếu hẹn admin đã ký.

    Tách khỏi `run` để chạy được ở nhịp DÀY hơn (1 phút thay vì 15). Cả hai
    việc ở đây chỉ đọc sqlite trên máy — không hỏi Notion, không gọi model —
    nên chạy 1.440 lần mỗi ngày vẫn gần như 0đ. Nhập chung vào `run` thì hoặc
    lịch định kỳ bị chạy dày lên vô ích, hoặc cái hẹn 3h sáng kêu lúc 3h14.
    """
    admin = os.environ.get("COMPANYSPEC_ADMIN_CHAT_ID", "")
    if not admin:
        print("Thiếu COMPANYSPEC_ADMIN_CHAT_ID (F6).", file=sys.stderr)
        return 1
    conn = store()
    gui = 0
    for loi_nhan in nhac_den_han(conn) + chay_hen_den_han():
        res = telegram.send_message(admin, loi_nhan)
        gui += 1
        print(("gửi được: " if res.get("ok") else "gửi HỎNG: ") + loi_nhan[:80])
    conn.close()
    if not gui:
        print("không có hẹn nào tới giờ")
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
    sub.add_parser("hen").set_defaults(fn=cmd_hen)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
