#!/usr/bin/env python3
"""core.brainRouter — chọn bộ não, và CHẶN theo ranh giới dữ liệu.

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

from .contracts import DataClassification

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

    `unhealthyBrains` là kết quả ĐO ĐƯỢC từ `ops/nao.py kiem`, không phải phỏng
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


def _allBrainsMentioned(policy: dict) -> list:
    names = []
    for boundary in (policy.get("dataBoundary") or {}).values():
        names.extend(boundary.get("allowed") or ())
    for forTask in (policy.get("taskRouting") or {}).values():
        names.extend(forTask.get("preferred") or ())
        names.extend(forTask.get("fallback") or ())
    return names
