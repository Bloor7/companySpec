#!/usr/bin/env python3
"""core.secrets — cấp khoá theo phạm vi, sống ngắn, và ghi sổ.

    Employee → Broker → Policy check → credential hẹp, sống ngắn → tiến trình

Thay cho hình cũ: một chủ thể cầm cả chùm khoá và tự quyết dùng cái nào.

═══════════════════════════════════════════════════════════════════════
P4 — SECRET KHÔNG BAO GIỜ LÀ MEMORY, KHÔNG BAO GIỜ LÀ PROMPT
═══════════════════════════════════════════════════════════════════════

Khoá không được nằm trong: memory · prompt · audit log · source code ·
employee profile · envelope.

Nên broker này KHÔNG BAO GIỜ trả về giá trị khoá cho phần suy luận. Nó trả về
một `SecretLease` — một cái phiếu mang TÊN biến môi trường và một hạn dùng.
Giá trị thật chỉ được bơm vào môi trường của TIẾN TRÌNH CON, ở
core/execution.py, đúng lúc chạy.

Khác biệt nghe nhỏ nhưng là cả vấn đề: model biết `NOTION_TOKEN` tồn tại thì
không sao; model ĐỌC ĐƯỢC giá trị của nó thì giá trị đó đã ra khỏi máy.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..contracts import SecretRequest, newId, utcNow

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # core/<goi>/ nen lui BA cap
DEFAULT_STORE = os.path.join(ROOT, "core", "secretLease.sqlite")

#: Phiếu sống bao lâu. Ngắn là có chủ ý: một phiếu sống mãi thì nó không còn
#: là phiếu, nó là cái khoá.
DEFAULT_LEASE_SECONDS = 300


class SecretDenied(PermissionError):
    """Từ chối cấp. Luôn nói RÕ vì sao — im lặng thì người ta đi tìm đường vòng."""


@dataclass
class SecretLease:
    """Cái phiếu. Mang TÊN, không mang GIÁ TRỊ."""
    secretName: str
    subject: str
    expiresAt: str
    leaseId: str = field(default_factory=lambda: newId("lse"))
    projectId: Optional[str] = None
    reason: str = ""
    issuedAt: str = field(default_factory=utcNow)

    #: Trace đã xin phiếu này. Có mặt để TÁCH lưu lượng của bộ đo ra khỏi sổ
    #: tra, không phải để che nó đi — theo đúng tiền lệ `evl_` ở `ceoRunLog`
    #: và `reg_` ở báo cáo backOffice.
    #:
    #: Một sổ "khoá nào đã bị chạm" mà 90% là dòng của `tests/run.py` thì nó
    #: vẫn đúng và vẫn vô dụng: không ai đọc nổi để tìm ra lần chạm thật.
    traceId: str = ""

    def isValidAt(self, moment: Optional[str] = None) -> bool:
        return (moment or utcNow()) < self.expiresAt

    def __repr__(self) -> str:
        """An toàn khi lỡ tay in ra log.

        Không có gì để giấu ở đây (phiếu vốn không mang giá trị), nhưng viết rõ
        để người đọc sau này không đi thêm một bước "cho tiện" là nhét giá trị
        vào dataclass này.
        """
        return (f"SecretLease({self.secretName!r} cho {self.subject!r}, "
                f"hết hạn {self.expiresAt})")


def openStore(path: str = DEFAULT_STORE) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS secretLease (
          leaseId    TEXT PRIMARY KEY,
          secretName TEXT NOT NULL,
          subject    TEXT NOT NULL,
          projectId  TEXT,
          reason     TEXT NOT NULL DEFAULT '',
          issuedAt   TEXT NOT NULL,
          expiresAt  TEXT NOT NULL,
          revokedAt  TEXT,
          traceId    TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS secretLease_subject
          ON secretLease (subject, issuedAt);
        """
    )
    # Sổ dựng trước 2026-09-20 chưa có cột `traceId`. Thêm tại chỗ, idempotent
    # — không thêm thì `issueLease` ném OperationalError ở lời gọi đầu tiên
    # sau khi cập nhật, tức là cửa vào sập vì một cột thiếu (O8).
    if "traceId" not in {row[1] for row in
                         conn.execute("PRAGMA table_info(secretLease)")}:
        conn.execute("ALTER TABLE secretLease ADD COLUMN traceId TEXT "
                     "NOT NULL DEFAULT ''")
    conn.commit()
    return conn


