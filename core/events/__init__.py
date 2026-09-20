#!/usr/bin/env python3
"""core.events — Travis thôi chờ bị gõ.

Hôm nay hệ chỉ có hai cửa vào: admin nhắn, hoặc cron tới giờ chạy một việc cố
định. Hệ quả: nó KHÔNG BAO GIỜ tự phát hiện vấn đề.

Bằng chứng đắt nhất cho điều đó: hai ngày admin về quê, Windows CÓ bật, Task
Scheduler CÓ chạy, mọi thứ báo xanh — và hệ chết 61 giờ. Không một dòng lỗi.
Không ai hỏi "sao hai ngày rồi không có tin nào".

═══════════════════════════════════════════════════════════════════════
EV-1 — EVENT ĐỀ XUẤT TASK, KHÔNG CẤP QUYỀN CHO TASK
═══════════════════════════════════════════════════════════════════════

Task do event đẻ ra đi qua ĐÚNG cánh cửa Policy như mọi Task khác. Cụ thể:
`scheduledTrigger` và `eventTrigger` vẫn chỉ được ĐỌC (S3), trừ khi cầm phiếu
hẹn admin đã ký.

Viết ngược lại — "hệ tự phát hiện thì hệ tự sửa luôn" — là cách một con cron
lúc 3 giờ sáng ghi nhầm vào sổ tiền của admin, và không có ai thức để thấy.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..contracts import Event, EventKind, IssuedBy, RiskTier, newId, utcNow

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # core/<goi>/ nen lui BA cap
DEFAULT_STORE = os.path.join(ROOT, "core", "event.sqlite")


@dataclass
class TaskProposal:
    """Thứ một event đẻ ra. CHÚ Ý: đây là ĐỀ XUẤT, chưa phải Task.

    Nó không mang theo quyền nào. Ai biến nó thành Task thật thì vẫn phải đưa
    qua core.policy như một lời gọi bình thường.
    """
    companyId: str
    capability: str
    inputValue: dict
    reason: str
    issuedBy: IssuedBy = IssuedBy.eventTrigger
    proposalId: str = field(default_factory=lambda: newId("prp"))
    createdAt: str = field(default_factory=utcNow)


@dataclass
class Rule:
    """Gặp event loại này thì đề xuất gì."""
    name: str
    eventKind: EventKind
    propose: Callable          # (Event) -> tuple[TaskProposal]
    description: str = ""


class EventBus:
    """Nhận event, chạy luật, trả ra ĐỀ XUẤT. Không thi hành gì."""

    def __init__(self):
        self._rules: list = []

    def register(self, rule: Rule) -> None:
        self._rules.append(rule)

    def rulesFor(self, kind: EventKind) -> tuple:
        return tuple(r for r in self._rules if r.eventKind is kind)

    def dispatch(self, event: Event) -> tuple:
        """Chạy mọi luật khớp. Một luật hỏng KHÔNG được làm chết cả bus.

        Nếu một luật ném ngoại lệ thì những luật còn lại vẫn phải chạy — bằng
        không một luật viết ẩu sẽ làm câm toàn bộ khả năng tự phát hiện, và
        cái câm đó im lặng (O8, cùng họ với "cửa vào không được sập").
        """
        proposals = []
        for rule in self.rulesFor(event.kind):
            try:
                proposals.extend(rule.propose(event) or ())
            except Exception as exc:
                proposals.append(TaskProposal(
                    companyId="", capability="", inputValue={},
                    reason=f"LUẬT `{rule.name}` HỎNG: "
                           f"{type(exc).__name__}: {exc}"))
        return tuple(proposals)


# ══════════════════════════ chống nhắn lặp ══════════════════════════

def decideNotification(previousStatus: Optional[str], currentStatus: str,
                       consecutiveFailures: int = 0) -> dict:
    """LUẬT chống nhắn lặp, dạng hàm THUẦN. Không sổ, không trạng thái.

    ═══ VÌ SAO TÁCH RA KHỎI `NotificationThrottle` ═══

    `core/events/scheduler.py` đã có bản của riêng nó, và bản đó tốt hơn ở một điểm:
    nó suy trạng thái từ bảng `scheduleRun` vốn đã phải ghi, nên không có
    trạng thái thứ hai để lệch. Còn `NotificationThrottle` giữ bảng riêng, hợp
    với nguồn không có sẵn lịch sử.

    Hai cách lưu, nhưng phải MỘT LUẬT. Hai bản của cùng một luật là cách nó
    lệch đi — đúng vụ "hạn mức ăn uống" ra hai con số mà cả hai đều không lỗi.

    Nên luật sống ở đây; cả hai bên chỉ đưa dữ liệu vào rồi đọc câu trả lời.

    Trả về `action`:
      notify         — lần đầu hỏng, nhắn
      suppress       — đang lặp, im (VẪN GHI SỔ — im lặng khác nuốt lỗi, O10)
      notifyRecovery — vừa khỏi, báo KÈM số lần đã hỏng
      silent         — bình thường, không có gì để nói
    """
    failedNow = currentStatus == "failed"
    failedBefore = previousStatus == "failed"

    if failedNow and failedBefore:
        return {"action": "suppress", "occurrences": consecutiveFailures + 1}
    if failedNow:
        return {"action": "notify", "occurrences": 1}
    if failedBefore:
        # "Đã khỏi" một mình không nói lên gì; "đã khỏi sau 21 lần hỏng trong
        # 6 tiếng" nói rằng có thứ cần sửa tận gốc.
        return {"action": "notifyRecovery", "occurrences": consecutiveFailures}
    return {"action": "silent", "occurrences": 0}


class NotificationThrottle:
    """Lỗi hạ tầng lặp lại thì nhắn MỘT lần, khỏi thì báo kèm số lần.

    Bản CÓ SỔ RIÊNG, cho nguồn không có sẵn lịch sử. Luật nằm ở
    `decideNotification` — lớp này chỉ lo phần nhớ.

    BÀI HỌC (bảng bẫy): cron 15 phút/lần × sự cố 6 tiếng = 21 tin giống hệt
    lúc nửa đêm. Hệ quả không phải phiền — hệ quả là admin HỌC CÁCH BỎ QUA
    thông báo, và lần sau có tin thật thì cũng trôi luôn.

    Ba câu trả lời, khác hẳn nhau:
      · shouldNotify  → lần đầu, nhắn
      · suppressed    → đang lặp, im
      · recovered     → vừa khỏi, báo kèm ĐÃ LẶP BAO NHIÊU LẦN
    """

    def __init__(self, connection: sqlite3.Connection):
        self.conn = connection
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS incident (
              fingerprint TEXT PRIMARY KEY,
              occurrences INTEGER NOT NULL,
              firstSeenAt TEXT NOT NULL,
              lastSeenAt  TEXT NOT NULL,
              notifiedAt  TEXT
            );
            """
        )
        self.conn.commit()

    def onFailure(self, fingerprint: str) -> dict:
        row = self.conn.execute(
            "SELECT * FROM incident WHERE fingerprint = ?",
            (fingerprint,)).fetchone()
        now = utcNow()
        if row is None:
            self.conn.execute(
                "INSERT INTO incident (fingerprint, occurrences, firstSeenAt, "
                "lastSeenAt, notifiedAt) VALUES (?,?,?,?,?)",
                (fingerprint, 1, now, now, now))
            self.conn.commit()
            return {"action": "notify", "occurrences": 1}

        occurrences = row["occurrences"] + 1
        self.conn.execute(
            "UPDATE incident SET occurrences = ?, lastSeenAt = ? "
            "WHERE fingerprint = ?", (occurrences, now, fingerprint))
        self.conn.commit()
        return {"action": "suppress", "occurrences": occurrences}

    def onRecovery(self, fingerprint: str) -> dict:
        """Khỏi rồi. Báo KÈM SỐ LẦN — đó là thông tin, không phải trang trí.

        "Đã khỏi" một mình không nói lên gì; "đã khỏi sau 21 lần hỏng trong 6
        tiếng" nói rằng có thứ cần sửa tận gốc.
        """
        row = self.conn.execute(
            "SELECT * FROM incident WHERE fingerprint = ?",
            (fingerprint,)).fetchone()
        if row is None:
            return {"action": "silent", "occurrences": 0}
        self.conn.execute("DELETE FROM incident WHERE fingerprint = ?",
                          (fingerprint,))
        self.conn.commit()
        return {"action": "notifyRecovery", "occurrences": row["occurrences"],
                "firstSeenAt": row["firstSeenAt"]}

    def openIncidents(self) -> list:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM incident ORDER BY firstSeenAt")]


