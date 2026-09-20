#!/usr/bin/env python3
"""brains.base — giao diện chung của một bộ não (§11 kế hoạch).

    class Brain:
        def reason(...)
        def generate(...)
        def review(...)

Ba động từ, không phải một. Chúng KHÁC nhau ở thứ người gọi mong đợi:

    reason   — nghĩ ra một hướng đi, chấp nhận dài và chậm
    generate — tạo ra nội dung theo yêu cầu đã rõ
    review   — soi một thứ đã có và nói chỗ sai

Gộp làm một `call()` thì router không còn gì để chọn: "việc này cần model
mạnh hay model rẻ" trả lời được chính vì ba động từ này khác nhau.

═══════════════════════════════════════════════════════════════════════
RANH GIỚI: KHÔNG NHÀ NÀO TỰ QUYẾT ĐƯỢC NÓ CÓ ĐƯỢC NHẬN VIỆC KHÔNG
═══════════════════════════════════════════════════════════════════════

`BrainContext.classification` đi cùng MỌI lời gọi, và `brains.router` chặn
TRƯỚC khi tới đây. Một lớp con tự nới ra là tự phá §29 — nên lớp cơ sở giữ
phép kiểm ấy trong `assertMayReceive`, và lớp con gọi nó ở đầu mỗi hàm.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))

from core.contracts import BrainReply, DataClassification  # noqa: E402
from .router import allowedBrainsFor, loadBrainPolicy  # noqa: E402


class BrainRefused(PermissionError):
    """Nhà này không được phép nhận mức dữ liệu đó."""


@dataclass
class BrainContext:
    """Thứ đi kèm mọi lời gọi. `classification` là BẮT BUỘC, không mặc định.

    Không cho nó giá trị mặc định là có chủ ý: người gọi PHẢI nói dữ liệu này
    thuộc loại gì. Mặc định `public` thì ai quên sẽ vô tình gửi đời tư admin
    ra ngoài; mặc định `secret` thì không gì chạy được và người ta sẽ tắt phép
    kiểm đi. Bắt khai là cách duy nhất không hỏng theo một trong hai chiều.
    """
    classification: DataClassification
    taskType: str = "default"
    employeeId: Optional[str] = None
    maxTokens: int = 1200
    timeoutSec: int = 90
    history: tuple = field(default_factory=tuple)


class Brain:
    """Lớp cơ sở. Lớp con chỉ cần cài `_call`."""

    brainId: str = "base"

    def __init__(self, policy: Optional[dict] = None):
        self._policy = policy if policy is not None else loadBrainPolicy()

    # ── ranh giới ──

    def mayReceive(self, classification: DataClassification) -> bool:
        return self.brainId in allowedBrainsFor(classification, self._policy)

    def assertMayReceive(self, context: BrainContext) -> None:
        if self.mayReceive(context.classification):
            return
        raise BrainRefused(
            f"`{self.brainId}` không được nhận dữ liệu mức "
            f"`{context.classification.value}`. Luật ở "
            "registry/brainPolicy.yaml — nới nó phải là sửa một file đọc "
            "được, không phải thêm một nhánh `if` ở đây.")

    # ── ba động từ ──

    def reason(self, prompt: str, context: BrainContext) -> BrainReply:
        """Nghĩ ra hướng đi. Chấp nhận dài và chậm."""
        self.assertMayReceive(context)
        return self._call(prompt, context, mode="reason")

    def generate(self, prompt: str, context: BrainContext) -> BrainReply:
        """Tạo nội dung theo yêu cầu đã rõ."""
        self.assertMayReceive(context)
        return self._call(prompt, context, mode="generate")

    def review(self, subject: str, context: BrainContext) -> BrainReply:
        """Soi một thứ đã có và nói chỗ sai.

        Prompt khác hẳn hai cái trên: nó được dặn đi TÌM LỖI. Một model được
        hỏi "cái này ổn chứ" gần như luôn trả lời "ổn" — phải hỏi "sai ở đâu".
        """
        self.assertMayReceive(context)
        return self._call(
            "Soi kỹ thứ dưới đây và chỉ ra chỗ SAI, chỗ thiếu, chỗ sẽ hỏng. "
            "Nếu không tìm thấy gì thì nói rõ là không tìm thấy, đừng khen.\n\n"
            + subject, context, mode="review")

    # ── lớp con cài cái này ──

    def _call(self, prompt: str, context: BrainContext, mode: str) -> BrainReply:
        raise NotImplementedError


class ProviderBrain(Brain):
    """Bộ não gọi qua `lib/llmClient.py`.

    Mọi nhà thật đều là lớp này với `brainId` và `defaultModel` khác nhau —
    phần gọi thật đã có sẵn và đã chạy qua nhiều sự cố, viết lại là mua lại
    những lần hỏng đã trả tiền rồi.
    """

    defaultModel: str = ""

    def _call(self, prompt: str, context: BrainContext, mode: str) -> BrainReply:
        import llmClient

        configuration = llmClient.nap()
        messages = []
        for turn in context.history:
            messages.append({"role": turn.get("role", "user"),
                             "content": turn.get("content", "")})
        messages.append({"role": "user", "content": prompt})

        try:
            result = llmClient.goi(
                nha=self.brainId, model=self.defaultModel,
                messages=messages, cfg=configuration,
                timeout=context.timeoutSec, max_tokens=context.maxTokens)
        except Exception as exc:
            # LUÔN trả về thứ đọc được. Một nhà hỏng không được làm sập người
            # gọi — chuỗi dự phòng chỉ có nghĩa nếu lỗi là DỮ LIỆU, không phải
            # một ngoại lệ bay thẳng lên trên (O8).
            return BrainReply(text="", brainId=self.brainId, isError=True,
                              rawText=f"{type(exc).__name__}: {exc}")

        text = (result or {}).get("chu") or ""
        return BrainReply(
            text=text, brainId=self.brainId,
            costUsd=float((result or {}).get("costUsd") or 0.0),
            # Mã thoát 0 KHÔNG có nghĩa là chạy được: soi cả nội dung.
            isError=not text.strip(),
            rawText=str(result)[:2000])
