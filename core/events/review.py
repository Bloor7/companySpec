#!/usr/bin/env python3
"""core.events.review — bản soát tuần (§21), và đề xuất tự cải thiện (§34).

    Projects · Tasks · Failures · Costs · Technical debt
    Blocked missions · New opportunities · Potential improvements

═══════════════════════════════════════════════════════════════════════
VÌ SAO CẦN, VÀ VÌ SAO NÓ KHÁC BÁO CÁO NGÀY
═══════════════════════════════════════════════════════════════════════

Báo cáo ngày trả lời "hôm qua có gì". Bản tuần trả lời câu khác hẳn:
**"có thứ gì đang hỏng dần mà từng ngày nhìn không thấy không?"**

Hai loại hỏng chỉ lộ ra ở thang tuần:
  · một năng lực trượt 30% — mỗi ngày một lần, nhìn qua thì như tai nạn lẻ
  · một mission đứng bánh — không có ngày nào nó "hỏng", nó chỉ không nhúc nhích

Cả hai đều IM LẶNG. Và im lặng là thứ đã để hệ chết 61 giờ trong khi mọi thứ
báo xanh, vì không có gì báo cả.

═══════════════════════════════════════════════════════════════════════
ĐỀ XUẤT LÀ ĐỀ XUẤT, KHÔNG PHẢI VIỆC ĐÃ LÀM
═══════════════════════════════════════════════════════════════════════

§34 muốn Travis tự thấy điểm yếu rồi đề nghị cải thiện. Phần "đề nghị" dừng ở
CHỮ — không Task nào được sinh ra từ đây, không quyền nào được cấp.

Một hệ tự phát hiện vấn đề rồi tự sửa mà không ai nhìn là cách một con cron
lúc 3 giờ sáng đổi thứ không ai yêu cầu đổi.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BACKOFFICE = os.path.join(ROOT, "backOffice", "store.sqlite")

#: Nhãn của lời gọi do BỘ ĐO sinh ra — không phải việc thật của admin.
#:
#: ⚠ LẤY TỪ `core.audit`, KHÔNG gõ lại. Bản cũ chép tay và thiếu `drl_`, nên
#: suốt từ lúc bộ diễn tập ra đời, bản soát tuần (§21) và đề xuất tự cải
#: thiện (§34) vẫn đếm bốn lần hỏng CỐ Ý của bài `hong` như sự cố thật —
#: chúng góp vào `FAILURE_RATE_THRESHOLD` và có thể đẻ ra một đề xuất về
#: chính bộ đo.
#:
#: Đây là bản thứ BA của cùng một danh sách, và là bản duy nhất không ai
#: canh. `core/events/scheduler.py` đã làm đúng từ đầu (import về).
from ..audit import TEST_TRACE_PREFIXES  # noqa: E402

#: Trượt quá tỉ lệ này trong tuần thì nêu tên.
FAILURE_RATE_THRESHOLD = 0.2

#: Dưới ngần này lời gọi thì tỉ lệ không nói lên gì — 1/2 là 50% nhưng nó chỉ
#: có nghĩa là "chạy hai lần". Đừng báo động vì một mẫu quá nhỏ.
MIN_CALLS_FOR_RATE = 5


def _testTraceFilter(column: str = "traceId") -> str:
    return " AND ".join(f"{column} NOT LIKE '{prefix}%'"
                        for prefix in TEST_TRACE_PREFIXES)


def collect(since: Optional[str] = None,
            storePath: str = BACKOFFICE) -> dict:
    """Gom số liệu THẬT của tuần. Chỉ đọc, không đổi gì."""
    since = since or (datetime.now(timezone.utc) - timedelta(days=7)
                      ).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = sqlite3.connect(storePath)
    conn.row_factory = sqlite3.Row
    notTest = _testTraceFilter()

    try:
        # sql-an-toan: chỉ ghép `notTest`, dựng từ hằng TEST_TRACE_PREFIXES
        # viết cứng trong file này. Mọi GIÁ TRỊ vẫn đi qua tham số `?`.
        byCapability = [dict(r) for r in conn.execute(
            f"SELECT companyId, capability, COUNT(*) total, "
            f"SUM(CASE WHEN status IN ('failed','budgetExceeded') THEN 1 ELSE 0 END) failed, "
            f"SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) completed "
            f"FROM taskLog WHERE startedAt >= ? AND {notTest} "
            f"GROUP BY companyId, capability ORDER BY total DESC", (since,))]

        # sql-an-toan: chỉ ghép `notTest` dựng từ hằng viết cứng; giá trị qua `?`
        approvals = [dict(r) for r in conn.execute(
            f"SELECT companyId, capability, COUNT(*) n FROM taskLog "
            f"WHERE startedAt >= ? AND status='needsApproval' AND {notTest} "
            f"GROUP BY companyId, capability ORDER BY n DESC LIMIT 5", (since,))]

        ceoErrors = [dict(r) for r in conn.execute(
            "SELECT substr(loi,1,90) reason, COUNT(*) n FROM ceoRunLog "
            "WHERE createdAt >= ? AND isError=1 AND loi IS NOT NULL "
            "GROUP BY 1 ORDER BY 2 DESC LIMIT 5", (since,))]

        cost = conn.execute(
            "SELECT COALESCE(SUM(costUsd),0) FROM ceoRunLog "
            "WHERE createdAt >= ? AND traceId NOT LIKE 'evl_%'",
            (since,)).fetchone()[0]

        # Lời gọi KHÔNG có quyết định policy — nếu có thì đó là đường vào hệ
        # không qua cửa, và không gì đáng báo hơn.
        #
        # ⚠ CHỈ ĐẾM TỪ LÚC CỘT ẤY TỒN TẠI. Dòng cũ hơn ngày thêm cột
        # `policyDecision` (2026-09-19) vốn KHÔNG THỂ có giá trị — đếm chúng là
        # báo động về quá khứ, và một cảnh báo đúng luật nhưng sai chỗ thì cũng
        # dạy người ta bỏ qua cảnh báo, hệt như 21 tin lúc nửa đêm.
        #
        # Mốc suy TỪ DỮ LIỆU, không viết cứng ngày: dòng đầu tiên CÓ
        # policyDecision là lúc cột bắt đầu có nghĩa. Viết cứng thì sang năm
        # nó vẫn đúng một cách tình cờ, rồi có ngày sai mà không ai biết.
        floor = conn.execute(
            "SELECT MIN(startedAt) FROM taskLog WHERE policyDecision IS NOT NULL"
        ).fetchone()[0]
        if floor:
            # sql-an-toan: chỉ ghép `notTest` dựng từ hằng viết cứng; giá trị qua `?`
            unexplained = conn.execute(
                f"SELECT COUNT(*) FROM taskLog WHERE startedAt >= ? "
                f"AND policyDecision IS NULL AND {notTest}",
                (max(since, floor),)).fetchone()[0]
        else:
            # Chưa dòng nào có quyết định → cột vừa thêm, chưa chạy lần nào.
            # Không phải "tất cả đều lọt cửa".
            unexplained = 0
    finally:
        conn.close()

    return {"since": since, "byCapability": byCapability,
            "approvals": approvals, "ceoErrors": ceoErrors,
            "costUsd": round(cost or 0.0, 2), "unexplained": unexplained}


def weakSpots(data: dict) -> list:
    """Chỗ đang hỏng dần. Mỗi mục kèm SỐ, không kèm cảm giác."""
    spots = []
    for row in data["byCapability"]:
        if row["total"] < MIN_CALLS_FOR_RATE:
            continue
        rate = row["failed"] / row["total"]
        if rate >= FAILURE_RATE_THRESHOLD:
            spots.append(
                f"{row['companyId']}.{row['capability']}: trượt "
                f"{row['failed']}/{row['total']} ({rate:.0%})")
    return spots


def proposals(data: dict, stalledMissions: tuple = (),
              unreportedMissions: tuple = ()) -> list:
    """Đề xuất — CHỮ, không phải Task. Mỗi cái nói rõ VÌ SAO đề xuất.

    Không có "vì sao" thì admin phải tin, và tin thì sớm muộn thành bấm bừa.
    """
    items = []

    if data["unexplained"]:
        items.append(
            f"⚠ {data['unexplained']} lời gọi KHÔNG có quyết định policy. "
            "Đó là đường vào hệ không qua cửa — soát ngay bằng "
            "`travis.py health`.")

    for spot in weakSpots(data):
        items.append(
            f"{spot} — đọc `travis.py why <taskId>` của vài lần trượt để biết "
            "chúng hỏng cùng một kiểu hay mỗi lần một kiểu.")

    for row in data["approvals"][:2]:
        if row["n"] >= 20:
            items.append(
                f"{row['companyId']}.{row['capability']} bắt admin bấm duyệt "
                f"{row['n']} lần trong tuần. Nếu nó có nhóm CÓ NGHĨA, ít và "
                "đếm được thì khai `whitelistScope`; không thì đó là việc nên "
                "chuyển thành phiếu hẹn.")

    for missionId, objective in stalledMissions:
        items.append(
            f"Mission `{missionId}` đứng bánh: {objective[:60]}. Còn theo đuổi "
            "không? Bỏ dở mà không nói lý do thì lần sau lại làm lại từ đầu.")

    for missionId, objective in unreportedMissions:
        items.append(
            f"Mission `{missionId}` XONG mà chưa ai báo: {objective[:60]}. "
            "Trạng thái nằm trong sổ không phải là thông báo (N3).")

    if not items:
        items.append(
            "Không thấy gì đáng đề xuất. KHÔNG có nghĩa là mọi thứ tốt — chỉ "
            "có nghĩa là những phép soát ở đây không thấy gì.")
    return items


def render(data: dict, stalledMissions: tuple = (),
           unreportedMissions: tuple = ()) -> str:
    """Bản soát tuần cho admin đọc. Ngắn, và nói số."""
    lines = [f"— Soát tuần (từ {data['since'][:10]}) —", ""]

    totalCalls = sum(r["total"] for r in data["byCapability"])
    totalFailed = sum(r["failed"] for r in data["byCapability"])
    lines.append(f"Việc: {totalCalls} lời gọi · {totalFailed} trượt "
                 f"· CEO ${data['costUsd']}")

    if data["byCapability"]:
        lines.append("")
        lines.append("Dùng nhiều nhất:")
        for row in data["byCapability"][:5]:
            lines.append(f"  {row['companyId']}.{row['capability']}: "
                         f"{row['total']} lần" +
                         (f" ({row['failed']} trượt)" if row["failed"] else ""))

    spots = weakSpots(data)
    if spots:
        lines.append("")
        lines.append("Đang hỏng dần:")
        for spot in spots:
            lines.append(f"  {spot}")

    if data["ceoErrors"]:
        lines.append("")
        lines.append("CEO chết vì:")
        for row in data["ceoErrors"]:
            lines.append(f"  {row['n']}× {row['reason']}")

    lines.append("")
    lines.append("Đề xuất:")
    for index, item in enumerate(
            proposals(data, stalledMissions, unreportedMissions), start=1):
        lines.append(f"  {index}. {item}")

    lines.append("")
    lines.append("Đây là ĐỀ XUẤT, không phải việc đã làm. Không Task nào được")
    lines.append("sinh ra từ bản soát này — §34 dừng ở chữ, đúng như thiết kế.")
    return "\n".join(lines)


def weeklyReview(storePath: str = BACKOFFICE) -> str:
    """Điểm vào cho scheduler. Gom mission trực tiếp để không cần ai tiêm vào."""
    from ..missions import (
        missionsAwaitingReport, openStore, stalledMissions as findStalled,
    )
    data = collect(storePath=storePath)
    try:
        conn = openStore()
        stalled = tuple((m.missionId, m.objective) for m in findStalled(conn))
        unreported = tuple((m.missionId, m.objective)
                           for m in missionsAwaitingReport(conn))
        conn.close()
    except Exception as exc:
        # Sổ mission hỏng KHÔNG được làm chết cả bản soát — phần còn lại vẫn
        # đáng đọc. Nhưng phải NÓI RA, đừng nuốt (O10).
        stalled = unreported = ()
        return (render(data) + f"\n\n⚠ Không đọc được sổ mission: "
                f"{type(exc).__name__}: {exc}")
    return render(data, stalled, unreported)