def issueLease(conn: sqlite3.Connection, request: SecretRequest,
               allowedSecretNames: tuple,
               leaseSeconds: int = DEFAULT_LEASE_SECONDS,
               traceId: str = "") -> SecretLease:
    """Cấp phiếu — hoặc từ chối và nói rõ vì sao.

    `allowedSecretNames` do NGƯỜI GỌI tra từ manifest/employee rồi đưa vào.
    core/ không tự đọc file company (W3′), và quan trọng hơn: danh sách phải
    đến từ ĐĨA, không từ envelope — model không nới được (G3).
    """
    if not request.reason.strip():
        # Cấp khoá mà không nói để làm gì thì sổ ghi lại cũng vô dụng: sáu
        # tháng sau không ai trả lời được "lần đó lấy khoá để làm gì".
        raise SecretDenied(
            f"`{request.subject}` xin `{request.secretName}` mà không nói lý "
            "do. Sổ không có lý do là sổ không tra được.")

    if request.secretName not in allowedSecretNames:
        raise SecretDenied(
            f"`{request.subject}` KHÔNG được cấp `{request.secretName}`. "
            f"Chỉ được: {', '.join(sorted(allowedSecretNames)) or '(không gì cả)'}. "
            "Không khai = không có (PM-1).")

    expiresAt = (datetime.now(timezone.utc) + timedelta(seconds=leaseSeconds)
                 ).strftime("%Y-%m-%dT%H:%M:%SZ")
    lease = SecretLease(
        secretName=request.secretName, subject=request.subject,
        expiresAt=expiresAt, projectId=request.projectId,
        reason=request.reason.strip(), traceId=traceId)

    conn.execute(
        "INSERT INTO secretLease (leaseId, secretName, subject, projectId, "
        "reason, issuedAt, expiresAt, traceId) VALUES (?,?,?,?,?,?,?,?)",
        (lease.leaseId, lease.secretName, lease.subject, lease.projectId,
         lease.reason, lease.issuedAt, lease.expiresAt, lease.traceId))
    conn.commit()
    return lease


def revoke(conn: sqlite3.Connection, leaseId: str) -> None:
    conn.execute("UPDATE secretLease SET revokedAt = ? WHERE leaseId = ?",
                 (utcNow(), leaseId))
    conn.commit()


def activeLeases(conn: sqlite3.Connection,
                 moment: Optional[str] = None) -> list:
    moment = moment or utcNow()
    return [dict(r) for r in conn.execute(
        "SELECT * FROM secretLease WHERE revokedAt IS NULL AND expiresAt > ? "
        "ORDER BY issuedAt DESC", (moment,))]


def resolveForProcess(leases: tuple, environment: dict,
                      moment: Optional[str] = None) -> dict:
    """Biến phiếu thành biến môi trường THẬT, đúng lúc chạy tiến trình con.

    Đây là NƠI DUY NHẤT giá trị khoá được chạm tới, và nó nằm ngoài mọi đường
    đi của prompt. Phiếu hết hạn thì bỏ qua — im lặng, vì phiếu hết hạn là
    chuyện bình thường, không phải lỗi.
    """
    moment = moment or utcNow()
    resolved = {}
    for lease in leases:
        if not lease.isValidAt(moment):
            continue
        if lease.secretName in environment:
            resolved[lease.secretName] = environment[lease.secretName]
    return resolved


#: Tiền tố trace của bộ đo. Cùng danh sách với `core.audit.TEST_TRACE_PREFIXES`
#: — KHÔNG import về để `core.secrets` không phụ thuộc `core.audit` cho một
#: hằng; nhưng chúng phải khớp, và ca thử ép chúng khớp.
TEST_TRACE_PREFIXES = ("reg_", "evl_", "e2e_", "demo_", "drl_")


