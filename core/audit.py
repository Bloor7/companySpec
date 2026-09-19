#!/usr/bin/env python3
"""core.audit — sổ không sửa được: ai làm gì, và VÌ SAO nó được phép.

§30 kế hoạch liệt kê những câu BackOffice phải trả lời được:

    Travis đang làm gì · đã làm gì · cái gì hỏng · vì sao hỏng · ai làm ·
    dùng bộ não nào · tốn bao nhiêu · chạm secret nào · đổi những gì ·
    đã kiểm chứng chưa · VÌ SAO NÓ ĐƯỢC PHÉP

Câu cuối là câu bản cũ không trả lời được: `taskLog` ghi `status` nhưng không
ghi quyết định của Policy hay lý do. Nên "vì sao lời gọi này chạy được" phải
đi đọc lại code — mà code thì đã đổi từ lúc đó.

═══════════════════════════════════════════════════════════════════════
DI TRÚ THÊM CỘT, KHÔNG ĐỔI BẢNG
═══════════════════════════════════════════════════════════════════════

`backOffice/store.sqlite` đang có dữ liệu thật của nhiều tháng và đang được
`ops/`, `backOffice/` đọc. Nên: chỉ THÊM cột (`ALTER TABLE ADD COLUMN`), không
đổi tên, không xoá. Mọi cột mới đều cho phép NULL — dòng cũ không có dữ liệu
đó, và giả vờ rằng có là nói dối về quá khứ.
"""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Optional

from .contracts import AuditEntry, Execution, PolicyOutcome, Task, utcNow

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_STORE = os.path.join(ROOT, "backOffice", "store.sqlite")

#: Cột thêm vào `taskLog`. Tên → kiểu SQLite.
#:
#: Thứ tự trong dict là thứ tự thêm; thêm cột mới thì nối vào CUỐI, đừng chèn
#: giữa — sqlite không quan tâm, nhưng người đọc diff thì có.
ADDED_COLUMNS = {
    "policyDecision": "TEXT",
    "policyReason": "TEXT",
    "employeeId": "TEXT",
    "brainId": "TEXT",
    "verificationJson": "TEXT",
    "paidVnd": "REAL",
}


def openStore(path: str = DEFAULT_STORE) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> list:
    """Thêm cột còn thiếu. Idempotent — chạy bao nhiêu lần cũng được.

    Trả về danh sách cột vừa thêm, để người gọi biết có gì đổi. Trả về rỗng
    KHÔNG phải là lỗi, đó là trường hợp thường gặp nhất.
    """
    existing = {row[1] for row in conn.execute("PRAGMA table_info(taskLog)")}
    added = []
    for column, columnType in ADDED_COLUMNS.items():
        if column in existing:
            continue
        # Không `NOT NULL`, không `DEFAULT`: dòng cũ KHÔNG có dữ liệu này, và
        # điền một giá trị mặc định vào là bịa ra quá khứ. NULL nói đúng sự
        # thật — "không biết" (O10).
        #
        # Tên cột và kiểu KHÔNG tham số hoá được: sqlite chỉ nhận `?` ở vị trí
        # GIÁ TRỊ. Cả hai lấy từ hằng `ADDED_COLUMNS` viết cứng ngay trong file
        # này — không có đường nào cho dữ liệu ngoài đi vào đây.
        # sql-an-toan: tên cột lấy từ hằng ADDED_COLUMNS viết cứng trong file
        conn.execute(f"ALTER TABLE taskLog ADD COLUMN {column} {columnType}")
        added.append(column)
    if added:
        conn.commit()
    return added


def recordDecision(conn: sqlite3.Connection, task: Task,
                   outcome: PolicyOutcome) -> None:
    """Ghi quyết định NGAY khi có, trước cả khi chạy.

    A-1 — lần bị CHẶN cũng là dữ liệu (O5). Chờ tới lúc chạy xong mới ghi thì
    mọi lời gọi bị từ chối sẽ không để lại dòng nào, và "vì sao hệ không làm
    việc đó" thành câu không tra được.
    """
    conn.execute(
        "UPDATE taskLog SET policyDecision = ?, policyReason = ?, "
        "employeeId = ? WHERE taskId = ?",
        (outcome.decision.value, outcome.reason, task.employeeId,
         task.taskId))
    conn.commit()


