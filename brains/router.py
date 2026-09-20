#!/usr/bin/env python3
"""brains.router — chọn bộ não, và CHẶN theo ranh giới dữ liệu.

Hàm thuần: cùng đầu vào ra cùng thứ tự. Nó không gọi model, không đọc mạng —
việc gọi là của lib/llmClient.py, vốn đã có chuỗi dự phòng và đo chi phí.

═══════════════════════════════════════════════════════════════════════
LUẬT QUAN TRỌNG NHẤT Ở ĐÂY: ƯU TIÊN KHÔNG NÂNG ĐƯỢC QUYỀN
═══════════════════════════════════════════════════════════════════════

`taskRouting` nói NÊN dùng ai. `dataBoundary` nói ĐƯỢC PHÉP dùng ai.
Khi hai cái mâu thuẫn thì dataBoundary thắng, luôn luôn.

Viết ngược lại — lọc theo sở thích trước rồi mới soát ranh giới — thì một hôm
nào đó ai đó thêm một nhà rẻ vào `preferred` và dữ liệu đời tư của admin đi ra
ngoài mà không ai thấy dòng nào khác trong log.
"""
from __future__ import annotations

import os

import yaml

from core.contracts import DataClassification

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POLICY_PATH = os.path.join(ROOT, "registry", "brainPolicy.yaml")


class DataBoundaryError(PermissionError):
    """Không nhà nào được phép cầm mức dữ liệu này."""


