#!/usr/bin/env python3
"""core.task — vòng đời của một Task (§4 kế hoạch).

    created → planned → approvalRequired → approved → scheduled
            → running → verifying → completed

Nhánh kết thúc khác: failed · cancelled · denied · quarantined · blocked ·
budgetExceeded · needsInput.

═══════════════════════════════════════════════════════════════════════
LUẬT T-1 — TRẠNG THÁI LÀ THỨ CORE GHI, KHÔNG PHẢI THỨ TASK TỰ NHẬN
═══════════════════════════════════════════════════════════════════════

Bài học `is_done()`: agent tự gọi "done" với nội dung là câu KẾ HOẠCH →
company báo XONG → CEO nói với admin đã gửi form → thật ra chưa gửi gì.

Nên module này không có hàm nào tên `markDone`. Đường duy nhất tới `completed`
đi qua `core.verification.concludeTask`, và nó đòi bằng chứng.

`canTransitionTo` tồn tại để một bước nhảy sai BỊ CHẶN chứ không lặng lẽ xảy
ra: `created → completed` là thứ không bao giờ được phép, và nếu nó xảy ra
được thì cả tầng Verification chỉ là trang trí.
"""
from __future__ import annotations

from typing import Optional

from ..contracts import (
    Budget, IssuedBy, RiskTier, Task, TaskStatus, utcNow,
)

#: Từ trạng thái nào đi được sang trạng thái nào.
#:
#: Bảng này CỐ Ý không cho `created → completed`. Đường tới `completed` chỉ có
#: một: qua `verifying`, tức là qua bằng chứng (V-1).
ALLOWED_TRANSITIONS = {
    TaskStatus.created: (
        TaskStatus.planned, TaskStatus.approvalRequired, TaskStatus.running,
        TaskStatus.denied, TaskStatus.blocked, TaskStatus.cancelled,
        TaskStatus.quarantined, TaskStatus.needsInput,
    ),
    TaskStatus.planned: (
        TaskStatus.approvalRequired, TaskStatus.running, TaskStatus.scheduled,
        TaskStatus.denied, TaskStatus.blocked, TaskStatus.cancelled,
    ),
    TaskStatus.approvalRequired: (
        TaskStatus.approved, TaskStatus.denied, TaskStatus.cancelled,
        TaskStatus.scheduled,
    ),
    TaskStatus.approved: (
        TaskStatus.running, TaskStatus.cancelled, TaskStatus.budgetExceeded,
    ),
    TaskStatus.scheduled: (
        TaskStatus.approved, TaskStatus.running, TaskStatus.cancelled,
    ),
    TaskStatus.running: (
        TaskStatus.verifying, TaskStatus.failed, TaskStatus.budgetExceeded,
        TaskStatus.needsInput, TaskStatus.cancelled,
    ),
    # CHỈ từ đây mới tới `completed` được.
    TaskStatus.verifying: (
        TaskStatus.completed, TaskStatus.failed, TaskStatus.needsInput,
    ),
    TaskStatus.needsInput: (
        TaskStatus.running, TaskStatus.cancelled, TaskStatus.failed,
    ),
}


class IllegalTransition(ValueError):
    """Bước nhảy trạng thái không hợp lệ. NÉM, không nuốt (O10)."""


def canTransitionTo(current: TaskStatus, target: TaskStatus) -> bool:
    if current.isTerminal:
        return False
    return target in ALLOWED_TRANSITIONS.get(current, ())


