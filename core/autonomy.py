#!/usr/bin/env python3
"""core.autonomy — quyền tự chủ chỉ được nới khi có BẰNG CHỨNG.

    Level 0  chỉ đọc
    Level 1  chạy được việc an toàn
    Level 2  chạy + kiểm chứng
    Level 3  chạy + kiểm chứng + tự sửa khi trượt
    Level 4  mission dài hơi, tự lái

═══════════════════════════════════════════════════════════════════════
LUẬT GỐC: AUTONOMY KHÔNG ĐỒNG NGHĨA VỚI QUYỀN LỰC
═══════════════════════════════════════════════════════════════════════

Tăng autonomy là tăng thứ hệ được làm MÀ KHÔNG HỎI. Nó chỉ an toàn khi tăng
CÙNG LÚC với verification, permission và bằng chứng.

Nên ở đây mức được TÍNH RA từ lịch sử đo được, không phải đặt bằng tay trong
một file cấu hình. Đặt bằng tay thì nó chỉ phản ánh niềm tin của người gõ vào
hôm đó — và niềm tin không có hạn sử dụng, còn bằng chứng thì có.

Và một chiều nữa, quan trọng không kém: mức PHẢI TỤT được khi hỏng. Một cái
thang chỉ đi lên là một cái thang không ai dám trèo.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .contracts import RiskTier, TaskStatus

#: Số lần chạy tối thiểu trước khi được xét lên mức cao hơn.
#:
#: Ba lần là ít, cố ý: đây là trợ lý cá nhân của MỘT người, không phải hệ chạy
#: triệu lượt. Đòi 100 lần thì không việc gì lên mức 2 nổi, và một cái thang
#: không ai trèo được thì bằng không có thang.
MIN_RUNS_FOR_PROMOTION = 3

#: Tỉ lệ thành công tối thiểu, tính trên những lần ĐÃ KIỂM CHỨNG.
MIN_SUCCESS_RATE = 0.9

#: Một lần hỏng KHÔNG hoàn tác được là tụt thẳng, bất kể thống kê đẹp cỡ nào.
#:
#: Trung bình che mất cái đuôi, mà cái đuôi mới là thứ giết người: 99 lần ghi
#: đúng không bù được một lần xoá nhầm thứ không lấy lại được.
IRREVERSIBLE_FAILURE_DEMOTES = True


@dataclass(frozen=True)
class TrackRecord:
    """Lịch sử ĐO ĐƯỢC của một (company, capability).

    Đọc từ sổ audit, không nhận từ model. Model có thể mô tả nó đã làm tốt thế
    nào; con số thì không.
    """
    companyId: str
    capability: str
    totalRuns: int = 0
    verifiedSuccesses: int = 0
    failures: int = 0
    irreversibleFailures: int = 0
    lastFailureAt: Optional[str] = None

    @property
    def successRate(self) -> float:
        """Chưa chạy lần nào thì trả 0.0, KHÔNG phải 1.0.

        "Chưa hỏng lần nào" và "luôn chạy đúng" là hai câu rất khác nhau, và
        nhầm chúng là cách một thứ chưa ai thử được trao quyền tự chạy (O10 —
        đừng để con số 0 trông như một kết quả tốt).
        """
        if self.totalRuns <= 0:
            return 0.0
        return self.verifiedSuccesses / self.totalRuns


def maxAutonomyFor(riskTier: RiskTier) -> int:
    """Trần cứng theo rủi ro. KHÔNG bằng chứng nào nâng qua được.

    Đây là phần không thương lượng: `irreversible` mãi mãi dừng ở mức 0. Một
    thứ không lấy lại được thì "hệ đã làm đúng 500 lần" không phải lý lẽ —
    lần thứ 501 vẫn xoá mất thứ không có bản sao.
    """
    return {
        RiskTier.read: 4,
        RiskTier.low: 3,
        RiskTier.write: 2,
        RiskTier.high: 1,
        RiskTier.irreversible: 0,
    }[riskTier]


def earnedAutonomy(record: TrackRecord, riskTier: RiskTier) -> int:
    """Mức mà lịch sử này ĐÃ KIẾM ĐƯỢC. Luôn bị chặn bởi trần rủi ro."""
    ceiling = maxAutonomyFor(riskTier)

    if IRREVERSIBLE_FAILURE_DEMOTES and record.irreversibleFailures > 0:
        return 0
    if record.totalRuns < MIN_RUNS_FOR_PROMOTION:
        # Chưa đủ dữ liệu. Mức 1 chứ không phải 0: hệ vẫn chạy được việc an
        # toàn, chỉ là chưa được tự kết luận và chưa được tự sửa.
        return min(1, ceiling)
    if record.successRate < MIN_SUCCESS_RATE:
        return min(1, ceiling)
    if record.failures == 0 and record.totalRuns >= MIN_RUNS_FOR_PROMOTION * 3:
        return min(4, ceiling)
    return min(2, ceiling)


def mayActWithoutAsking(level: int, riskTier: RiskTier) -> bool:
    """Mức này có được làm mà không hỏi admin không.

    Mức 2 trở lên mới được, VÀ rủi ro phải cho phép. Hai điều kiện, không phải
    một — đó là chỗ "autonomy tăng cùng permission" được viết thành code.
    """
    return level >= 2 and maxAutonomyFor(riskTier) >= 2


def requiresVerification(level: int) -> bool:
    """Từ mức 2 trở lên BẮT BUỘC có bằng chứng.

    Nghịch lý có chủ ý: càng được tự do thì càng phải chứng minh nhiều. Ngược
    lại — tự do hơn thì kiểm ít hơn — là công thức để một hệ trôi dần vào chỗ
    không ai biết nó đang làm gì.
    """
    return level >= 2


def mayRetryAfterFailure(level: int) -> bool:
    """Tự sửa khi trượt là đặc quyền của mức 3.

    Dưới mức đó, hỏng thì DỪNG và báo. Tự thử lại khi chưa biết vì sao hỏng là
    cách biến một lỗi thành một vòng lặp — và L4 tồn tại vì điều đó đã xảy ra.
    """
    return level >= 3


def describeLevel(level: int) -> str:
    return {
        0: "mức 0 — chỉ đọc",
        1: "mức 1 — chạy được việc an toàn, không tự kết luận",
        2: "mức 2 — chạy và tự kiểm chứng, vẫn báo admin",
        3: "mức 3 — chạy, kiểm chứng, tự sửa khi trượt",
        4: "mức 4 — tự lái mission dài hơi",
    }.get(level, f"mức {level} — không xác định")


def explainAutonomy(record: TrackRecord, riskTier: RiskTier) -> str:
    """Vì sao mức là chừng này. Phải đọc được, vì nó quyết định hệ tự làm gì."""
    level = earnedAutonomy(record, riskTier)
    ceiling = maxAutonomyFor(riskTier)
    parts = [f"{record.companyId}.{record.capability}: {describeLevel(level)}"]

    if record.irreversibleFailures:
        parts.append(
            f"TỤT VỀ 0 — đã có {record.irreversibleFailures} lần hỏng không "
            "hoàn tác được. Trung bình che mất cái đuôi, mà cái đuôi mới là "
            "thứ giết người.")
    elif record.totalRuns < MIN_RUNS_FOR_PROMOTION:
        parts.append(
            f"mới chạy {record.totalRuns}/{MIN_RUNS_FOR_PROMOTION} lần — "
            "chưa đủ để kết luận gì")
    elif record.successRate < MIN_SUCCESS_RATE:
        parts.append(
            f"tỉ lệ đạt {record.successRate:.0%} < {MIN_SUCCESS_RATE:.0%}")
    else:
        parts.append(
            f"{record.verifiedSuccesses}/{record.totalRuns} lần đã kiểm chứng")

    if level == ceiling and ceiling < 4:
        parts.append(
            f"đã chạm TRẦN của `{riskTier.value}` (mức {ceiling}) — bằng chứng "
            "không nâng qua được trần rủi ro")
    return " · ".join(parts)


def recordFromAuditRows(companyId: str, capability: str,
                        rows: list) -> TrackRecord:
    """Dựng TrackRecord từ các dòng audit thật.

    `rows` là dict có `status` và `isReversible`. Chỉ `completed` tính là
    thành công — `ok` của company nghĩa là "chạy trót lọt", không phải "đã
    kiểm chứng" (xem core/verification.py).
    """
    total = successes = failures = irreversible = 0
    lastFailureAt = None
    for row in rows:
        total += 1
        status = row.get("status")
        if status == TaskStatus.completed.value:
            successes += 1
            continue
        if status in (TaskStatus.failed.value, TaskStatus.budgetExceeded.value):
            failures += 1
            lastFailureAt = row.get("createdAt") or lastFailureAt
            if row.get("isReversible") is False:
                irreversible += 1
    return TrackRecord(
        companyId=companyId, capability=capability, totalRuns=total,
        verifiedSuccesses=successes, failures=failures,
        irreversibleFailures=irreversible, lastFailureAt=lastFailureAt)
