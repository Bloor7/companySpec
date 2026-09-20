#!/usr/bin/env python3
"""core.permissions.isolation — ranh giới filesystem / mạng / tiến trình cho một employee.

⚠ ĐÂY LÀ CÔ LẬP LOGIC, CHƯA PHẢI SANDBOX THẬT.

Nói thẳng ngay dòng đầu, vì gọi nhầm tên là nguy hiểm hơn cả không có: người
đọc sau này sẽ tin rằng có container, rồi cho `forge` chạy một repo lạ.

Cái đang có:  một bộ luật đọc được, soát được bằng test, chặn ở TẦNG GỌI.
Cái CHƯA có: container/VM, cgroup, netns. Tiến trình con vẫn chạy cùng user,
             vẫn thấy cùng một filesystem.

Nghĩa là: một tiến trình CỐ TÌNH phá thì phá được. Tầng này chặn tai nạn và
chặn model đi lạc; nó KHÔNG chặn mã độc. Nên `lab/quarantine` vẫn là nơi duy
nhất được chạm vào repo lạ, và chạm bằng cách ĐỌC (core/acquisition.py).

Phase 12 của kế hoạch đòi container thật. Chừng nào chưa có, file này phải giữ
nguyên dòng cảnh báo trên đầu.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from ..contracts import Employee


class IsolationBreach(PermissionError):
    """Vượt ranh giới. Chặn TRƯỚC khi chạy, không phát hiện sau khi xong."""


@dataclass(frozen=True)
class SandboxPolicy:
    """Ranh giới của một employee, dạng dữ liệu.

    Danh sách RỖNG nghĩa là KHÔNG ĐƯỢC GÌ, không phải "không giới hạn". Viết
    rõ ở đây vì `whitelistScope: []` đã dạy đúng bài đó một lần.
    """
    subject: str
    allowedPaths: tuple = ()
    allowedHosts: tuple = ()
    allowedProcesses: tuple = ()
    allowedSecretNames: tuple = ()
    mayTouchProduction: bool = False

    def describe(self) -> str:
        return (
            f"{self.subject}: "
            f"đường dẫn={list(self.allowedPaths) or 'KHÔNG'} · "
            f"mạng={list(self.allowedHosts) or 'KHÔNG'} · "
            f"lệnh={list(self.allowedProcesses) or 'KHÔNG'} · "
            f"secret={list(self.allowedSecretNames) or 'KHÔNG'} · "
            f"production={'CÓ' if self.mayTouchProduction else 'KHÔNG'}")


def pathIsAllowed(policy: SandboxPolicy, path: str) -> bool:
    """Đường dẫn này có nằm trong vùng cho phép không.

    So bằng đường dẫn đã CHUẨN HOÁ, không bằng tiền tố chuỗi: `/workspace/x/../../etc`
    có tiền tố đúng nhưng trỏ ra ngoài. Cùng một bài học như `isInsideLab`.
    """
    if not policy.allowedPaths:
        return False
    resolved = os.path.realpath(path)
    for allowed in policy.allowedPaths:
        allowedResolved = os.path.realpath(allowed)
        try:
            if os.path.commonpath([resolved, allowedResolved]) == allowedResolved:
                return True
        except ValueError:
            continue  # khác ổ đĩa / khác gốc
    return False


def hostIsAllowed(policy: SandboxPolicy, host: str) -> bool:
    """Tên miền cho phép, khớp CHÍNH XÁC hoặc là tên miền con thật.

    So bằng `endswith` trần thì `evil-github.com` lọt qua luật `github.com` —
    một lỗi kinh điển, và nó im lặng.
    """
    if not policy.allowedHosts:
        return False
    host = (host or "").strip().lower().rstrip(".")
    for allowed in policy.allowedHosts:
        allowed = allowed.strip().lower()
        if host == allowed or host.endswith("." + allowed):
            return True
    return False


def processIsAllowed(policy: SandboxPolicy, executable: str) -> bool:
    if not policy.allowedProcesses:
        return False
    return os.path.basename(executable) in policy.allowedProcesses


def policyFromEmployee(employee: Employee, allowedPaths: tuple = (),
                       allowedHosts: tuple = (),
                       allowedProcesses: tuple = (),
                       allowedSecretNames: tuple = ()) -> SandboxPolicy:
    """Dựng ranh giới, và ép `cannot` của employee thắng mọi tham số truyền vào.

    Người gọi có thể lỡ tay mở rộng; `cannot` thì không được lỡ tay bỏ qua
    (E-2). Nên production bị khoá ở đây dựa trên chính manifest, không dựa
    trên thiện chí của chỗ gọi.
    """
    mayTouchProduction = not (
        employee.isForbidden("production.deploy")
        or employee.isForbidden("production.modify"))
    if employee.isForbidden("secret.read"):
        allowedSecretNames = ()
    return SandboxPolicy(
        subject=employee.employeeId,
        allowedPaths=tuple(allowedPaths),
        allowedHosts=tuple(allowedHosts),
        allowedProcesses=tuple(allowedProcesses),
        allowedSecretNames=tuple(allowedSecretNames),
        mayTouchProduction=mayTouchProduction,
    )


def assertWithinPolicy(policy: SandboxPolicy, path: Optional[str] = None,
                       host: Optional[str] = None,
                       executable: Optional[str] = None) -> None:
    """Chặn TRƯỚC khi chạy. Nói rõ vượt ở đâu."""
    if path is not None and not pathIsAllowed(policy, path):
        raise IsolationBreach(
            f"`{policy.subject}` không được chạm `{path}`. "
            f"Cho phép: {list(policy.allowedPaths) or 'KHÔNG GÌ CẢ'}")
    if host is not None and not hostIsAllowed(policy, host):
        raise IsolationBreach(
            f"`{policy.subject}` không được gọi `{host}`. "
            f"Cho phép: {list(policy.allowedHosts) or 'KHÔNG GÌ CẢ'}")
    if executable is not None and not processIsAllowed(policy, executable):
        raise IsolationBreach(
            f"`{policy.subject}` không được chạy `{executable}`. "
            f"Cho phép: {list(policy.allowedProcesses) or 'KHÔNG GÌ CẢ'}")


def isolationMaturity() -> dict:
    """Trả lời trung thực câu "cô lập tới đâu rồi".

    Có hàm này để không ai phải đoán, và để lúc lên container thì có đúng một
    chỗ phải sửa. Một hệ nói dối về mức cô lập của nó thì nguy hiểm hơn một hệ
    không cô lập gì — vì người dùng nó sẽ dám làm những việc đáng ra không dám.
    """
    return {
        "level": "logical",
        "enforced": ["filesystem (kiểm tầng gọi)", "network host allowlist",
                     "process allowlist", "secret scope"],
        "notEnforced": ["container/VM", "cgroup CPU/RAM", "network namespace",
                        "seccomp", "user riêng"],
        "meaning": ("Chặn tai nạn và chặn model đi lạc. KHÔNG chặn mã độc cố "
                    "tình phá. Repo lạ vẫn chỉ được ĐỌC, trong lab/quarantine."),
    }
