#!/usr/bin/env python3
"""core.lab — nơi Travis thử cái mới, và cánh cổng ra Main.

    LAB               MAIN
    thử nghiệm        production
    không tin         tin được
    hỏng cũng được    không được hỏng
    thay được         có kiểm toán

P6 — Lab ĐƯỢC PHÉP thất bại. Đó không phải lời an ủi, đó là yêu cầu thiết kế:
một chỗ mà thất bại phải trả giá thì không ai dám thử gì, và không thử gì thì
hệ không học được gì.

Đổi lại, cổng ra Main phải chặt. Cụ thể là: nó đòi BẰNG CHỨNG, không đòi thiện
chí — cùng một luật V-1 của Verification, áp cho việc tiếp nhận đồ bên ngoài.
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from typing import Optional

from .contracts import newId, utcNow

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAB_ROOT = os.path.join(ROOT, "lab")

#: Vòng đời của một thứ đến từ bên ngoài. Không được nhảy cóc.
STAGES = ("quarantine", "sandboxes", "experiments", "benchmarks",
          "candidates", "rejected")

#: Bốn cấp tiếp nhận (§25 kế hoạch). Cấp càng cao, ràng buộc càng chặt.
ADOPTION_LEVELS = {
    "reference": "Chỉ học ý tưởng. Không mã nào của họ vào repo.",
    "skill": "Học cách làm, viết lại bằng mã của mình.",
    "dependency": "Dùng thẳng thư viện của họ — mã người lạ chạy trong hệ.",
    "integrated": "Biến thành company/tool chính thức của Travis.",
}


class PromotionBlocked(PermissionError):
    """Chưa đủ điều kiện ra Main. Nói rõ THIẾU GÌ."""


@dataclass
class Candidate:
    """Một thứ đang xin vào Main."""
    name: str
    source: str
    adoptionLevel: str
    candidateId: str = field(default_factory=lambda: newId("cnd"))
    createdAt: str = field(default_factory=utcNow)
    acquisitionReport: Optional[dict] = None
    benchmark: Optional[dict] = None
    approvedBy: str = ""
    notes: str = ""


def ensureLabLayout(labRoot: str = LAB_ROOT) -> dict:
    """Dựng thư mục Lab. Idempotent."""
    paths = {}
    for stage in STAGES:
        path = os.path.join(labRoot, stage)
        os.makedirs(path, exist_ok=True)
        paths[stage] = path
    return paths


def quarantinePathFor(name: str, labRoot: str = LAB_ROOT) -> str:
    """Chỗ một repo lạ hạ cánh. KHÔNG BAO GIỜ nằm ngoài lab/.

    Chặn cả `../` trong tên: tên do người ngoài đặt (URL repo), và một cái tên
    như `../../ops` sẽ ghi đè đúng chỗ nguy hiểm nhất.
    """
    safeName = _safeName(name)
    return os.path.join(labRoot, "quarantine", safeName)


def _safeName(name: str) -> str:
    cleaned = os.path.basename(name.strip().rstrip("/"))
    cleaned = cleaned.replace("..", "").replace(os.sep, "")
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    if not cleaned or cleaned.startswith("."):
        raise ValueError(f"tên không dùng được cho thư mục cách ly: {name!r}")
    return cleaned


def isInsideLab(path: str, labRoot: str = LAB_ROOT) -> bool:
    """Đường dẫn này có thật sự nằm trong lab/ không.

    Hỏi bằng đường dẫn đã chuẩn hoá, không hỏi bằng chuỗi có tiền tố: một
    symlink hoặc một chuỗi `lab/../ops` đều qua được phép so chuỗi.
    """
    resolved = os.path.realpath(path)
    labResolved = os.path.realpath(labRoot)
    return os.path.commonpath([resolved, labResolved]) == labResolved


def registerCandidate(candidate: Candidate,
                      labRoot: str = LAB_ROOT) -> str:
    """Ghi một ứng viên vào sổ. Ghi cả thứ sẽ bị từ chối (O5)."""
    ensureLabLayout(labRoot)
    path = os.path.join(labRoot, "candidates",
                        f"{candidate.candidateId}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({
            "candidateId": candidate.candidateId,
            "name": candidate.name,
            "source": candidate.source,
            "adoptionLevel": candidate.adoptionLevel,
            "createdAt": candidate.createdAt,
            "acquisitionReport": candidate.acquisitionReport,
            "benchmark": candidate.benchmark,
            "approvedBy": candidate.approvedBy,
            "notes": candidate.notes,
        }, fh, ensure_ascii=False, indent=2)
    return path


def reject(candidate: Candidate, reason: str,
           labRoot: str = LAB_ROOT) -> str:
    """Từ chối, và GIỮ LẠI hồ sơ.

    Vứt đi thì sáu tháng sau có người mang đúng repo đó quay lại và cả vòng
    soi chạy lại từ đầu. Lần từ chối cũng là dữ liệu.
    """
    if not reason.strip():
        raise ValueError("từ chối thì phải nói lý do")
    ensureLabLayout(labRoot)
    candidate.notes = reason
    path = os.path.join(labRoot, "rejected", f"{candidate.candidateId}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"candidateId": candidate.candidateId,
                   "name": candidate.name, "source": candidate.source,
                   "rejectedAt": utcNow(), "reason": reason}, fh,
                  ensure_ascii=False, indent=2)
    return path


def checkPromotionReadiness(candidate: Candidate) -> list:
    """Những thứ CÒN THIẾU để ra Main. Rỗng nghĩa là đủ điều kiện.

    Trả về danh sách thiếu chứ không trả về true/false: "chưa đủ" mà không nói
    thiếu gì thì người ta đoán, và đoán thì thường đoán là "chắc ổn".
    """
    missing = []

    if candidate.adoptionLevel not in ADOPTION_LEVELS:
        missing.append(
            f"`adoptionLevel` phải là một trong: "
            f"{', '.join(sorted(ADOPTION_LEVELS))}")

    report = candidate.acquisitionReport
    if not report:
        missing.append("chưa có báo cáo soi repo (acquisitionReport)")
    else:
        high = [f for f in (report.get("findings") or [])
                if f.get("severity") == "high"]
        if high:
            categories = sorted({f.get("category", "?") for f in high})
            missing.append(
                f"còn {len(high)} điểm NGHIÊM TRỌNG chưa xử lý "
                f"({', '.join(categories)})")
        if report.get("licenceClass") == "unknown":
            missing.append(
                "giấy phép không xác định — không có giấy phép nghĩa là "
                "KHÔNG được phép dùng, chứ không phải tự do dùng")

    # Cấp `reference` chỉ học ý tưởng, không mã nào vào repo — nên không cần
    # benchmark. Từ `dependency` trở lên là mã người lạ CHẠY TRONG HỆ.
    if candidate.adoptionLevel in ("dependency", "integrated"):
        if not candidate.benchmark:
            missing.append(
                "chưa có số đo (benchmark). Từ cấp `dependency` trở lên là mã "
                "người lạ chạy trong hệ — 'trông có vẻ tốt' không phải lý do.")
        if not candidate.approvedBy:
            missing.append("chưa có admin duyệt")

    return missing


def promote(candidate: Candidate, destination: str,
            sourcePath: str = "", labRoot: str = LAB_ROOT) -> str:
    """Đưa một ứng viên ra Main. Chặn nếu chưa đủ bằng chứng.

    `destination` phải NGOÀI lab/ — đó là cả ý nghĩa của thăng cấp. Nhưng
    nguồn thì phải TRONG lab/: thăng cấp một thứ chưa từng qua cách ly là bỏ
    qua toàn bộ quy trình.
    """
    missing = checkPromotionReadiness(candidate)
    if missing:
        raise PromotionBlocked(
            f"`{candidate.name}` chưa ra Main được:\n  - "
            + "\n  - ".join(missing))

    if sourcePath:
        if not isInsideLab(sourcePath, labRoot):
            raise PromotionBlocked(
                f"nguồn `{sourcePath}` không nằm trong lab/ — thăng cấp một "
                "thứ chưa từng qua cách ly là bỏ qua cả quy trình")
        if isInsideLab(destination, labRoot):
            raise PromotionBlocked(
                f"đích `{destination}` vẫn nằm trong lab/ — đó không phải "
                "thăng cấp")
        os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)
        shutil.copytree(sourcePath, destination, dirs_exist_ok=True)

    return destination
