#!/usr/bin/env python3
"""core.execution — chạy một Task, và KHÔNG biết gì về nghiệp vụ.

Executor biết: tiến trình con, hạn giờ, thử lại, giới hạn tài nguyên, thu
output, thu tác động ra ngoài. Executor KHÔNG biết chi tiêu là gì, lời nhắc là
gì. Thêm company mới không phải sửa file này (W3′).

═══════════════════════════════════════════════════════════════════════
BỐN BÀI HỌC ĐƯỢC ĐÓNG ĐINH Ở ĐÂY — mỗi cái là hoá đơn của một sự cố thật
═══════════════════════════════════════════════════════════════════════

O8 — CỬA VÀO KHÔNG ĐƯỢC PHÉP SẬP.
  Admin bấm duyệt 12:57:14, CEO treo, đúng 600 giây sau gateway văng
  `TimeoutExpired`. Admin chờ 10 phút, việc không chạy, mã duyệt đã tiêu, và
  thứ nhận về là một cục traceback. Mọi `subprocess.run(timeout=…)` ở đây phải
  có `except TimeoutExpired` trả về kết quả BÁO ĐƯỢC.

HAI CHIỀU CỦA TIMEOUT, ngược nhau, cả hai đều đã gây sự cố.
  · Ở tầng GỌI company (file này): timeout phải NHỎ HƠN HẲN ngân sách, để
    company kịp báo lỗi tử tế trước khi bị giết.
  · Ở tầng GỌI BỘ NÃO: timeout phải LỚN HƠN HẲN ngân sách dài nhất của tầng
    dưới. `run_ceo` chờ 600s trong khi `researchCompany` được cấp 900s — mọi
    lời gọi nghiên cứu chắc chắn bị giết giữa chừng.
  Nhầm chiều là giết việc đang chạy đúng.

CẮT LOG TỪ ĐUÔI, KHÔNG TỪ ĐẦU.
  Poller từng ghi `stderr[:300]`, mà traceback Python để LOẠI LỖI ở dòng cuối —
  journal cụt ở "line 1597, in h", mất đúng dòng nói hỏng vì cái gì.

MÃ THOÁT 0 KHÔNG CÓ NGHĨA LÀ CHẠY ĐƯỢC.
  Phiên OAuth hết hạn trả `{"is_error": true, …}` mà thoát MÃ 0; cùng sự cố
  hôm trước lại thoát mã 1. Soi cả nội dung, không chỉ mã thoát.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

from ..contracts import (
    Budget, Execution, PolicyOutcome, SideEffect, Task, TaskStatus, utcNow,
)

# Cắt bao nhiêu ký tự stderr khi company chết. Lấy từ ĐUÔI.
STDERR_TAIL = 2000

# Trừ hao trước hạn của manifest, để company còn kịp bắt lỗi và trả lời tử tế
# thay vì bị SIGKILL giữa chừng. Nhỏ quá thì cắt oan việc đang chạy đúng; lớn
# quá thì company không kịp nói gì. 2 giây là số đang dùng, chưa đo kỹ —
# ai đo được thì sửa kèm con số.
GRACE_SECONDS = 2


@dataclass
class ProcessLimits:
    """Trần tài nguyên cho MỘT lần chạy company.

    Giai đoạn này mới là cô lập LOGIC. Container/VM là Phase 12 — xem
    docs/ARCHITECTURE.md §6. Đừng gọi nó là sandbox khi nó chưa phải.
    """
    timeoutSec: int
    allowedSecretNames: tuple = ()
    allowedEnvNames: tuple = ()
    workingDirectory: Optional[str] = None


def buildChildEnvironment(limits: ProcessLimits, parentEnv: dict) -> dict:
    """C2.4 — company CHỈ nhận đúng những secret nó đã khai trong manifest.

    Truyền cả `os.environ` thì mọi company đều đọc được `NOTION_TOKEN`, và
    "mỗi company một phạm vi" chỉ còn là lời nói. Danh sách lấy từ manifest
    trên đĩa, KHÔNG lấy từ envelope — model không nới được (G3).
    """
    childEnv = {
        "PATH": parentEnv.get("PATH", "/usr/bin:/bin"),
        "HOME": parentEnv.get("HOME", ""),
        "LANG": parentEnv.get("LANG", "C.UTF-8"),
        "PYTHONIOENCODING": "utf-8",
    }
    for name in tuple(limits.allowedSecretNames) + tuple(limits.allowedEnvNames):
        if name in parentEnv:
            childEnv[name] = parentEnv[name]
    return childEnv


def runCompanyProcess(entrypoint: str, interpreter: str, envelope: dict,
                      limits: ProcessLimits,
                      parentEnv: Optional[dict] = None) -> dict:
    """Chạy một company theo hợp đồng C1: envelope vào stdin, result ra stdout.

    LUÔN trả về một dict đọc được. Không bao giờ ném ra ngoài — người gọi ở đây
    là cửa vào của cả hệ, và cửa vào không được phép sập (O8).
    """
    parentEnv = os.environ if parentEnv is None else parentEnv
    startedAt = time.time()

    try:
        proc = subprocess.run(
            [interpreter, entrypoint],
            input=json.dumps(envelope, ensure_ascii=False),
            capture_output=True, text=True,
            env=buildChildEnvironment(limits, parentEnv),
            cwd=limits.workingDirectory,
            timeout=max(1, limits.timeoutSec - GRACE_SECONDS),
        )
    except subprocess.TimeoutExpired:
        return _failure(envelope, "budgetExceeded",
                        f"Quá {limits.timeoutSec}s — cắt.",
                        startedAt)
    except FileNotFoundError as exc:
        # Thiếu hẳn cái lệnh để chạy. Đã có tiền lệ: thiếu `claude` ném
        # FileNotFoundError không ai bắt và sập luôn cửa vào.
        return _failure(envelope, "failed",
                        f"Không chạy được entrypoint: {exc}", startedAt)
    except Exception as exc:  # O3 — hỏng thì hỏng to, nhưng vẫn phải BÁO ĐƯỢC
        return _failure(envelope, "failed",
                        f"Executor hỏng ngoài dự kiến: "
                        f"{type(exc).__name__}: {exc}", startedAt)

    if proc.returncode != 0:
        # Cắt từ ĐUÔI: traceback Python để loại lỗi ở dòng cuối.
        detail = proc.stderr.strip()[-STDERR_TAIL:] or "tiến trình thoát khác 0"
        return _failure(envelope, "failed", detail, startedAt)

    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return _failure(
            envelope, "failed",
            f"Company in ra thứ không phải JSON ({exc}). "
            f"stdout(đầu)={proc.stdout[:300]!r} "
            f"stderr(đuôi)={proc.stderr[-STDERR_TAIL:]!r}",
            startedAt)

    if not isinstance(result, dict):
        return _failure(envelope, "failed",
                        "Company trả về JSON nhưng không phải object", startedAt)

    result.setdefault("usage", {})["durationMs"] = _elapsedMs(startedAt)
    return result


def looksSuccessful(result: dict) -> bool:
    """Có THẬT SỰ xong không — không hỏi "có chạy không".

    Cố ý không đặt tên `isDone`. Bài học `is_done()`: agent tự gọi "done" với
    nội dung là câu kế hoạch, company báo XONG, CEO nói với admin đã gửi form,
    thật ra chưa gửi gì. "Không chắc" tính là CHƯA XONG.

    Soi cả `isError`/`is_error` chứ không chỉ `status`: cùng một sự cố có khi
    thoát mã 0 có khi mã 1, và nhánh dự phòng chỉ đỡ được một trong hai hình.
    """
    if result.get("status") != "ok":
        return False
    if result.get("isError") or result.get("is_error"):
        return False
    if result.get("error"):
        return False
    return True


def sideEffectsOf(result: dict) -> tuple:
    """Những thay đổi ra thế giới bên ngoài mà company khai."""
    effects = []
    for raw in (result.get("sideEffects") or []):
        if not isinstance(raw, dict):
            continue
        effects.append(SideEffect(
            type=raw.get("type", "?"),
            target=raw.get("target", "") or "",
            # Company khai `reversible`; contracts gọi là `isReversible` theo
            # §7 (boolean mang tiền tố is/has/can). Đọc cả hai để hợp đồng C1
            # với 22 company đang chạy không phải đổi.
            isReversible=bool(raw.get("isReversible",
                                      raw.get("reversible", False))),
        ))
    return tuple(effects)


def warnIfWorldAlreadyChanged(result: dict) -> str:
    """Câu cảnh báo khi output sai schema NHƯNG việc đã làm rồi.

    Đã xảy ra thật 2026-08-04: bảng kế hoạch ĐƯỢC TẠO trên Notion trong khi CEO
    báo "chưa được tạo". Admin thử lại → làm hai lần. Không nói rõ chỗ này thì
    một lỗi định dạng biến thành một hành động lặp.
    """
    effects = result.get("sideEffects") or []
    if not effects:
        return ""
    kinds = sorted({e.get("type", "?") for e in effects if isinstance(e, dict)})
    return (f" ĐÃ CÓ {len(effects)} tác động ra ngoài rồi ({', '.join(kinds)}) "
            "— việc coi như đã làm, chỉ là kết quả trả về sai định dạng. "
            "ĐỪNG làm lại; kiểm tra thực tế trước.")


def toExecution(task: Task, policy: PolicyOutcome, result: dict) -> Execution:
    """Gói kết quả thô của company thành một Execution để ghi sổ."""
    usage = result.get("usage") or {}
    status = _statusFromResult(result)
    return Execution(
        taskId=task.taskId,
        traceId=task.traceId,
        companyId=task.companyId,
        capability=task.capability,
        policyDecision=policy.decision,
        inputHash=task.fingerprint,
        employeeId=task.employeeId,
        status=status,
        summary=result.get("summary", "") or "",
        outputValue=result.get("output"),
        errorText=result.get("error"),
        sideEffects=sideEffectsOf(result),
        costUsd=float(usage.get("costUsd", 0.0) or 0.0),
        paidVnd=float(usage.get("paidVnd", 0.0) or 0.0),
        durationMs=int(usage.get("durationMs", 0) or 0),
        finishedAt=utcNow(),
    )


# ══════════════════════════ nội bộ ══════════════════════════

def _statusFromResult(result: dict) -> TaskStatus:
    raw = result.get("status", "failed")
    try:
        status = TaskStatus(raw)
    except ValueError:
        # Status lạ thì coi là HỎNG, không coi là xong. Một trạng thái không ai
        # biết nghĩa mà được tính là thành công thì đó là `is_done()` quay lại.
        return TaskStatus.failed
    # `ok` của hợp đồng C1 nghĩa là "company chạy trót lọt", KHÔNG phải
    # "đã kiểm chứng". Chỉ Verification mới đẩy được lên `completed`.
    return TaskStatus.verifying if raw == "ok" else status


def _failure(envelope: dict, status: str, summary: str,
             startedAt: float) -> dict:
    return {
        "taskId": envelope.get("taskId", ""),
        "traceId": envelope.get("traceId", ""),
        "status": status,
        "output": None,
        "summary": summary,
        "error": summary,
        "sideEffects": [],
        "usage": {"steps": 0, "durationMs": _elapsedMs(startedAt),
                  "costUsd": 0.0},
    }


def _elapsedMs(startedAt: float) -> int:
    return int((time.time() - startedAt) * 1000)
