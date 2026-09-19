#!/usr/bin/env python3
"""core.council — nhiều góc nhìn, nhưng KHÔNG nhầm đồng thuận với bằng chứng.

    Problem
      ├── brain A → proposal
      ├── brain B → proposal      (độc lập, không đọc của nhau)
      └── brain C → proposal
                 ↓
            Synthesizer
                 ↓
              Critic
                 ↓
             Decision

═══════════════════════════════════════════════════════════════════════
BÀI HỌC ĐẮT NHẤT VỀ HỘI ĐỒNG
═══════════════════════════════════════════════════════════════════════

Hỏi hội đồng "chiến lược kênh YouTube" thì mấy model tuôn ra:

    "kênh mới cần 90 ngày thoát sandbox"
    "nghiên cứu Tubics: 73% kênh triệu view dùng giọng AI"

Nghe như tri thức. Thật ra là văn mẫu. Chúng học từ CÙNG MỘT mớ chữ nên sai
giống nhau, và ba lần đoán biến thành một lần "đồng thuận".

Nên ở đây có hai lớp, và lớp thứ hai mới là lớp thật:

  lớp 1 — luật trong prompt  (model phá lúc nào cũng được, không ai biết)
  lớp 2 — MỘT PHÉP SOÁT BẰNG CODE  (`unsourcedClaims`)

Lớp 2 tồn tại chính vì lớp 1 không đáng tin.

═══════════════════════════════════════════════════════════════════════
KHI NÀO KHÔNG DÙNG HỘI ĐỒNG
═══════════════════════════════════════════════════════════════════════

Không cho: typo, format code, đọc file, đổi margin, chạy test.
Có thể cho: viết lại kiến trúc, thiết kế bảo mật, migration lớn, quyết định
kỹ thuật mơ hồ, nghiên cứu chưa rõ hướng.

Mỗi ghế là một lời gọi model. Một cuộc họp cho một việc đã biết cách làm là
tiền vứt đi — và bảng bẫy đã đo: việc biết trước cách làm thì kịch bản cứng
chạy 16 giây, đúng mọi lần, 0đ.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .contracts import newId, utcNow

#: Loại việc ĐÁNG mở hội đồng. Ngoài danh sách này thì mặc định là KHÔNG.
#:
#: Danh sách đóng chứ không phải danh sách cấm: mở hội đồng là hành động tốn
#: tiền, nên nó phải được cho phép rõ ràng, không phải chỉ cần "không bị cấm".
WORTH_A_COUNCIL = frozenset({
    "architectureRewrite", "securityDesign", "largeMigration",
    "ambiguousResearch", "complexTechnicalDecision",
})

#: Con số trong kết luận. Đây là thứ model hay bịa nhất, vì số nghe có vẻ chắc.
NUMBER_PATTERN = re.compile(r"\d[\d.,]*\s*%?")


@dataclass
class Proposal:
    """Một đề xuất ĐỘC LẬP.

    `sawOtherProposals` phải là False. Cho các model đọc của nhau thì cái thứ
    hai chỉ phụ hoạ cái thứ nhất, và ba tiếng nói thành một tiếng vọng.
    """
    brainId: str
    content: str
    sawOtherProposals: bool = False
    costUsd: float = 0.0


@dataclass
class CouncilResult:
    question: str
    proposals: tuple
    synthesis: str = ""
    critique: str = ""
    decision: str = ""
    unverifiedClaims: tuple = ()
    councilId: str = field(default_factory=lambda: newId("cnc"))
    createdAt: str = field(default_factory=utcNow)

    @property
    def totalCostUsd(self) -> float:
        return round(sum(p.costUsd for p in self.proposals), 4)

    @property
    def isTrustworthy(self) -> bool:
        """Có bằng chứng thật không, hay chỉ là mấy model gật gù với nhau.

        `unverifiedClaims` KHÔNG rỗng nghĩa là kết luận có số mà dữ kiện không
        có — phải nói lại cho admin, không được im lặng dùng.
        """
        return not self.unverifiedClaims


class CouncilMisuse(ValueError):
    """Mở hội đồng cho việc không đáng, hoặc mở sai cách."""


def assertWorthConvening(taskType: str, proposalCount: int) -> None:
    """Chặn TRƯỚC khi tiêu tiền, không phải than sau khi đã tiêu."""
    if taskType not in WORTH_A_COUNCIL:
        raise CouncilMisuse(
            f"`{taskType}` không thuộc loại việc đáng mở hội đồng. "
            f"Đáng: {', '.join(sorted(WORTH_A_COUNCIL))}. "
            "Việc đã biết trước cách làm thì viết kịch bản cứng — đo được là "
            "16 giây, đúng mọi lần, 0đ.")
    if proposalCount < 2:
        raise CouncilMisuse(
            "một ghế thì không phải hội đồng, chỉ là một lời gọi model đắt hơn")


def assertProposalsWereIndependent(proposals: tuple) -> None:
    """Không ghế nào được đọc bài của ghế khác trước khi viết bài mình."""
    tainted = [p.brainId for p in proposals if p.sawOtherProposals]
    if tainted:
        raise CouncilMisuse(
            f"những ghế này đã đọc đề xuất của ghế khác: {', '.join(tainted)}. "
            "Đọc của nhau thì cái sau phụ hoạ cái trước, và ba tiếng nói thành "
            "một tiếng vọng.")


def unsourcedClaims(conclusion: str, facts: str) -> tuple:
    """Con số nào trong kết luận mà KHÔNG có trong khối dữ kiện.

    Đây là lớp soát bằng CODE, lớp mà model không phá được. Nó không hiểu ngữ
    nghĩa — nó chỉ hỏi đúng một câu rất khó cãi: *con số này ở đâu ra?*

    P3 cấm company gọi company, nên việc ghép nguồn là của CEO/Core: `facts`
    phải là khối dữ kiện đã TRA TRƯỚC rồi đưa sang, không phải thứ hội đồng tự
    nhớ ra.
    """
    inFacts = set(NUMBER_PATTERN.findall(facts or ""))
    normalisedFacts = {_normalise(n) for n in inFacts}

    missing = []
    for raw in NUMBER_PATTERN.findall(conclusion or ""):
        value = _normalise(raw)
        if not value:
            continue
        # Số rất nhỏ thường là đánh số mục ("1.", "2.") — bỏ qua để đỡ ồn.
        if len(value.replace("%", "")) <= 1:
            continue
        if value not in normalisedFacts:
            missing.append(raw.strip())
    return tuple(dict.fromkeys(missing))


def _normalise(raw: str) -> str:
    return raw.strip().replace(",", "").replace(" ", "").rstrip(".")


def buildResult(question: str, proposals: tuple, synthesis: str,
                critique: str, decision: str, facts: str = "") -> CouncilResult:
    """Gói một phiên họp, KÈM phép soát nguồn.

    Gọi hàm này thay vì tự dựng CouncilResult: tự dựng thì dễ quên chạy
    `unsourcedClaims`, và quên nó là quay lại đúng chỗ hội đồng bịa số.
    """
    assertProposalsWereIndependent(proposals)
    return CouncilResult(
        question=question,
        proposals=tuple(proposals),
        synthesis=synthesis,
        critique=critique,
        decision=decision,
        unverifiedClaims=unsourcedClaims(f"{synthesis}\n{decision}", facts),
    )


def formatForAdmin(result: CouncilResult) -> str:
    """Nói lại cho admin. Thứ chưa kiểm chứng phải NẰM TRÊN, không nằm dưới."""
    lines = []
    if result.unverifiedClaims:
        lines.append(
            "⚠ CHƯA KIỂM CHỨNG — những con số sau có trong kết luận nhưng "
            "KHÔNG có trong dữ kiện đã tra: "
            + ", ".join(result.unverifiedClaims))
        lines.append(
            "  Hội đồng gồm nhiều model học từ cùng một mớ chữ, nên chúng sai "
            "giống nhau. Đồng thuận KHÔNG phải bằng chứng.")
        lines.append("")
    lines.append(f"Hỏi: {result.question}")
    lines.append(f"Ghế: {', '.join(p.brainId for p in result.proposals)} "
                 f"· ${result.totalCostUsd}")
    if result.critique:
        lines.append(f"Phản biện: {result.critique}")
    lines.append(f"Kết luận: {result.decision}")
    return "\n".join(lines)
