#!/usr/bin/env python3
"""core.memory — trí nhớ phân tầng, có nhãn, có ngày rụng.

═══════════════════════════════════════════════════════════════════════
BA LUẬT, MỖI LUẬT LÀ HOÁ ĐƠN CỦA MỘT LẦN HỎNG
═══════════════════════════════════════════════════════════════════════

M-1 — KHÔNG BIẾN SUY ĐOÁN THÀNH SỰ THẬT.
  Hỏi hội đồng "chiến lược kênh YouTube" thì mấy model tuôn ra "kênh mới cần
  90 ngày thoát sandbox", "nghiên cứu Tubics: 73% kênh triệu view dùng giọng
  AI" — nghe như tri thức, thật ra là văn mẫu. Chúng học từ cùng một mớ chữ
  nên sai giống nhau, và ba lần đoán biến thành một lần "đồng thuận".
  Nên `inference` BẮT BUỘC có `confidence` + `source`, và người đọc phải phân
  biệt được nó với `fact` mà không cần hỏi ai.

M-2 — THỨ CHỈ ĐÚNG TRONG MỘT QUÃNG PHẢI CÓ NGÀY RỤNG.
  Admin nói một hoàn cảnh đang diễn ra (đang yêu, đang trông khách sạn thay
  người) — không phải cảm giác một ngày, cũng không phải điều luôn đúng. Hồ sơ
  cũ chỉ có ngăn cho điều VĨNH VIỄN nên từ chối, và phiên sau CEO trắng.
  Cất mà không hẹn ngày hết còn TỆ HƠN không cất: nó nạp vào mọi lượt và không
  bao giờ tự hết hạn.

M-3 — SECRET KHÔNG BAO GIỜ LÀ MEMORY.
  Có một phép soát bằng code ở dưới (`looksLikeSecret`), không chỉ một lời dặn.
"""
from __future__ import annotations

import os
import re
import sqlite3
from typing import Optional

from .contracts import MemoryItem, MemoryKind, MemoryTier, newId, utcNow

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_STORE = os.path.join(ROOT, "core", "memory.sqlite")

