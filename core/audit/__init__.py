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

from ..contracts import AuditEntry, Execution, PolicyOutcome, Task, utcNow

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # core/<goi>/ nen lui BA cap
DEFAULT_STORE = os.path.join(ROOT, "backOffice", "store.sqlite")

#: Cột thêm vào `taskLog`. Tên → kiểu SQLite.
#:
#: Thứ tự trong dict là thứ tự thêm; thêm cột mới thì nối vào CUỐI, đừng chèn
#: giữa — sqlite không quan tâm, nhưng người đọc diff thì có.
#: Nhãn traceId của lời gọi do BỘ ĐO sinh ra, không phải việc thật của admin.
#:
#: `trc_` KHÔNG nằm ở đây: đó là tiền tố mặc định của mọi lời gọi thật. Bộ đo
#: nào còn dùng `trc_` thì phải tự đặt nhãn cho mình — xem `tests/evals/`.
TEST_TRACE_PREFIXES = ("reg_", "evl_", "e2e_", "demo_")

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


def policyColumnFloor(conn: sqlite3.Connection) -> Optional[str]:
    """Mốc cột `policyDecision` bắt đầu có nghĩa — SUY TỪ DỮ LIỆU.

    Dòng đầu tiên CÓ quyết định là lúc cột ra đời. Viết cứng ngày thì sang năm
    nó vẫn đúng một cách tình cờ, rồi có ngày sai mà không ai biết.
    """
    return conn.execute(
        "SELECT MIN(startedAt) FROM taskLog WHERE policyDecision IS NOT NULL"
    ).fetchone()[0]


def unexplainedCalls(conn: sqlite3.Connection, since: str,
                     limit: int = 50) -> list:
    """Lời gọi KHÔNG có quyết định policy nào kèm theo.

    Rỗng là điều ta muốn. Không rỗng nghĩa là có đường đi vào hệ mà không qua
    Policy — và một đường như thế là thứ nguy hiểm nhất có thể tồn tại ở đây.

    ⚠ CHỈ ĐẾM TỪ LÚC CỘT ẤY TỒN TẠI. Dòng ghi trước ngày thêm cột
    `policyDecision` vốn KHÔNG THỂ có giá trị — đếm chúng là báo động về quá
    khứ. Bản đầu không có sàn này và `travis health` kêu "10 lời gọi không qua
    cửa" về những dòng chỉ đơn giản là cũ hơn cái cột.

    Một cảnh báo đúng luật nhưng sai chỗ thì cũng dạy người ta bỏ qua cảnh
    báo — hệt như 21 tin giống hệt lúc nửa đêm.
    """
    floor = policyColumnFloor(conn)
    if floor is None:
        # Chưa dòng nào có quyết định → cột vừa thêm, chưa chạy lần nào.
        # KHÔNG phải "tất cả đều lọt cửa".
        return []
    # Bỏ lời gọi của BỘ ĐO: bộ ca thử dùng một dispatcher GIẢ
    # (`tests/evals/shim/`) vốn không ghi quyết định policy — đó là chủ ý, nó
    # không phải cổng thật. Đếm chúng là báo động về chính cái thước.
    #
    # sql-an-toan: chỉ ghép `notTest`, dựng từ hằng TEST_TRACE_PREFIXES viết
    # cứng trong file này; mọi giá trị vẫn đi qua tham số `?`.
    notTest = " AND ".join(f"traceId NOT LIKE '{prefix}%'"
                           for prefix in TEST_TRACE_PREFIXES)
    # sql-an-toan: chỉ ghép `notTest` dựng từ hằng viết cứng; giá trị qua `?`
    return [dict(r) for r in conn.execute(
        "SELECT taskId, companyId, capability, status, startedAt "
        f"FROM taskLog WHERE startedAt >= ? AND policyDecision IS NULL "
        f"AND {notTest} ORDER BY startedAt DESC LIMIT ?",
        (max(since, floor), limit))]


def trackRecordRows(conn: sqlite3.Connection, companyId: str,
                    capability: str, limit: int = 200) -> list:
    """Lịch sử của một năng lực, cho core.policy.autonomy tính mức.

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