def loadBrainPolicy(path: str = POLICY_PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def allowedBrainsFor(classification: DataClassification,
                     policy: dict) -> tuple:
    """Những nhà ĐƯỢC PHÉP nhận mức dữ liệu này. Rỗng nghĩa là không ai."""
    boundary = (policy.get("dataBoundary") or {}).get(classification.value)
    if boundary is None:
        # Mức không khai trong chính sách → ĐÓNG, không phải mở.
        #
        # Mặc định phải nghiêng về phía an toàn: quên khai một mức mới thì hệ
        # dừng và hỏi, chứ không lặng lẽ gửi đi đâu đó.
        return ()
    if boundary.get("denyAll"):
        return ()
    return tuple(boundary.get("allowed") or ())


def routeBrains(taskType: str, classification: DataClassification,
                policy: dict, employeePreferred: tuple = (),
                employeeFallback: tuple = (),
                unhealthyBrains: tuple = ()) -> tuple:
    """Thứ tự thử các nhà, đã lọc qua ranh giới dữ liệu.

    Thứ tự ghép: sở thích của employee → sở thích theo loại việc → dự phòng.
    Employee đứng trước vì nó cụ thể hơn; nhưng cả ba đều phải qua cùng một
    cái lọc.

    `unhealthyBrains` là kết quả ĐO ĐƯỢC từ `brains/fallback.py kiem`, không phải phỏng
    đoán. Nhà đang hỏng bị đẩy xuống CUỐI chứ không bị loại hẳn: nó có thể đã
    khỏe lại, và một ghế cuối hàng vẫn hơn không còn ghế nào.
    """
    allowed = set(allowedBrainsFor(classification, policy))
    if not allowed:
        raise DataBoundaryError(
            f"Mức dữ liệu `{classification.value}` không nhà nào được phép "
            "nhận. Việc này phải chạy trên máy nhà, hoặc không chạy.")

    routing = (policy.get("taskRouting") or {})
    forTask = routing.get(taskType) or routing.get("default") or {}

    ordered = []
    for source in (employeePreferred, forTask.get("preferred") or (),
                   employeeFallback, forTask.get("fallback") or ()):
        for brainId in source:
            if brainId in allowed and brainId not in ordered:
                ordered.append(brainId)

    healthy = [b for b in ordered if b not in unhealthyBrains]
    sick = [b for b in ordered if b in unhealthyBrains]
    return tuple(healthy + sick)


def explainRouting(taskType: str, classification: DataClassification,
                   policy: dict, chosen: tuple) -> str:
    """Câu giải thích đọc được, để đi vào Audit.

    Dashboard phải trả lời được "vì sao lời gọi này đi tới nhà đó", và câu trả
    lời phải còn đọc được sau nhiều tuần. Không có câu này thì mỗi lần nghi ngờ
    lại phải đọc lại code.
    """
    allowed = allowedBrainsFor(classification, policy)
    blocked = [b for b in _allBrainsMentioned(policy) if b not in allowed]
    text = (f"việc `{taskType}` · dữ liệu `{classification.value}` → "
            f"thử theo thứ tự: {', '.join(chosen) or '(không ai)'}")
    if blocked:
        text += f" · bị ranh giới dữ liệu chặn: {', '.join(sorted(set(blocked)))}"
    return text


#: Mức riêng tư của `fallback.riengTu` → mức phân loại dữ liệu.
#:
#: `canTrong` (mặc định) CẮT hồ sơ đời tư và số dư ví khỏi prompt, nên thứ đi
#: ra chỉ còn câu hỏi và cấu trúc hệ thống — `internal`.
#:
#: `dayDu` gửi CẢ hồ sơ và bức tranh tài chính. Đó là `sensitive`, và theo
#: brainPolicy thì chỉ `claude` với `local` được nhận — nghĩa là chuỗi dự
#: phòng (gemini, groq) bị chặn sạch.
#:
#: ĐÓ LÀ CÂU TRẢ LỜI ĐÚNG, dù nghe khó chịu: bộ não dự phòng chỉ chạy khi
#: Claude đã câm, và đúng lúc đó mà gửi số dư ví của admin sang một nhà miễn
#: phí thì cái giá không nằm ở chỗ tiện hay không tiện.
#: Admin muốn khác thì đổi `dataBoundary` trong registry/brainPolicy.yaml —
#: một hành động có chủ ý, đọc được, chứ không phải một nhánh `if` nào đó
#: lặng lẽ nới ra.
#: `toiThieu` cắt tới mức chỉ còn DANH MỤC năng lực — không hồ sơ, không bức
#: tranh tài chính, không lịch sử. Thứ đi ra gần như chỉ là câu hỏi, nên nó
#: MỞ NHẤT chứ không phải chặt nhất.
#:
#: ⚠ Bản đầu của bảng này chỉ khai hai mức, nên `toiThieu` rơi vào mặc định an
#: toàn `sensitive` và bị chặn CHẶT HƠN `canTrong` — ngược hoàn toàn với ý
#: nghĩa của nó. Bắt được ngay khi chạy `fallback.py trang-thai` và đọc dòng mô tả
#: ba mức. Mặc định an toàn là đúng, nhưng nó không thay được việc khai đủ.
PRIVACY_LEVEL_TO_CLASSIFICATION = {
    "toiThieu": DataClassification.public,
    "canTrong": DataClassification.internal,
    "dayDu": DataClassification.sensitive,
}


def classificationForPrivacyLevel(level: str) -> DataClassification:
    """Mức không nhận ra được thì coi là NHẠY CẢM, không phải công khai.

    Mặc định phải nghiêng về phía an toàn: thêm một mức mới mà quên khai ở đây
    thì hệ chặn và hỏi, chứ không lặng lẽ gửi đời tư admin đi đâu đó.
    """
    return PRIVACY_LEVEL_TO_CLASSIFICATION.get(level,
                                               DataClassification.sensitive)


def filterProviderChain(chain: list, classification: DataClassification,
                        policy: dict, extraAllowed: tuple = ()) -> tuple:
    """Lọc chuỗi dự phòng của `nao` theo ranh giới dữ liệu.

    `chain` là list các dict `{nha, model}` trong registry/models.yaml.
    Trả về (chuỗi còn dùng được, danh sách nhà bị chặn).

    `extraAllowed` cho phép người gọi thêm nhà vào danh sách — dùng cho ca thử
    với nhà GIẢ. Nó KHÔNG phải cửa hậu: danh sách thật vẫn đọc từ
    brainPolicy.yaml, và một tham số truyền vào từ mã gọi thì nằm cùng mức tin
    cậy với file đó. Nếu nó thành cách nới quyền ở production thì đó là lỗi
    của chỗ gọi, và `codemap` không đỡ được chuyện đó — nên chỗ gọi duy nhất
    được phép dùng nó là `tests/evals/`.

    KHÔNG ném lỗi khi lọc sạch: người gọi cần biết để nói với admin một câu tử
    tế, chứ không phải nhận một traceback đúng lúc Claude đã câm (O8).
    """
    allowed = set(allowedBrainsFor(classification, policy)) | set(extraAllowed)
    kept, blocked = [], []
    for step in chain or []:
        provider = (step or {}).get("nha")
        if provider in allowed:
            kept.append(step)
        elif provider:
            blocked.append(provider)
    return tuple(kept), tuple(dict.fromkeys(blocked))


def _allBrainsMentioned(policy: dict) -> list:
    names = []
    for boundary in (policy.get("dataBoundary") or {}).values():
        names.extend(boundary.get("allowed") or ())
    for forTask in (policy.get("taskRouting") or {}).values():
        names.extend(forTask.get("preferred") or ())
        names.extend(forTask.get("fallback") or ())
    return names