def transition(task: Task, target: TaskStatus,
               reason: str = "") -> Task:
    """Đổi trạng thái, hoặc NÉM nếu bước nhảy đó không hợp lệ.

    Ném chứ không trả False: một bước nhảy sai mà chỉ trả về False thì người
    gọi dễ bỏ qua giá trị trả về, và Task đứng im ở trạng thái cũ trong khi
    mọi người tưởng nó đã đi tiếp. Im lặng là cách hỏng tệ nhất ở đây.
    """
    if not canTransitionTo(task.status, target):
        raise IllegalTransition(
            f"{task.taskId}: không đi từ `{task.status.value}` sang "
            f"`{target.value}` được"
            + (f" ({reason})" if reason else "")
            + (". Trạng thái này đã kết thúc."
               if task.status.isTerminal
               else f". Từ `{task.status.value}` chỉ đi được sang: "
                    + ", ".join(s.value for s in
                                ALLOWED_TRANSITIONS.get(task.status, ()))))
    task.status = target
    return task


def newTask(companyId: str, capability: str, inputValue: dict,
            riskTier: RiskTier, *, traceId: Optional[str] = None,
            issuedBy: IssuedBy = IssuedBy.admin,
            employeeId: Optional[str] = None,
            missionId: Optional[str] = None,
            projectId: Optional[str] = None,
            parentTaskId: Optional[str] = None,
            adminIntent: str = "") -> Task:
    """Dựng một Task mới ở trạng thái `created`."""
    task = Task(
        companyId=companyId, capability=capability, inputValue=inputValue,
        riskTier=riskTier, issuedBy=issuedBy, employeeId=employeeId,
        missionId=missionId, projectId=projectId, parentTaskId=parentTaskId,
        adminIntent=adminIntent)
    if traceId:
        task.traceId = traceId
    return task


def childTask(parent: Task, companyId: str, capability: str,
              inputValue: dict, riskTier: RiskTier) -> Task:
    """Task con — CÙNG trace, CÙNG mission, nhưng quyền thì KHÔNG thừa kế.

    Task con vẫn đi qua đúng cánh cửa Policy như mọi Task khác. "Cha đã được
    duyệt nên con khỏi hỏi" là cách biến một lần bấm nút thành tờ séc khống:
    admin duyệt MỘT NỘI DUNG (G4), không duyệt một ý định.
    """
    return newTask(
        companyId=companyId, capability=capability, inputValue=inputValue,
        riskTier=riskTier, traceId=parent.traceId,
        issuedBy=parent.issuedBy, employeeId=parent.employeeId,
        missionId=parent.missionId, projectId=parent.projectId,
        parentTaskId=parent.taskId, adminIntent=parent.adminIntent)


def budgetFor(maxDurationSec: int, *, depth: int = 1,
              maxCostUsd: float = 1.0) -> Budget:
    """Ngân sách một lần chạy. Hạn chót lấy từ MANIFEST, không từ số mặc định.

    Company biết việc của nó cần bao lâu: `auditPage` cần 600s còn `addExpense`
    cần 20s. Ép chung một trần là hoặc cắt oan, hoặc treo vô ích (L3).
    """
    from datetime import datetime, timedelta, timezone
    deadline = datetime.now(timezone.utc) + timedelta(seconds=maxDurationSec)
    return Budget(deadlineAt=deadline.strftime("%Y-%m-%dT%H:%M:%SZ"),
                  depth=depth, maxCostUsd=maxCostUsd)


def describeLifecycle(task: Task) -> str:
    """Task này đang ở đâu, và đi tiếp được sang đâu."""
    if task.status.isTerminal:
        return (f"{task.taskId}: `{task.status.value}` — đã kết thúc"
                + (", ĐÃ KIỂM CHỨNG" if task.status.isSuccess
                   else ", chưa bao giờ tới `completed`"))
    nextStates = ALLOWED_TRANSITIONS.get(task.status, ())
    return (f"{task.taskId}: `{task.status.value}` → đi tiếp được sang "
            + (", ".join(s.value for s in nextStates) or "(không đâu cả)"))


__all__ = [
    "ALLOWED_TRANSITIONS", "IllegalTransition", "budgetFor", "canTransitionTo",
    "childTask", "describeLifecycle", "newTask", "transition", "utcNow",
]