# ══════════════════════════ im lặng cũng là sự cố ══════════════════════════

def silenceIsAnIncident(lastHeartbeatAt: Optional[str],
                        maxSilenceHours: int = 6,
                        now: Optional[str] = None) -> Optional[Event]:
    """Không có tin nào QUÁ LÂU thì bản thân điều đó là một sự cố.

    Đây là phép kiểm mà hệ đã thiếu suốt 61 giờ chết: mọi thứ báo xanh vì
    không có gì báo cả. Một hệ chỉ biết kêu khi có lỗi thì nó câm đúng lúc nó
    chết.

    ⚠ Phép kiểm này phải chạy TỪ NGOÀI hệ đang canh. Chạy từ bên trong thì khi
    hệ chết, phép kiểm cũng chết theo — đúng cái bẫy đã sập lần trước.
    """
    from datetime import datetime, timedelta, timezone
    now = now or utcNow()
    if not lastHeartbeatAt:
        return Event(kind=EventKind.productionDown,
                     payload={"reason": "chưa từng có nhịp tim nào"},
                     source="silenceCheck")
    try:
        last = datetime.strptime(lastHeartbeatAt, "%Y-%m-%dT%H:%M:%SZ")
        current = datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return Event(kind=EventKind.productionDown,
                     payload={"reason": f"mốc nhịp tim không đọc được: "
                                        f"{lastHeartbeatAt!r}"},
                     source="silenceCheck")
    silentFor = current - last
    if silentFor > timedelta(hours=maxSilenceHours):
        return Event(
            kind=EventKind.productionDown,
            payload={"reason": f"im lặng {silentFor} — quá ngưỡng "
                               f"{maxSilenceHours} giờ",
                     "lastHeartbeatAt": lastHeartbeatAt},
            source="silenceCheck")
    return None