def auditTrail(conn: sqlite3.Connection, limit: int = 50,
               includeTestTraffic: bool = False) -> list:
    """Ai xin khoá gì, lúc nào, để làm gì.

    Đây là câu trả lời cho dòng "Which secrets were accessed?" trong danh sách
    câu hỏi mà BackOffice phải trả lời được (§30 kế hoạch).

    Mặc định BỎ lưu lượng của bộ đo. Mỗi lần chạy `tests/run.py` đi qua hơn 80
    năng lực, nên không lọc thì sổ này gần như toàn dòng `reg_` và câu hỏi
    "khoá nào đã bị chạm" trở thành không trả lời nổi — sổ vẫn đúng, và vẫn
    vô dụng.

    KHÔNG che hẳn: `includeTestTraffic=True` lấy đủ. Bộ đo tự xoá dấu vết của
    mình là bộ đo không kiểm được — tiền lệ `evl_` ở `ceoRunLog` đã chốt điều
    đó một lần rồi.
    """
    columns = ("SELECT leaseId, secretName, subject, projectId, reason, "
               "issuedAt, expiresAt, revokedAt, traceId FROM secretLease")
    if includeTestTraffic:
        # sql-an-toan: chỉ ghép `columns` viết cứng ngay trên; giá trị qua `?`
        return [dict(r) for r in conn.execute(
            f"{columns} ORDER BY issuedAt DESC LIMIT ?", (limit,))]

    # sql-an-toan: chỉ ghép `notTest` dựng từ hằng viết cứng; giá trị qua `?`
    notTest = " AND ".join(f"traceId NOT LIKE '{prefix}%'"
                           for prefix in TEST_TRACE_PREFIXES)
    return [dict(r) for r in conn.execute(
        f"{columns} WHERE {notTest} ORDER BY issuedAt DESC LIMIT ?", (limit,))]


#: Giữ phiếu ĐÃ HẾT HẠN của bộ đo bao lâu trước khi dọn.
#:
#: Một lượt `tests/run.py` đẻ ~190 phiếu. Không dọn thì sổ phình đúng kiểu
#: `taskLog` của cron từng phình — đo 01/09, cron chiếm 61% số dòng sau MỘT
#: ngày. Không tốn tiền, nhưng làm mọi câu truy vấn nhiễu đi.
GIU_NGAY_PHIEU_CA_THU = 2


def prune(conn: sqlite3.Connection, keepDays: int = GIU_NGAY_PHIEU_CA_THU,
          now: Optional[str] = None) -> int:
    """Dọn phiếu CỦA BỘ ĐO đã hết hạn từ lâu. Trả về số dòng đã xoá.

    BA HÀNG RÀO, mỗi cái chặn một cách hỏng — cùng hình với `don_dong_cron`:

    · chỉ tiền tố của bộ đo. Phiếu THẬT không bao giờ bị dọn: sổ này là câu
      trả lời cho §30 "khoá nào đã bị chạm", và một câu trả lời tự xoá mình
      sau vài ngày thì không phải câu trả lời.
    · chỉ phiếu ĐÃ HẾT HẠN. Phiếu còn hạn có thể đang được dùng.
    · chỉ cũ hơn `keepDays`, để còn soi được lượt chạy hôm qua.

    Trả về số dòng để chỗ gọi IN RA. Dọn im lặng thì có ngày nó dọn nhầm mà
    không ai biết.
    """
    now = now or utcNow()
    cutoff = (datetime.strptime(now[:19], "%Y-%m-%dT%H:%M:%S")
              - timedelta(days=keepDays)).strftime("%Y-%m-%dT%H:%M:%SZ")
    # sql-an-toan: chỉ ghép `isTest` dựng từ hằng viết cứng; giá trị qua `?`
    isTest = " OR ".join(f"traceId LIKE '{prefix}%'"
                         for prefix in TEST_TRACE_PREFIXES)
    removed = conn.execute(
        f"DELETE FROM secretLease WHERE ({isTest}) AND expiresAt < ?",
        (cutoff,)).rowcount
    conn.commit()
    return removed


def redact(text: str, environment: Optional[dict] = None) -> str:
    """Xoá mọi giá trị secret đã biết khỏi một đoạn chữ TRƯỚC khi ghi log.

    Lớp cuối cùng. Không thay được P4 — nếu phải dùng tới nó thì đã có chỗ rò
    ở trên rồi. Nhưng lớp cuối vẫn phải có, vì "đã có chỗ rò ở trên" là câu
    người ta chỉ nói được SAU KHI khoá đã nằm trong log.
    """
    environment = os.environ if environment is None else environment
    cleaned = text
    for name, value in environment.items():
        if not value or len(value) < 12:
            continue
        if not _looksSecretName(name):
            continue
        cleaned = cleaned.replace(value, f"<đã ẩn:{name}>")
    return cleaned


def _looksSecretName(name: str) -> bool:
    upper = name.upper()
    return any(mark in upper for mark in
               ("TOKEN", "KEY", "SECRET", "PASSWORD", "CREDENTIAL", "_PAT"))
