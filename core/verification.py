#!/usr/bin/env python3
"""core.verification — "xong" phải có BẰNG CHỨNG, không phải lời khai.

═══════════════════════════════════════════════════════════════════════
VÌ SAO TẦNG NÀY TỒN TẠI
═══════════════════════════════════════════════════════════════════════

Bảng bẫy CLAUDE.md, hai dòng liền nhau:

  · `is_done()` tưởng là thành công — agent tự gọi "done" với nội dung là câu
    KẾ HOẠCH. Company báo XONG, CEO nói với admin đã gửi form, thật ra chưa
    gửi gì.

  · Việc XONG mà không ai nói cho người cần biết — hộp dựng xong cả một web
    todolist, rồi đặt việc về `choXem` và im lặng. Cùng tối admin hỏi "cái web
    làm sao xem" và CEO đáp "em không viết file HTML được". Sản phẩm nằm cách
    đó đúng một thư mục.

Cả hai đều KHÔNG phải lỗi kỹ thuật. Không bộ phận nào hỏng. Chỉ là **không ai
chứng minh gì cả**.

═══════════════════════════════════════════════════════════════════════
BA LUẬT
═══════════════════════════════════════════════════════════════════════

V-1  Không có bằng chứng thì KHÔNG `completed`. `inconclusive` tính là TRƯỢT.
     "Không chắc" là CHƯA XONG, không phải là xong.

V-2  Thiếu công cụ kiểm ≠ đã kiểm. Dự án không có script test thì phép kiểm
     `test` ra `inconclusive`, KHÔNG ra `skipped` — trừ khi có người KHAI RÕ
     rằng dự án này không cần. Phải nói ra thì mới được bỏ qua.

V-3  Bộ đo đứng trong phép đo. Mọi lần chạy kiểm đều ghi thời lượng và kết
     quả; không có phép kiểm nào chạy ngoài sổ.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

import yaml

from .contracts import CheckStatus, TaskStatus, Verification, VerificationCheck

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFICATION_PATH = os.path.join(ROOT, "registry", "verification.yaml")

#: Khai rõ "dự án này không cần phép kiểm đó". Phải viết ra, không được để
#: trống rồi hy vọng bộ kiểm hiểu ý (V-2).
NOT_APPLICABLE = "notApplicable"


@dataclass
class CheckSpec:
    """Một phép kiểm: chạy lệnh gì, bao lâu, có bắt buộc không."""
    name: str
    command: Optional[str]
    timeoutSec: int = 300
    isRequired: bool = True
    workingDirectory: Optional[str] = None


def loadVerificationPolicy(path: str = VERIFICATION_PATH) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def requiredCheckNames(policy: dict, changeKind: str) -> tuple:
    """Loại thay đổi nào cần bằng chứng gì.

    Sửa UI cần thêm mắt nhìn; sửa sổ sách cần đọc lại đúng cái vừa ghi. Một bộ
    kiểm chung cho mọi thứ thì hoặc thừa (chậm vô ích) hoặc thiếu (bỏ sót đúng
    chỗ quan trọng).
    """
    suites = policy.get("changeKinds") or {}
    suite = suites.get(changeKind) or suites.get("default") or {}
    return tuple(suite.get("required") or ())


def runCheck(spec: CheckSpec) -> VerificationCheck:
    """Chạy MỘT phép kiểm. Luôn trả về kết quả đọc được, không ném ra ngoài."""
    if spec.command == NOT_APPLICABLE:
        # V-2 — được bỏ qua vì CÓ NGƯỜI KHAI RÕ, không phải vì im lặng.
        return VerificationCheck(
            spec.name, CheckStatus.skipped,
            "khai rõ là không áp dụng cho dự án này")

    if not spec.command:
        # Đây là chỗ V-2 sống. Trước đây thiếu công cụ = mặc nhiên qua, nên
        # "build PASS" có khi nghĩa là "không có lệnh build nào để chạy".
        return VerificationCheck(
            spec.name, CheckStatus.inconclusive,
            "không có lệnh để chạy — KHÔNG chứng minh được gì. Khai lệnh, "
            f"hoặc khai rõ `{NOT_APPLICABLE}` nếu dự án này thật sự không cần.")

    startedAt = time.time()
    try:
        proc = subprocess.run(
            shlex.split(spec.command),
            capture_output=True, text=True,
            cwd=spec.workingDirectory, timeout=spec.timeoutSec)
    except subprocess.TimeoutExpired:
        return VerificationCheck(
            spec.name, CheckStatus.inconclusive,
            f"quá {spec.timeoutSec}s — cắt. Không kết luận được, nên tính là "
            "CHƯA ĐẠT.")
    except FileNotFoundError as exc:
        return VerificationCheck(
            spec.name, CheckStatus.inconclusive,
            f"không chạy được lệnh: {exc}")
    except Exception as exc:
        return VerificationCheck(
            spec.name, CheckStatus.inconclusive,
            f"{type(exc).__name__}: {exc}")

    durationMs = int((time.time() - startedAt) * 1000)
    if proc.returncode == 0:
        return VerificationCheck(spec.name, CheckStatus.passed,
                                 f"{durationMs}ms")
    # Cắt từ ĐUÔI — loại lỗi nằm ở dòng cuối.
    detail = (proc.stderr.strip() or proc.stdout.strip())[-1500:]
    return VerificationCheck(
        spec.name, CheckStatus.failed,
        f"thoát mã {proc.returncode} sau {durationMs}ms · {detail}")


def verify(specs: tuple) -> Verification:
    """Chạy cả bộ và gói thành bằng chứng."""
    return Verification(checks=tuple(runCheck(spec) for spec in specs))


def concludeTask(verification: Verification,
                 requiredNames: tuple = ()) -> TaskStatus:
    """Bằng chứng này có đủ để gọi là XONG không.

    Đây là hàm thay cho `is_done()`. Khác biệt nằm ở ba chỗ:
      · không có bằng chứng nào → CHƯA xong (không phải "chắc ổn")
      · `inconclusive` → CHƯA xong (không phải "coi như qua")
      · thiếu một phép kiểm BẮT BUỘC → CHƯA xong (không phải "đủ rồi")
    """
    if not verification.checks:
        return TaskStatus.verifying

    present = {check.name for check in verification.checks}
    missing = [name for name in requiredNames if name not in present]
    if missing:
        return TaskStatus.verifying

    for check in verification.checks:
        if check.name not in requiredNames:
            continue
        if check.status in _ACCEPTABLE:
            continue
        return TaskStatus.failed

    return TaskStatus.completed


#: Trạng thái được coi là "không chặn".
#:
#: `skipped` nằm ở đây, `inconclusive` thì KHÔNG — và đó là cả điểm của V-2:
#:
#:   skipped      = CÓ NGƯỜI KHAI RÕ rằng phép kiểm này không áp dụng
#:                  (`notApplicable`). Một quyết định có chủ ý, đọc được trong
#:                  file, và ai sửa file cũng thấy.
#:   inconclusive = KHÔNG CHỨNG MINH ĐƯỢC GÌ — thiếu lệnh, quá giờ, thiếu
#:                  binary. Im lặng, không ai quyết định gì cả.
#:
#: Gộp hai thứ này làm một là hỏng theo một trong hai chiều: hoặc "không có
#: lệnh build" được tính là PASS (chiều nguy hiểm), hoặc khai rõ `notApplicable`
#: lại làm mọi thứ trượt và không ai dùng được cửa thoát đó.
#:
#: ⚠ Bản đầu của file này gộp chúng, và chính bộ đo bắt được khi chạy selfCheck
#: của repo: `typecheck: notApplicable` (Python thuần, đúng) làm kết luận ra
#: `failed`. Ghi lại đây để đừng ai "dọn cho gọn" bằng cách gộp lại.
#:
#: Lấy từ contracts.py chứ KHÔNG định nghĩa lại: bản đầu định nghĩa riêng ở
#: đây, và khi sửa thì chỉ sửa một bên — nên `Verification.isVerified` vẫn coi
#: `skipped` là trượt trong khi `concludeTask` đã chấp nhận nó. Hai bản của
#: cùng một luật là cách nó lệch đi.
from .contracts import _VERIFICATION_ACCEPTABLE as _ACCEPTABLE  # noqa: E402


def explainVerdict(verification: Verification,
                   requiredNames: tuple = ()) -> str:
    """Câu nói cho admin. Nói THIẾU GÌ, không chỉ nói trượt.

    "Chưa xong" mà không nói thiếu gì thì admin phải đi mò — và mò thì thường
    kết thúc bằng bấm lại một lần nữa.
    """
    present = {check.name for check in verification.checks}
    missing = [name for name in requiredNames if name not in present]
    failed = [check for check in verification.checks
              if check.name in requiredNames
              and check.status not in _ACCEPTABLE]

    if missing:
        return ("CHƯA XONG — thiếu bằng chứng: " + ", ".join(missing)
                + ". Phép kiểm bắt buộc chưa chạy thì không kết luận được.")
    if failed:
        parts = [f"{c.name} ({c.status.value}: {c.detail[:120]})"
                 for c in failed]
        return "CHƯA XONG — " + " · ".join(parts)
    if not verification.checks:
        return "CHƯA XONG — chưa có phép kiểm nào chạy."
    return ("XONG — " + ", ".join(f"{c.name} {c.status.value}"
                                  for c in verification.checks))


#: Bộ kiểm cho MỘT LỜI GỌI COMPANY. Tên cố định, dùng ở cả dispatch và test.
COMPANY_CALL_CHECKS = ("statusOk", "outputSchema", "sideEffectRecorded")


def verifyCompanyCall(status: str, outputSchemaErrors: tuple,
                      sideEffects: tuple, isDryRun: bool = False,
                      declaresSideEffects: bool = True) -> Verification:
    """Bằng chứng cho một lời gọi company — thứ dispatch VỐN ĐÃ làm.

    ═══ VÌ SAO HÀM NÀY TỒN TẠI ═══

    Dispatch từ lâu đã soát output theo `outputSchema` và ghi `sideEffects`.
    Đó CHÍNH LÀ bằng chứng — nhưng nó trôi mất ngay sau khi dùng: kết quả trả
    về chỉ còn `status: ok`, và sổ chỉ ghi `ok`.

    Hệ quả: sáu tháng sau không ai trả lời được "lần đó đã kiểm những gì".
    Hàm này không thêm phép kiểm nào mới — nó chỉ GIỮ LẠI thứ đã kiểm, dưới
    dạng đọc được.

    ═══ VÌ SAO KHÔNG ĐÒI THÊM ═══

    Cám dỗ là bắt mọi lời gọi company chạy typecheck/build/test. Nhưng company
    là code cứng đã có test riêng; chạy lại cả bộ cho mỗi lần ghi một khoản
    chi thì việc 0,3 giây thành 40 giây, và thứ gì chậm vô ích thì người ta
    tắt nó đi.

    Bằng chứng phải TƯƠNG XỨNG với việc. Việc nặng hơn (sửa code, đổi UI) thì
    dùng bộ kiểm trong registry/verification.yaml.
    """
    checks = []

    if isDryRun:
        # Chạy khô không chạm gì, nên không có gì để kiểm chứng — và nói thẳng
        # điều đó, đừng cho nó một dấu PASS mà nó chưa kiếm được.
        return Verification(checks=(
            VerificationCheck("statusOk", CheckStatus.skipped,
                              "chạy khô — không có tác động nào để kiểm"),))

    checks.append(VerificationCheck(
        "statusOk",
        CheckStatus.passed if status == "ok" else CheckStatus.failed,
        f"company trả `{status}`"))

    checks.append(VerificationCheck(
        "outputSchema",
        CheckStatus.passed if not outputSchemaErrors else CheckStatus.failed,
        "khớp outputSchema" if not outputSchemaErrors
        else "; ".join(outputSchemaErrors)[:300]))

    # Năng lực có tác động ra ngoài mà KHÔNG khai sideEffects là một khoảng
    # tối: thế giới đã đổi và sổ không biết. Nhưng năng lực chỉ ĐỌC thì không
    # khai gì mới là đúng — nên người gọi phải nói rõ nó thuộc loại nào.
    if not declaresSideEffects:
        checks.append(VerificationCheck(
            "sideEffectRecorded", CheckStatus.skipped,
            "năng lực chỉ đọc — không có tác động nào để ghi"))
    elif sideEffects:
        checks.append(VerificationCheck(
            "sideEffectRecorded", CheckStatus.passed,
            f"{len(sideEffects)} tác động đã ghi vào sổ"))
    else:
        checks.append(VerificationCheck(
            "sideEffectRecorded", CheckStatus.inconclusive,
            "năng lực GHI mà không khai tác động nào — thế giới có thể đã đổi "
            "mà sổ không biết"))

    return Verification(checks=tuple(checks))


def specsForProject(projectCommands: dict, requiredNames: tuple,
                    workingDirectory: Optional[str] = None,
                    timeouts: Optional[dict] = None) -> tuple:
    """Ghép lệnh thật của dự án với danh sách phép kiểm bắt buộc.

    `projectCommands` đến từ registry/projects.yaml. Khoá thiếu → `None` →
    `inconclusive`, đúng V-2: thiếu công cụ kiểm KHÔNG phải là đã kiểm.
    """
    timeouts = timeouts or {}
    return tuple(
        CheckSpec(name=name,
                  command=projectCommands.get(name),
                  timeoutSec=int(timeouts.get(name, 300)),
                  workingDirectory=workingDirectory)
        for name in requiredNames)
