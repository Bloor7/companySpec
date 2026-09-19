#!/usr/bin/env python3
"""core.mission — mục tiêu dài hạn, và cách nó đẻ ra Task.

    Task    = việc cụ thể, chạy một lần.
    Mission = thứ việc đó phục vụ, sống nhiều tuần.

═══════════════════════════════════════════════════════════════════════
LUẬT QUAN TRỌNG NHẤT: MISSION KHÔNG CẤP QUYỀN
═══════════════════════════════════════════════════════════════════════

Travis được tự chia một Mission thành nhiều Task. Travis KHÔNG được vì thế mà
bỏ qua Policy: mỗi Task con vẫn đi qua đúng cánh cửa đó, vẫn hỏi duyệt nếu
phải hỏi.

Viết ngược lại — "admin đã duyệt Mission nên các Task bên trong khỏi hỏi" —
là cách biến một lần bấm nút thành một tờ séc khống. Admin duyệt MỘT NỘI DUNG
(G4), không duyệt một ý định.

═══════════════════════════════════════════════════════════════════════
VÀ MỘT LUẬT SINH RA TỪ SỰ CỐ THẬT
═══════════════════════════════════════════════════════════════════════

N3 — "ai là người đầu tiên biết việc đã xong, và họ biết bằng cách nào?"

Hộp từng dựng xong cả một web todolist rồi đặt việc về `choXem` và im lặng.
Cùng tối admin hỏi "cái web làm sao xem". Trạng thái nằm trong sổ KHÔNG PHẢI
là thông báo. Nên Mission có `stalled` và `awaitingReport`: một mission xong
mà chưa ai báo thì nó CHƯA xong.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from .contracts import Mission, MissionStatus, newId, utcNow

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_STORE = os.path.join(ROOT, "core", "mission.sqlite")

#: Không có Task nào nhúc nhích quá ngần này ngày → coi là ĐỨNG BÁNH.
#:
#: Không phải hỏng — đứng bánh. Khác nhau: hỏng thì có dòng lỗi, đứng bánh thì
#: im lặng, và im lặng là thứ đã để hệ chết 61 giờ mà không ai biết.
STALL_AFTER_DAYS = 7


class MissionError(ValueError):
    pass


def openStore(path: str = DEFAULT_STORE) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS mission (
          missionId   TEXT PRIMARY KEY,
          objective   TEXT NOT NULL,
          projectId   TEXT,
          status      TEXT NOT NULL,
          createdAt   TEXT NOT NULL,
          updatedAt   TEXT NOT NULL,
          reviewAt    TEXT,
          reportedAt  TEXT,
          closedReason TEXT
        );
        CREATE TABLE IF NOT EXISTS missionTask (
          missionId  TEXT NOT NULL,
          taskId     TEXT NOT NULL,
          status     TEXT NOT NULL,
          summary    TEXT NOT NULL DEFAULT '',
          createdAt  TEXT NOT NULL,
          PRIMARY KEY (missionId, taskId)
        );
        CREATE TABLE IF NOT EXISTS missionMetric (
          missionId TEXT NOT NULL,
          name      TEXT NOT NULL,
          target    TEXT NOT NULL DEFAULT '',
          observed  TEXT,
          measuredAt TEXT,
          PRIMARY KEY (missionId, name)
        );
        CREATE INDEX IF NOT EXISTS missionTask_mission
          ON missionTask (missionId, createdAt);
        """
    )
    conn.commit()
    return conn


def createMission(conn: sqlite3.Connection, objective: str,
                  projectId: Optional[str] = None,
                  metrics: tuple = ()) -> Mission:
    """Mở một mission.

    `objective` phải nói ĐƯỢC CÁI GÌ, không nói LÀM GÌ: "Panharmon lên top 10
    cho 5 từ khoá giải mộng" đo được; "cải thiện SEO" thì không, và một mục
    tiêu không đo được là một mục tiêu không bao giờ đóng được.
    """
    if not objective.strip():
        raise MissionError("mission phải có `objective`")

    mission = Mission(missionId=newId("mis"), objective=objective.strip(),
                      projectId=projectId, status=MissionStatus.active,
                      metrics=tuple(metrics))
    now = utcNow()
    conn.execute(
        "INSERT INTO mission (missionId, objective, projectId, status, "
        "createdAt, updatedAt) VALUES (?,?,?,?,?,?)",
        (mission.missionId, mission.objective, projectId,
         mission.status.value, now, now))
    for name in metrics:
        conn.execute(
            "INSERT OR REPLACE INTO missionMetric (missionId, name, target) "
            "VALUES (?,?,?)", (mission.missionId, name, ""))
    conn.commit()
    return mission


