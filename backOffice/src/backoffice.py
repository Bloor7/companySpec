#!/usr/bin/env python3
"""backOffice — bộ phận theo dõi và báo cáo.

Hạ tầng, KHÔNG phải company (chốt Q7): nó không cần LLM, và bắt nó đi qua
dispatcher chỉ tổ vòng vo.

T3 — chỉ ĐỌC dữ liệu của company, ghi vào kho của chính mình.

    python3 backOffice/src/backoffice.py usage      # hạn mức đã dùng
    python3 backOffice/src/backoffice.py report     # hoạt động 7 ngày
    python3 backOffice/src/backoffice.py whitelist  # quyền đang có
    python3 backOffice/src/backoffice.py check      # L7 — còn chạy được không

Thêm --json để máy đọc; mặc định in cho người đọc.
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "ops"))
import approvals  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "lib"))
import db  # noqa: E402

STORE = os.path.join(ROOT, "backOffice", "store.sqlite")
TZ = timezone(timedelta(hours=7))


def store():
    return db.connect(STORE)


def utc_ago(**kw) -> str:
    return (datetime.now(timezone.utc) - timedelta(**kw)).strftime("%Y-%m-%dT%H:%M:%SZ")


def week_start() -> str:
    now = datetime.now(timezone.utc)
    return (now - timedelta(days=now.weekday())).strftime("%Y-%m-%dT00:00:00Z")


def spent_since(conn, since: str) -> dict:
    """Hạn mức đã dùng = CEO + company tự chạy LLM + ca thử. Cùng một gói Pro.

    Cộng cả ba vì chúng là những tiến trình claude riêng biệt, cùng trừ vào một
    gói. Bỏ sót vế nào là báo cáo thiếu.

    CA THỬ ĐẾM RIÊNG, nhưng vẫn nằm trong `total`. Nó là hạn mức thật đã tiêu,
    che đi thì con số trấn an một cách sai sự thật (đo 2026-08-18: sổ ghi $0,95
    trong khi ca thử tiêu $2,64 — bản trước không ghi gì). Nhưng trộn chung với
    CEO thì cũng sai theo chiều kia: một đêm chạy eval sẽ trông y hệt một đêm
    admin dùng nhiều, và hai thứ đó cần xử lý khác nhau. Nên: cộng vào tổng,
    hiện thành một dòng riêng.
    """
    ceo = conn.execute(
        "SELECT COALESCE(SUM(costUsd),0) FROM ceoRunLog "
        "WHERE createdAt >= ? AND traceId NOT LIKE 'evl_%'",
        (since,)).fetchone()[0]
    eval_ = conn.execute(
        "SELECT COALESCE(SUM(costUsd),0) FROM ceoRunLog "
        "WHERE createdAt >= ? AND traceId LIKE 'evl_%'",
        (since,)).fetchone()[0]
    comp = conn.execute(
        "SELECT COALESCE(SUM(costUsd),0) FROM taskLog WHERE startedAt >= ?",
        (since,)).fetchone()[0]
    by_company = {r["companyId"]: round(r["t"], 3) for r in conn.execute(
        "SELECT companyId, SUM(costUsd) t FROM taskLog "
        "WHERE startedAt >= ? AND costUsd > 0 GROUP BY 1", (since,))}
    return {"ceo": round(ceo, 3), "company": round(comp, 3),
            "caThu": round(eval_, 3),
            "total": round(ceo + comp + eval_, 3), "byCompany": by_company}


# ───────────────────────── L7 — cầu dao hạn mức ─────────────────────────

def quota_hits(gio: int = 168) -> list:
    """Những lần Anthropic THẬT SỰ nói hết hạn mức, mới nhất trước.

    Đây là nguồn sự thật duy nhất về quota kể từ 2026-08-16 — xem
    lib/quotaSignal.py. Bảng có thể chưa tồn tại (chưa lần nào chạm trần), và
    đó là trạng thái bình thường chứ không phải lỗi.
    """
    conn = store()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT loai, resetLuc, createdAt FROM quotaHit WHERE createdAt >= ? "
            "ORDER BY hitId DESC LIMIT 20", (utc_ago(hours=gio),))]
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    return rows


def tien_that_thang() -> dict:
    """TIỀN THẬT ra ngoài trong tháng dương này (L8).

    Tách hẳn khỏi chi phí gói Pro. Hai loại tiền khác nhau về bản chất: hạn mức
    Pro dùng hết thì thôi và tháng sau lại có; còn đây trừ vào thẻ của admin và
    có hoá đơn. Gộp một chỗ thì đến lúc đối chiếu hoá đơn không tách ra được.
    """
    dau_thang = datetime.now(timezone.utc).strftime("%Y-%m-01T00:00:00Z")
    cfg = approvals.config().get("chiTieuNgoai", {})
    conn = store()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT companyId, nhaCungCap, SUM(soTienVnd) t, COUNT(*) n "
            "FROM chiTieuNgoai WHERE createdAt >= ? GROUP BY companyId, nhaCungCap "
            "ORDER BY t DESC", (dau_thang,))]
    except sqlite3.OperationalError:
        rows = []          # chưa company nào tiêu tiền thật — trạng thái bình thường
    conn.close()
    tong = sum(r["t"] for r in rows)
    return {"tong": tong, "tran": float(cfg.get("tranThangVnd", 0) or 0),
            "canhBaoTaiPhanTram": cfg.get("canhBaoTaiPhanTram", 70), "theo": rows}


def chi_phi_gan_day() -> dict:
    """Chi phí đã tiêu, KHÔNG kèm phán xét.

    Trước đây hàm này trả về ok/warn/stop và dispatcher dùng nó để khoá việc
    ghi. Bỏ ngày 2026-08-16 (admin quyết): con số là hệ tự cộng từ bảng giá
    token, không phải hạn mức thật — `claude -p` không trả về hạn mức còn lại
    và CLI không có lệnh `usage`. Ngưỡng đoán thì hoặc chặn oan, hoặc không
    chặn đúng thứ cần chặn.

    Con số vẫn hữu ích để BIẾT đang tiêu vào đâu, nên giữ lại và báo cáo.
    Việc nói "hết hạn mức" thì để Anthropic nói — xem quota_hits().
    """
    conn = store()
    w5 = spent_since(conn, utc_ago(hours=5))
    wk = spent_since(conn, week_start())
    conn.close()
    return {
        "window5h": w5,
        "week": wk,
        "hits": quota_hits(),
    }


def cmd_usage(args):
    q = chi_phi_gan_day()
    if args.json:
        return q
    lines = []
    for label, key in (("5 tiếng qua", "window5h"), ("Tuần này", "week")):
        d = q[key]
        phan = f"CEO ${d['ceo']:.2f} · company ${d['company']:.2f}"
        # Chỉ hiện khi có, để dòng báo cáo hằng ngày không dài thêm vì một số 0.
        if d.get("caThu"):
            phan += f" · ca thử ${d['caThu']:.2f}"
        lines.append(f"{label:<12} ${d['total']:.2f}  ({phan})")
        if d["byCompany"]:
            top = sorted(d["byCompany"].items(), key=lambda kv: -kv[1])[:3]
            lines.append("             " + ", ".join(f"{k} {v}" for k, v in top))
    lines.append("")
    if q["hits"]:
        h = q["hits"][0]
        lines.append(f"CHẠM TRẦN gần nhất: hạn mức {h['loai']} lúc {h['createdAt'][:16]}"
                     + (f", mở lại {h['resetLuc']}" if h["resetLuc"] else ""))
        lines.append(f"({len(q['hits'])} lần trong 7 ngày qua)")
    else:
        lines.append("Chưa lần nào Anthropic báo hết hạn mức trong 7 ngày qua.")
    lines.append("")
    lines.append("Đây là CHI PHÍ ĐÃ TIÊU, không phải hạn mức còn lại — Anthropic")
    lines.append("không công bố số đó. Hết hạn mức thì hệ báo ngay lúc gặp.")

    # TIỀN THẬT — để riêng, dưới một đường kẻ, vì nó khác loại với phần trên.
    t = tien_that_thang()
    lines.append("")
    lines.append("─── TIỀN THẬT ra ngoài, tháng này ───")
    if not t["theo"]:
        lines.append(f"  0đ / trần {t['tran']:,.0f}đ — chưa company nào gọi API tính tiền.")
    else:
        pct = (t["tong"] / t["tran"] * 100) if t["tran"] else 0
        canh = "  ⚠ sắp chạm trần" if pct >= t["canhBaoTaiPhanTram"] else ""
        lines.append(f"  {t['tong']:,.0f}đ / trần {t['tran']:,.0f}đ ({pct:.0f}%){canh}")
        for r in t["theo"]:
            lines.append(f"    {r['companyId']} · {r['nhaCungCap']}: "
                         f"{r['t']:,.0f}đ ({r['n']} lần)")
    return "\n".join(lines)


# ───────────────────────── báo cáo hoạt động ─────────────────────────

def cmd_report(args):
    since = utc_ago(days=args.days)
    conn = store()

    # LỜI GỌI CỦA BỘ ĐO ĐẾM RIÊNG, cùng lý lẽ với `evl_` ở ceoRunLog bên trên.
    #
    # Vì sao cần: bộ regression chạy khô cả 82 năng lực, mỗi lần chạy thêm vài
    # trăm dòng mang traceId `reg_`. Trộn chung thì báo cáo ngày in
    # "nhacCompany 1482 lời gọi" trong khi admin không hề đặt cái nhắc nào —
    # và một báo cáo nói sai như thế thì admin học cách bỏ qua nó, đúng thứ
    # dòng "lỗi hạ tầng lặp lại nhắn mỗi lần" trong bảng bẫy cảnh báo.
    #
    # KHÔNG che đi, chỉ tách ra: chúng vẫn là lời gọi đã xảy ra thật, và một
    # bộ đo tự xoá dấu vết của mình là một bộ đo không kiểm được.
    TEST_TRACES = "(traceId LIKE 'reg_%' OR traceId LIKE 'evl_%')"
    rows = list(conn.execute(
        "SELECT companyId, status, COUNT(*) n, ROUND(SUM(costUsd),3) c "
        f"FROM taskLog WHERE startedAt >= ? AND NOT {TEST_TRACES} "
        "GROUP BY 1,2 ORDER BY 1,2", (since,)))
    testCalls = conn.execute(
        f"SELECT COUNT(*) FROM taskLog WHERE startedAt >= ? AND {TEST_TRACES}",
        (since,)).fetchone()[0]
    ceo = conn.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(isError),0) e, ROUND(SUM(costUsd),3) c "
        "FROM ceoRunLog WHERE createdAt >= ?", (since,)).fetchone()
    # Lý do CEO chết. Đếm số lần chết mà không nói vì sao thì admin vẫn phải đi
    # mò log — mà log thì trước đây không có gì để mò. Gom theo lý do: ba lần
    # chết cùng một lý do là một sự cố, không phải ba.
    try:
        ceo_loi = list(conn.execute(
            "SELECT substr(loi,1,90) l, COUNT(*) n, MAX(createdAt) gan_nhat "
            "FROM ceoRunLog WHERE createdAt >= ? AND isError=1 AND loi IS NOT NULL "
            "GROUP BY 1 ORDER BY 2 DESC LIMIT 5", (since,)))
    except sqlite3.OperationalError:
        ceo_loi = []   # sổ cũ chưa có cột `loi`
    effects = list(conn.execute(
        "SELECT type, COUNT(*) n FROM sideEffectLog WHERE createdAt >= ? "
        "GROUP BY 1 ORDER BY 2 DESC", (since,)))
    approv = list(conn.execute(
        "SELECT status, COUNT(*) n FROM approvalRequest WHERE createdAt >= ? "
        "GROUP BY 1", (since,)))
    conn.close()

    data = {
        "days": args.days,
        "ceo": {"runs": ceo["n"], "errors": ceo["e"], "cost": ceo["c"] or 0,
                "errorReasons": [dict(r) for r in ceo_loi]},
        "tasks": [dict(r) for r in rows],
        "testCalls": testCalls,
        "sideEffects": {r["type"]: r["n"] for r in effects},
        "approvals": {r["status"]: r["n"] for r in approv},
    }
    if args.json:
        return data

    out = [f"── {args.days} ngày qua ──", ""]
    by_co: dict = {}
    for r in rows:
        by_co.setdefault(r["companyId"], []).append((r["status"], r["n"]))
    for co, sts in sorted(by_co.items()):
        total = sum(n for _, n in sts)
        detail = ", ".join(f"{s} {n}" for s, n in sts if s != "ok")
        out.append(f"  {co:<16}{total:>3} lời gọi" + (f"  ({detail})" if detail else ""))
    if not by_co:
        out.append("  (không có lời gọi thật nào)")
    if testCalls:
        # Nói ra chứ không giấu: một con số bị bỏ khỏi bảng mà không ai nhắc
        # tới là một con số sẽ bị quên mất là nó tồn tại.
        out.append(f"  + {testCalls} lời gọi của bộ đo (reg_/evl_), không tính ở trên")
    out.append("")
    out.append(f"  CEO: {ceo['n']} lượt · {ceo['e']} lỗi")
    for r in ceo_loi:
        out.append(f"    ✖ {r['n']}× {r['l']}  (gần nhất {r['gan_nhat'][:16]})")
    if ceo["e"] and not ceo_loi:
        out.append("    (lỗi ghi trước 14/08 nên không có lý do kèm theo)")
    if effects:
        out.append("")
        out.append("  Đã đổi ngoài thế giới thực:")
        for r in effects:
            out.append(f"    {r['type']:<26}{r['n']}")
    if approv:
        out.append("")
        out.append("  Yêu cầu duyệt: " + ", ".join(f"{r['status']} {r['n']}" for r in approv))
    return "\n".join(out)


# ───────────────────────── quyền ─────────────────────────

def cmd_whitelist(args):
    conn = store()
    rules = []
    for r in approvals.active_rules():
        used = conn.execute(
            "SELECT COUNT(*) FROM taskLog WHERE companyId=? AND capability=? "
            "AND status='ok' AND startedAt >= ?",
            (r["companyId"], r["capability"], r["createdAt"])).fetchone()[0]
        days_left = (approvals.parse(r["expiresAt"]) - approvals.now_dt()).days
        rules.append({**r, "usedSinceGranted": used, "daysLeft": days_left})
    conn.close()

    if args.json:
        return {"rules": rules}
    if not rules:
        return "Chưa cấp quyền tự chạy nào."

    out = ["── Quyền tự chạy ──", ""]
    for r in rules:
        scope = ", ".join(str(v) for v in r["scope"].values() if v) or "(toàn bộ)"
        warn = ""
        if r["daysLeft"] <= 14:
            warn = f"  ⚠ còn {r['daysLeft']} ngày"
        if r["usedSinceGranted"] == 0:
            warn += "  · chưa dùng lần nào"
        out.append(f"  {r['capability']:<16}{scope:<16}"
                   f"{r['usedSinceGranted']:>3} lần{warn}")
        out.append(f"    tối đa {r['maxPerDay']}/ngày · hết hạn {r['expiresAt'][:10]}")
    return "\n".join(out)


def cmd_trace(args):
    """Phát lại một phiên: admin nói gì, CEO gọi gì, đổi gì ngoài đời.

    NGUYÊN THỂ #11 — HARNESS.md xếp "phát lại quỹ đạo phiên" vào phần còn
    thiếu. Nó thiếu theo kiểu âm ỉ: khi CEO cư xử lạ, cách gỡ duy nhất từ trước
    tới nay là đọc chéo ba sổ ở ba chỗ (`ceo/store.sqlite` giữ tin nhắn,
    `backOffice/store.sqlite` giữ lời gọi và chi phí) rồi tự ghép theo giờ
    trong đầu. Ghép tay thì lần nào cũng bỏ sót đúng cái mình đang tìm.

    Không tốn gì và không đụng gì: chỉ đọc, gộp bốn nguồn theo trục thời gian.
    """
    ceo = db.connect(os.path.join(ROOT, "ceo", "store.sqlite"))
    conn = store()

    if not args.phien:
        print("Phiên gần đây (lấy id ở cột đầu rồi chạy lại kèm id đó):\n")
        for r in ceo.execute(
                "SELECT threadId, sessionId, turns, openedAt, lastAt, closed "
                "FROM thread ORDER BY threadId DESC LIMIT ?", (args.so,)):
            print(f"  #{r['threadId']:<4} {r['sessionId'][:8]}  {r['turns']:>2} lượt  "
                  f"{r['openedAt'][:16].replace('T',' ')}  "
                  f"{'đã đóng' if r['closed'] else 'đang mở'}")
        return

    row = ceo.execute(
        "SELECT * FROM thread WHERE threadId=? OR sessionId LIKE ?",
        (args.phien if args.phien.isdigit() else -1, args.phien + "%")).fetchone()
    if row is None:
        # O10 — gõ nhầm id thì nói ra. In một quỹ đạo rỗng trông y hệt một phiên
        # thật sự không làm gì, và người đi gỡ lỗi sẽ tin vào cái rỗng đó.
        print(f"Không có phiên nào khớp {args.phien!r}. Chạy không kèm id để xem danh sách.")
        return
    trace_id = "trc_" + row["sessionId"].replace("-", "")[:20]

    print(f"── Phiên #{row['threadId']} · {row['sessionId']}")
    print(f"   {row['openedAt'][:19].replace('T',' ')} → {row['lastAt'][:19].replace('T',' ')} "
          f"· {row['turns']} lượt · {'đã đóng' if row['closed'] else 'đang mở'}")

    sach = list(ceo.execute(
        "SELECT soTay, cauAdmin, createdAt FROM playbookLog WHERE threadId=? ORDER BY id",
        (row["threadId"],)))
    moc = []
    for r in ceo.execute("SELECT vaiTro, noiDung, createdAt FROM message "
                         "WHERE threadId=? ORDER BY id", (row["threadId"],)):
        moc.append((r["createdAt"], "admin" if r["vaiTro"] == "admin" else "CEO",
                    r["noiDung"][:220]))
    for r in conn.execute(
            "SELECT companyId, capability, riskTier, status, summary, costUsd, startedAt "
            "FROM taskLog WHERE traceId=? ORDER BY startedAt", (trace_id,)):
        moc.append((r["startedAt"], f"gọi[{r['status']}]",
                    f"{r['companyId']}.{r['capability']} ({r['riskTier']}) "
                    f"{(r['summary'] or '')[:120]}"))
    for r in conn.execute("SELECT type, target, createdAt FROM sideEffectLog "
                          "WHERE traceId=? ORDER BY createdAt", (trace_id,)):
        moc.append((r["createdAt"], "ĐỔI THẬT", f"{r['type']} {r['target'] or ''}"))

    if sach:
        print("\n   Sổ tay router đã nạp:")
        for r in sach:
            print(f"     {r['soTay'] or '(không nạp gì)':38} {r['cauAdmin'][:44]!r}")

    print("\n   Quỹ đạo:")
    for khi, vai, noi in sorted(moc, key=lambda x: x[0] or ""):
        print(f"     {(khi or '')[11:19]}  {vai:<14} {noi}")

    chay = list(conn.execute(
        "SELECT numTurns, durationMs, costUsd, isError, loi FROM ceoRunLog "
        "WHERE traceId=? ORDER BY runId", (trace_id,)))
    if chay:
        tien = sum(r["costUsd"] or 0 for r in chay)
        hong = [r for r in chay if r["isError"]]
        print(f"\n   {len(chay)} lượt CEO · ${tien:.4f} · {len(hong)} lượt hỏng")
        for r in hong:
            print(f"     HỎNG: {(r['loi'] or '')[:160]}")
    ceo.close()
    conn.close()


def cmd_check(args):
    return chi_phi_gan_day()


def main() -> int:
    ap = argparse.ArgumentParser(description="backOffice — theo dõi và báo cáo")
    ap.add_argument("--json", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("usage").set_defaults(fn=cmd_usage)
    r = sub.add_parser("report")
    r.add_argument("--days", type=int, default=7)
    r.set_defaults(fn=cmd_report)
    sub.add_parser("whitelist").set_defaults(fn=cmd_whitelist)
    t = sub.add_parser("trace", help="phát lại một phiên: nói gì, gọi gì, đổi gì")
    t.add_argument("phien", nargs="?", help="threadId hoặc đầu sessionId; "
                                            "bỏ trống thì liệt kê phiên gần đây")
    t.add_argument("--so", type=int, default=15)
    t.set_defaults(fn=cmd_trace)
    sub.add_parser("check").set_defaults(fn=cmd_check)

    args = ap.parse_args()
    if not hasattr(args, "days"):
        args.days = 7
    result = args.fn(args)
    if isinstance(result, str):
        print(result)
    elif result is None:
        pass          # lệnh tự in lấy (trace) — đừng phun thêm một chữ "null"
    else:
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