# ══════════════════════════ sổ event ══════════════════════════

def openStore(path: str = DEFAULT_STORE) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS eventLog (
          eventId   TEXT PRIMARY KEY,
          kind      TEXT NOT NULL,
          source    TEXT NOT NULL DEFAULT '',
          payload   TEXT NOT NULL DEFAULT '{}',
          createdAt TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS eventLog_kind ON eventLog (kind, createdAt);
        """
    )
    conn.commit()
    return conn


def record(conn: sqlite3.Connection, event: Event) -> Event:
    import json
    conn.execute(
        "INSERT OR REPLACE INTO eventLog (eventId, kind, source, payload, "
        "createdAt) VALUES (?,?,?,?,?)",
        (event.eventId, event.kind.value, event.source,
         json.dumps(event.payload, ensure_ascii=False), event.createdAt))
    conn.commit()
    return event


def recentEvents(conn: sqlite3.Connection, kind: Optional[EventKind] = None,
                 limit: int = 50) -> list:
    if kind:
        rows = conn.execute(
            "SELECT * FROM eventLog WHERE kind = ? ORDER BY createdAt DESC "
            "LIMIT ?", (kind.value, limit))
    else:
        rows = conn.execute(
            "SELECT * FROM eventLog ORDER BY createdAt DESC LIMIT ?", (limit,))
    return [dict(r) for r in rows]


# ══════════════════════════ luật mặc định ══════════════════════════

def defaultRules() -> tuple:
    """Bộ luật khởi đầu. Mọi đề xuất đều là việc ĐỌC — S3 vẫn nguyên.

    Cố ý không có luật nào đề xuất việc GHI. Hệ tự phát hiện vấn đề là một
    chuyện; hệ tự sửa mà không ai nhìn là chuyện khác hẳn, và chuyện thứ hai
    phải đợi Autonomy có bằng chứng (xem core/autonomy.py).
    """
    return (
        Rule(
            name="buildFailedThenLook",
            eventKind=EventKind.buildFailed,
            description="Build hỏng thì ĐỌC log, chưa sửa gì",
            propose=lambda event: (TaskProposal(
                companyId="", capability="",
                inputValue={"projectId": event.payload.get("projectId", "")},
                reason="build hỏng — đọc log và tóm tắt nguyên nhân cho admin"),),
        ),
        Rule(
            name="quotaHitThenReport",
            eventKind=EventKind.quotaHit,
            description="Chạm trần hạn mức thì báo admin, không tự xoay",
            propose=lambda event: (TaskProposal(
                companyId="", capability="",
                inputValue={},
                reason="chạm trần hạn mức — báo admin kèm mốc mở lại"),),
        ),
        Rule(
            name="missionStalledThenAsk",
            eventKind=EventKind.missionStalled,
            description="Mission đứng bánh thì HỎI admin còn theo không",
            propose=lambda event: (TaskProposal(
                companyId="", capability="",
                inputValue={"missionId": event.payload.get("missionId", "")},
                reason="mission đứng bánh — hỏi admin còn theo đuổi không"),),
        ),
    )


def proposalsAreReadOnly(proposals: tuple, riskOf: Callable) -> list:
    """Soát rằng không đề xuất nào của event là việc GHI.

    EV-1 bằng CODE, không bằng lời dặn. `riskOf(companyId, capability)` do
    người gọi cung cấp — core/ không đọc manifest company (W3′).
    """
    offenders = []
    for proposal in proposals:
        if not proposal.companyId or not proposal.capability:
            continue
        risk = riskOf(proposal.companyId, proposal.capability)
        if risk is not RiskTier.read:
            offenders.append(
                f"{proposal.companyId}.{proposal.capability} là "
                f"`{risk.value}` — event không được đề xuất việc ghi")
    return offenders