def attachTask(conn: sqlite3.Connection, missionId: str, taskId: str,
               status: str, summary: str = "") -> None:
    """Gắn một Task vào Mission.

    Gắn vào KHÔNG cấp quyền gì cho Task — xem ghi chú đầu file. Nó chỉ trả lời
    được câu "việc này phục vụ cái gì", thứ mà một danh sách task phẳng không
    trả lời được.
    """
    conn.execute(
        "INSERT OR REPLACE INTO missionTask (missionId, taskId, status, "
        "summary, createdAt) VALUES (?,?,?,?,?)",
        (missionId, taskId, status, summary, utcNow()))
    conn.execute("UPDATE mission SET updatedAt = ? WHERE missionId = ?",
                 (utcNow(), missionId))
    conn.commit()


def recordMetric(conn: sqlite3.Connection, missionId: str, name: str,
                 observed: str) -> None:
    """Số ĐO ĐƯỢC, kèm lúc đo.

    Không có `measuredAt` thì một con số cũ trông y hệt một con số mới, và
    "đã cải thiện" trở thành câu không kiểm được.
    """
    conn.execute(
        "UPDATE missionMetric SET observed = ?, measuredAt = ? "
        "WHERE missionId = ? AND name = ?",
        (observed, utcNow(), missionId, name))
    conn.commit()


def stalledMissions(conn: sqlite3.Connection,
                    afterDays: int = STALL_AFTER_DAYS,
                    now: Optional[datetime] = None) -> list:
    """Mission còn `active` mà lâu rồi không nhúc nhích.

    Đây là nguồn của event `missionStalled`. Không có phép soát này thì một
    mục tiêu chết lặng lẽ và không ai nhận ra — giống hệt 61 giờ hệ chết mà
    Task Scheduler vẫn báo xanh.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=afterDays)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = conn.execute(
        "SELECT * FROM mission WHERE status = ? AND updatedAt < ? "
        "ORDER BY updatedAt", (MissionStatus.active.value, cutoff))
    return [_toMission(row) for row in rows]


def missionsAwaitingReport(conn: sqlite3.Connection) -> list:
    """Xong rồi mà CHƯA AI BÁO — tính là chưa xong (N3).

    "Ai là người đầu tiên biết việc đã xong, và họ biết bằng cách nào?" Trả
    lời được bằng tên một hàm thì mới xong. Trạng thái nằm trong sổ không phải
    là thông báo.
    """
    rows = conn.execute(
        "SELECT * FROM mission WHERE status = ? AND reportedAt IS NULL",
        (MissionStatus.completed.value,))
    return [_toMission(row) for row in rows]


def markReported(conn: sqlite3.Connection, missionId: str) -> None:
    """Đã đẩy tin ra cho admin. CHỈ gọi sau khi thật sự gửi được."""
    conn.execute("UPDATE mission SET reportedAt = ? WHERE missionId = ?",
                 (utcNow(), missionId))
    conn.commit()


def closeMission(conn: sqlite3.Connection, missionId: str,
                 status: MissionStatus, reason: str = "") -> None:
    if status not in (MissionStatus.completed, MissionStatus.abandoned):
        raise MissionError(
            f"`{status.value}` không phải trạng thái đóng. Đóng bằng "
            "`completed` hoặc `abandoned` — và `abandoned` phải có lý do, "
            "vì bỏ dở mà không nói vì sao thì lần sau lại làm lại từ đầu.")
    if status is MissionStatus.abandoned and not reason.strip():
        raise MissionError("bỏ dở một mission thì phải nói lý do")
    conn.execute(
        "UPDATE mission SET status = ?, closedReason = ?, updatedAt = ? "
        "WHERE missionId = ?",
        (status.value, reason, utcNow(), missionId))
    conn.commit()


def missionProgress(conn: sqlite3.Connection, missionId: str) -> dict:
    """Bức tranh một mission, đủ để viết một dòng báo cáo tuần."""
    tasks = list(conn.execute(
        "SELECT status, COUNT(*) n FROM missionTask WHERE missionId = ? "
        "GROUP BY status", (missionId,)))
    byStatus = {row["status"]: row["n"] for row in tasks}
    metrics = [dict(row) for row in conn.execute(
        "SELECT name, target, observed, measuredAt FROM missionMetric "
        "WHERE missionId = ?", (missionId,))]
    return {
        "missionId": missionId,
        "taskCountByStatus": byStatus,
        "taskCount": sum(byStatus.values()),
        # CHỈ `completed`. `ok` của company nghĩa là "chạy trót lọt", không
        # phải "đã kiểm chứng" — xem core/verification.py.
        "completedCount": byStatus.get("completed", 0),
        "metrics": metrics,
        # Số liệu chưa ai đo là số liệu chưa có. Nói thẳng chứ đừng để 0 trông
        # như "đã đo và bằng không" (O10).
        "unmeasuredMetrics": [m["name"] for m in metrics if not m["measuredAt"]],
    }


def _toMission(row: sqlite3.Row) -> Mission:
    return Mission(
        missionId=row["missionId"],
        objective=row["objective"],
        projectId=row["projectId"],
        status=MissionStatus(row["status"]),
        createdAt=row["createdAt"],
    )