def recordExecution(conn: sqlite3.Connection, execution: Execution) -> None:
    """Ghi kết quả một lần chạy, KÈM bằng chứng."""
    verificationJson = None
    if execution.verification is not None:
        verificationJson = json.dumps(execution.verification.toDict(),
                                      ensure_ascii=False)
    conn.execute(
        "UPDATE taskLog SET status = ?, summary = ?, finishedAt = ?, "
        "durationMs = ?, costUsd = ?, paidVnd = ?, brainId = ?, "
        "verificationJson = ? WHERE taskId = ?",
        (execution.status.value, execution.summary, execution.finishedAt
         or utcNow(), execution.durationMs, execution.costUsd,
         execution.paidVnd, execution.brainId, verificationJson,
         execution.taskId))
    conn.commit()


def whyWasThisAllowed(conn: sqlite3.Connection, taskId: str) -> Optional[dict]:
    """Câu trả lời cho "vì sao lời gọi này được phép", sau nhiều tuần.

    Đây là lý do cả module này tồn tại. Không có nó thì mỗi lần nghi ngờ lại
    phải đọc lại code — mà code đã đổi từ lúc đó rồi.
    """
    row = conn.execute(
        "SELECT taskId, traceId, companyId, capability, riskTier, status, "
        "policyDecision, policyReason, employeeId, brainId, verificationJson, "
        "startedAt, finishedAt, costUsd, paidVnd "
        "FROM taskLog WHERE taskId = ?", (taskId,)).fetchone()
    if row is None:
        return None
    answer = dict(row)
    if answer.get("verificationJson"):
        try:
            answer["verification"] = json.loads(answer["verificationJson"])
        except json.JSONDecodeError:
            answer["verification"] = {"status": "sổ hỏng, không đọc được"}
    answer.pop("verificationJson", None)
    return answer


def unexplainedCalls(conn: sqlite3.Connection, since: str,
                     limit: int = 50) -> list:
    """Lời gọi KHÔNG có quyết định policy nào kèm theo.

    Rỗng là điều ta muốn. Không rỗng nghĩa là có đường đi vào hệ mà không qua
    Policy — và một đường như thế là thứ nguy hiểm nhất có thể tồn tại ở đây.

    Dòng cũ (trước khi thêm cột) cũng hiện ra, nên `since` phải đặt sau mốc di
    trú; bằng không ta đi tìm một vấn đề không có thật.
    """
    return [dict(r) for r in conn.execute(
        "SELECT taskId, companyId, capability, status, startedAt "
        "FROM taskLog WHERE startedAt >= ? AND policyDecision IS NULL "
        "ORDER BY startedAt DESC LIMIT ?", (since, limit))]


def trackRecordRows(conn: sqlite3.Connection, companyId: str,
                    capability: str, limit: int = 200) -> list:
    """Lịch sử của một năng lực, cho core.autonomy tính mức.

    Chỉ trả về dòng ĐÃ CÓ quyết định policy: dòng cũ hơn mốc di trú không có
    `verificationJson`, và đếm chúng như thành công là trao quyền dựa trên một
    quá khứ ta không đo được.
    """
    rows = conn.execute(
        "SELECT status, verificationJson, startedAt FROM taskLog "
        "WHERE companyId = ? AND capability = ? AND policyDecision IS NOT NULL "
        "ORDER BY startedAt DESC LIMIT ?", (companyId, capability, limit))
    return [{"status": r["status"], "createdAt": r["startedAt"],
             "isReversible": None} for r in rows]


def entryFrom(task: Task, outcome: PolicyOutcome,
              execution: Optional[Execution] = None) -> AuditEntry:
    """Gói một dòng audit đầy đủ — dùng khi cần xuất ra ngoài sqlite."""
    return AuditEntry(
        taskId=task.taskId,
        traceId=task.traceId,
        companyId=task.companyId,
        capability=task.capability,
        riskTier=task.riskTier,
        policyDecision=outcome.decision,
        policyReason=outcome.reason,
        status=execution.status if execution else task.status,
        inputHash=task.fingerprint,
        employeeId=task.employeeId,
        brainId=execution.brainId if execution else None,
        costUsd=execution.costUsd if execution else 0.0,
        paidVnd=execution.paidVnd if execution else 0.0,
        durationMs=execution.durationMs if execution else 0,
    )