#: Dấu hiệu một chuỗi là KHOÁ chứ không phải trí nhớ.
#:
#: Không hòng bắt hết — bắt hết là bất khả. Nó bắt những hình dạng THẬT SỰ hay
#: bị dán nhầm vào: token nhà cung cấp, chuỗi base64 dài, dòng `KEY=value`.
#: Bắt được một lần là đáng, vì một khoá lọt vào trí nhớ sẽ đi theo mọi prompt
#: về sau, sang mọi nhà cung cấp, và không có cách nào gọi nó về.
SECRET_SHAPES = (
    re.compile(r"\b(sk|pk|ghp|gho|ghs|xox[baprs])[-_][A-Za-z0-9_-]{16,}"),
    re.compile(r"\bntn_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{30,}"),
    re.compile(r"\b[A-Z][A-Z0-9_]{6,}\s*=\s*\S{12,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),  # JWT
)


class SecretInMemoryError(ValueError):
    """P4 — chặn ở cửa vào, không dọn ở cửa ra."""


class MemoryValidationError(ValueError):
    """Mẩu nhớ khai sai. Ném ra chứ không nuốt (O10)."""


def looksLikeSecret(text: str) -> bool:
    return any(shape.search(text) for shape in SECRET_SHAPES)


# ══════════════════════════ sổ ══════════════════════════

def openStore(path: str = DEFAULT_STORE) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS memoryItem (
          memoryId    TEXT PRIMARY KEY,
          tier        TEXT NOT NULL,
          kind        TEXT NOT NULL,
          content     TEXT NOT NULL,
          source      TEXT NOT NULL DEFAULT '',
          confidence  REAL,
          scopeId     TEXT NOT NULL DEFAULT '',
          createdAt   TEXT NOT NULL,
          expiresAt   TEXT,
          supersededBy TEXT
        );
        CREATE INDEX IF NOT EXISTS memoryItem_tier
          ON memoryItem (tier, scopeId, createdAt);
        """
    )
    conn.commit()
    return conn


def remember(conn: sqlite3.Connection, item: MemoryItem,
             scopeId: str = "") -> MemoryItem:
    """Cất một mẩu nhớ. Soát TRƯỚC khi ghi.

    `scopeId` là "của ai / của dự án nào": projectId với projectMemory,
    employeeId với employeeMemory. Không có nó thì trí nhớ của hai dự án trộn
    vào nhau và không ai gỡ ra được.
    """
    errors = item.validate()
    if errors:
        raise MemoryValidationError("; ".join(errors))

    # M-3 — chặn ở CỬA VÀO. Dọn ở cửa ra thì đã muộn: một khoá lọt vào đây sẽ
    # đi theo mọi prompt về sau và không gọi về được.
    if looksLikeSecret(item.content):
        raise SecretInMemoryError(
            "Nội dung trông như một KHOÁ/TOKEN. Secret không bao giờ là "
            "Memory (P4) — cất tên biến môi trường, đừng cất giá trị.")

    if item.tier in _SCOPED_TIERS and not scopeId:
        raise MemoryValidationError(
            f"tier `{item.tier.value}` phải có scopeId (của ai / dự án nào), "
            "không thì trí nhớ hai nơi trộn vào nhau.")

    conn.execute(
        "INSERT INTO memoryItem (memoryId, tier, kind, content, source, "
        "confidence, scopeId, createdAt, expiresAt) VALUES (?,?,?,?,?,?,?,?,?)",
        (item.memoryId, item.tier.value, item.kind.value, item.content,
         item.source, item.confidence, scopeId, item.createdAt, item.expiresAt))
    conn.commit()
    return item


_SCOPED_TIERS = (MemoryTier.project, MemoryTier.employee)


def recall(conn: sqlite3.Connection, tier: MemoryTier, scopeId: str = "",
           kinds: tuple = (), limit: int = 50,
           now: Optional[str] = None) -> list:
    """Đọc lại. KHÔNG trả về thứ đã hết hạn (M-2).

    Hết hạn thì im lặng biến mất khỏi kết quả, nhưng vẫn nằm trong sổ: xoá
    ngay thì mất dấu vết "hệ từng tin điều này", và đó là thứ cần khi đi lần
    ngược một quyết định cũ.
    """
    now = now or utcNow()
    sql = ["SELECT * FROM memoryItem WHERE tier = ?",
           "AND (expiresAt IS NULL OR expiresAt > ?)",
           "AND supersededBy IS NULL"]
    params = [tier.value, now]
    if scopeId:
        sql.append("AND scopeId = ?")
        params.append(scopeId)
    if kinds:
        sql.append("AND kind IN (%s)" % ",".join("?" * len(kinds)))
        params.extend(k.value for k in kinds)
    sql.append("ORDER BY createdAt DESC LIMIT ?")
    params.append(int(limit))

    return [_toItem(row) for row in conn.execute(" ".join(sql), params)]


def supersede(conn: sqlite3.Connection, oldMemoryId: str,
              newItem: MemoryItem, scopeId: str = "") -> MemoryItem:
    """Thay một mẩu nhớ bằng mẩu mới, GIỮ cái cũ.

    Xoá thẳng thì mất câu trả lời cho "trước đây hệ tin gì, và đổi ý lúc nào".
    Một quyết định cũ đọc lại được là thứ phân biệt trí nhớ với một cái bảng
    trắng bị ghi đè.
    """
    remember(conn, newItem, scopeId)
    conn.execute("UPDATE memoryItem SET supersededBy = ? WHERE memoryId = ?",
                 (newItem.memoryId, oldMemoryId))
    conn.commit()
    return newItem


def expiringSoon(conn: sqlite3.Connection, withinDays: int = 7,
                 now: Optional[str] = None) -> list:
    """Sắp rụng — để hỏi lại admin còn đúng không, TRƯỚC khi nó im lặng biến mất.

    Không có bước này thì M-2 sửa một lỗi (nhớ mãi thứ đã sai) bằng cách tạo
    một lỗi khác (quên mất thứ vẫn đúng).
    """
    from datetime import datetime, timedelta, timezone
    now = now or utcNow()
    horizon = (datetime.now(timezone.utc) + timedelta(days=withinDays)
               ).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = conn.execute(
        "SELECT * FROM memoryItem WHERE expiresAt IS NOT NULL "
        "AND expiresAt > ? AND expiresAt <= ? AND supersededBy IS NULL "
        "ORDER BY expiresAt", (now, horizon))
    return [_toItem(row) for row in rows]


def summariseForPrompt(items: list, maxChars: int = 2000) -> str:
    """Gói trí nhớ thành chữ để nhét vào prompt, CÓ NHÃN.

    Nhãn không phải trang trí: model đọc `[suy đoán · 0.6]` thì biết đó không
    phải thứ để khẳng định với admin. Bỏ nhãn đi là mời nó nói suy đoán bằng
    giọng của sự thật — đúng lỗi hội đồng từng mắc.
    """
    label = {MemoryKind.fact: "sự thật",
             MemoryKind.decision: "đã quyết",
             MemoryKind.inference: "suy đoán"}
    lines, used = [], 0
    for item in items:
        mark = label[item.kind]
        if item.kind is MemoryKind.inference:
            mark += f" · {item.confidence:.1f}"
            if item.source:
                mark += f" · nguồn: {item.source}"
        line = f"- [{mark}] {item.content}"
        if used + len(line) > maxChars:
            lines.append(f"- (còn nữa, đã cắt ở {maxChars} ký tự)")
            break
        lines.append(line)
        used += len(line)
    return "\n".join(lines)


def _toItem(row: sqlite3.Row) -> MemoryItem:
    return MemoryItem(
        tier=MemoryTier(row["tier"]),
        kind=MemoryKind(row["kind"]),
        content=row["content"],
        memoryId=row["memoryId"],
        source=row["source"] or "",
        confidence=row["confidence"],
        createdAt=row["createdAt"],
        expiresAt=row["expiresAt"],
    )


def newFact(tier: MemoryTier, content: str, source: str = "") -> MemoryItem:
    return MemoryItem(tier=tier, kind=MemoryKind.fact, content=content,
                      source=source, memoryId=newId("mem"))


def newDecision(tier: MemoryTier, content: str, source: str = "") -> MemoryItem:
    return MemoryItem(tier=tier, kind=MemoryKind.decision, content=content,
                      source=source, memoryId=newId("mem"))


def newInference(tier: MemoryTier, content: str, confidence: float,
                 source: str) -> MemoryItem:
    """Suy đoán. `confidence` và `source` là BẮT BUỘC, ép ngay ở chữ ký hàm."""
    return MemoryItem(tier=tier, kind=MemoryKind.inference, content=content,
                      confidence=confidence, source=source,
                      memoryId=newId("mem"))
