#!/usr/bin/env python3
"""core.secretBroker — cấp khoá theo phạm vi, sống ngắn, và ghi sổ.

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

from .contracts import SecretRequest, newId, utcNow

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
          revokedAt  TEXT
        );
        CREATE INDEX IF NOT EXISTS secretLease_subject
          ON secretLease (subject, issuedAt);
        """
    )
    conn.commit()
    return conn


def issueLease(conn: sqlite3.Connection, request: SecretRequest,
               allowedSecretNames: tuple,
               leaseSeconds: int = DEFAULT_LEASE_SECONDS) -> SecretLease:
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
        reason=request.reason.strip())

    conn.execute(
        "INSERT INTO secretLease (leaseId, secretName, subject, projectId, "
        "reason, issuedAt, expiresAt) VALUES (?,?,?,?,?,?,?)",
        (lease.leaseId, lease.secretName, lease.subject, lease.projectId,
         lease.reason, lease.issuedAt, lease.expiresAt))
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


def auditTrail(conn: sqlite3.Connection, limit: int = 50) -> list:
    """Ai xin khoá gì, lúc nào, để làm gì.

    Đây là câu trả lời cho dòng "Which secrets were accessed?" trong danh sách
    câu hỏi mà BackOffice phải trả lời được (§30 kế hoạch).
    """
    return [dict(r) for r in conn.execute(
        "SELECT leaseId, secretName, subject, projectId, reason, issuedAt, "
        "expiresAt, revokedAt FROM secretLease ORDER BY issuedAt DESC LIMIT ?",
        (limit,))]


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
