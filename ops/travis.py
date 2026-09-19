#!/usr/bin/env python3
"""travis — cửa vào Travis Core cho admin.

    python3 ops/travis.py health              # hệ có còn sống không, im lặng bao lâu
    python3 ops/travis.py why <taskId>        # VÌ SAO lời gọi đó được phép
    python3 ops/travis.py autonomy            # mức tự chủ từng năng lực đã KIẾM được
    python3 ops/travis.py employees           # ai làm được gì, và ai bị cấm gì
    python3 ops/travis.py brains <mức>        # mức dữ liệu này gửi được cho ai
    python3 ops/travis.py mission list|new|close
    python3 ops/travis.py memory recall|forget-expired
    python3 ops/travis.py acquire <đường dẫn> # soi một repo lạ, KHÔNG chạy nó
    python3 ops/travis.py verify              # tự kiểm repo này

CHỈ ĐỌC, trừ `mission new|close`. Không lệnh nào ở đây chạm dữ liệu của admin,
không lệnh nào gọi model, không lệnh nào tốn tiền.

VÌ SAO CÓ FILE NÀY: dựng xong `core/` mà không có cửa nào mở vào nó thì nó là
một thư viện không ai gọi. Và câu hỏi quan trọng nhất — "vì sao hệ được phép
làm việc đó" — trước đây chỉ trả lời được bằng cách đọc lại code.
"""
import argparse
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import core.audit as coreAudit  # noqa: E402
from core.autonomy import (  # noqa: E402
    describeLevel, earnedAutonomy, explainAutonomy, maxAutonomyFor,
    recordFromAuditRows,
)
from core.brainRouter import (  # noqa: E402
    DataBoundaryError, allowedBrainsFor, explainRouting, loadBrainPolicy,
    routeBrains,
)
from core.contracts import DataClassification, MissionStatus, RiskTier  # noqa: E402
from core.employeeRegistry import loadEmployees  # noqa: E402
from core.events import (  # noqa: E402
    NotificationThrottle, silenceIsAnIncident,
)
from core.memory import expiringSoon, openStore as openMemory, recall  # noqa: E402
from core.mission import (  # noqa: E402
    closeMission, createMission, missionProgress, missionsAwaitingReport,
    openStore as openMissions, stalledMissions,
)

BACKOFFICE = os.path.join(ROOT, "backOffice", "store.sqlite")


# ══════════════════════════ health ══════════════════════════

def cmdHealth(args) -> int:
    """Hệ có còn sống không — và IM LẶNG BAO LÂU RỒI.

    Câu thứ hai mới là câu quan trọng. Hệ từng chết 61 giờ trong khi mọi thứ
    báo xanh, vì không có gì báo cả: một hệ chỉ biết kêu khi có lỗi thì nó câm
    đúng lúc nó chết.
    """
    conn = sqlite3.connect(BACKOFFICE)
    conn.row_factory = sqlite3.Row

    lastCall = conn.execute(
        "SELECT MAX(startedAt) FROM taskLog "
        "WHERE traceId NOT LIKE 'reg_%' AND traceId NOT LIKE 'e2e_%' "
        "AND traceId NOT LIKE 'evl_%'").fetchone()[0]

    print("── Travis health ──\n")
    print(f"  Lời gọi thật gần nhất : {lastCall or '(chưa có)'}")

    incident = silenceIsAnIncident(lastCall, maxSilenceHours=args.hours)
    if incident:
        print(f"  ⚠ SỰ CỐ            : {incident.payload.get('reason')}")
        print("    Im lặng quá lâu TỰ NÓ là một sự cố — đây là phép kiểm mà hệ")
        print("    đã thiếu suốt 61 giờ chết.")
    else:
        print(f"  Im lặng             : trong ngưỡng {args.hours} giờ")

    unexplained = coreAudit.unexplainedCalls(
        coreAudit.openStore(BACKOFFICE), since=args.since, limit=10)
    print(f"\n  Lời gọi KHÔNG qua Policy (từ {args.since}): {len(unexplained)}")
    if unexplained:
        print("    ⚠ Có đường vào hệ không qua cửa — thứ nguy hiểm nhất có thể")
        print("      tồn tại ở đây. Danh sách:")
        for row in unexplained[:5]:
            print(f"      {row['startedAt'][:19]} {row['companyId']}."
                  f"{row['capability']} → {row['status']}")

    throttle = NotificationThrottle(sqlite3.connect(":memory:"))
    open_ = throttle.openIncidents()
    print(f"\n  Sự cố đang mở       : {len(open_)}")
    conn.close()
    return 0


# ══════════════════════════ why ══════════════════════════

def cmdWhy(args) -> int:
    """VÌ SAO lời gọi đó được phép. §30 — câu bản cũ không trả lời được."""
    conn = coreAudit.openStore(BACKOFFICE)
    try:
        answer = coreAudit.whyWasThisAllowed(conn, args.taskId)
    finally:
        conn.close()

    if answer is None:
        print(f"Không có task `{args.taskId}` trong sổ.", file=sys.stderr)
        return 1

    print(f"── {answer['companyId']}.{answer['capability']} ──\n")
    print(f"  taskId          : {answer['taskId']}")
    print(f"  traceId         : {answer['traceId']}")
    print(f"  rủi ro          : {answer['riskTier']}")
    print(f"  employee        : {answer['employeeId'] or '(CEO gọi thẳng)'}")
    print(f"  bộ não          : {answer['brainId'] or '(không dùng model)'}")
    print(f"  chạy lúc        : {answer['startedAt']} → {answer['finishedAt']}")
    print(f"  tốn             : ${answer['costUsd'] or 0} "
          f"· {answer['paidVnd'] or 0:,.0f}đ tiền thật")
    print(f"\n  QUYẾT ĐỊNH      : {answer['policyDecision'] or '(dòng cũ, chưa có)'}")
    print(f"  VÌ SAO          : {answer['policyReason'] or '(dòng cũ, chưa có)'}")
    print(f"  kết quả         : {answer['status']}")

    verification = answer.get("verification")
    if not verification:
        print("\n  BẰNG CHỨNG      : (dòng cũ — chạy trước khi có Verification)")
        return 0
    print(f"\n  BẰNG CHỨNG      : {verification.get('status')}")
    for check in verification.get("checks", []):
        print(f"    {check['name']:20} {check['status']:14} {check['detail'][:70]}")
    return 0


# ══════════════════════════ autonomy ══════════════════════════

def cmdAutonomy(args) -> int:
    """Mức tự chủ từng năng lực đã KIẾM ĐƯỢC — từ sổ thật, không đặt tay."""
    conn = coreAudit.openStore(BACKOFFICE)
    try:
        pairs = list(conn.execute(
            "SELECT companyId, capability, riskTier, COUNT(*) n FROM taskLog "
            "WHERE policyDecision IS NOT NULL AND traceId NOT LIKE 'reg_%' "
            "AND traceId NOT LIKE 'e2e_%' "
            "GROUP BY companyId, capability ORDER BY n DESC LIMIT ?",
            (args.limit,)))
        print("── Mức tự chủ đã kiếm được ──\n")
        if not pairs:
            print("  Chưa có lời gọi nào có quyết định Policy kèm theo.")
            print("  Cột `policyDecision` mới thêm 2026-09-19, nên chỉ những")
            print("  lời gọi SAU mốc đó mới đếm được — đếm dòng cũ là trao")
            print("  quyền dựa trên một quá khứ ta không đo được.")
            return 0

        for row in pairs:
            rows = coreAudit.trackRecordRows(conn, row["companyId"],
                                             row["capability"])
            record = recordFromAuditRows(row["companyId"], row["capability"],
                                         rows)
            try:
                risk = RiskTier(row["riskTier"])
            except ValueError:
                continue
            level = earnedAutonomy(record, risk)
            ceiling = maxAutonomyFor(risk)
            print(f"  {row['companyId']}.{row['capability']}")
            print(f"    {describeLevel(level)}  (trần `{risk.value}` = {ceiling})")
            print(f"    {explainAutonomy(record, risk)}")
            print()
    finally:
        conn.close()

    print("  ⚠ Hệ thật đang chạy ở MỨC 1 với mọi thứ: `ops/` chưa đọc bảng này")
    print("    để nới quyền. Thang đã dựng và đã kiểm, chưa ai trèo — và đó là")
    print("    trạng thái đúng: nới quyền phải là quyết định có chủ ý của admin.")
    return 0


# ══════════════════════════ employees ══════════════════════════

def cmdEmployees(args) -> int:
    employees = loadEmployees()
    print("── Employee ──\n")
    for employeeId in sorted(employees):
        employee = employees[employeeId]
        print(f"  {employeeId}  ({employee.role})")
        print(f"    tính cách : {', '.join(employee.personality) or '—'}")
        print(f"    não       : {', '.join(employee.preferredBrains)} "
              f"→ {', '.join(employee.fallbackBrains) or '—'}")
        allowed = [f"{p.resource.value}.{p.action.value}"
                   + (f"@{p.environment.value}" if p.environment else "")
                   for p in employee.permissions]
        print(f"    được      : {', '.join(allowed) or 'KHÔNG GÌ CẢ'}")
        print(f"    CẤM       : {', '.join(employee.cannot) or '—'}")
        print()
    print("  `cannot` thắng `permissions`, luôn luôn (E-2). Một luật cấm mà có")
    print("  thể bị một luật cho phép lấn qua thì nó không phải luật cấm.")
    return 0


# ══════════════════════════ brains ══════════════════════════

def cmdBrains(args) -> int:
    policy = loadBrainPolicy()
    try:
        classification = DataClassification(args.classification)
    except ValueError:
        print(f"Mức `{args.classification}` không hợp lệ. Chọn: "
              f"{', '.join(c.value for c in DataClassification)}",
              file=sys.stderr)
        return 2

    allowed = allowedBrainsFor(classification, policy)
    print(f"── Dữ liệu mức `{classification.value}` ──\n")
    print(f"  Được phép nhận : {', '.join(allowed) or 'KHÔNG AI CẢ'}")
    if not allowed:
        print("\n  Mức này không nhà nào được nhận. Việc phải chạy trên máy")
        print("  nhà, hoặc không chạy. Đây là luật CHẶN, không phải gợi ý.")
        return 0

    for taskType in ("architectureReview", "codeChange", "research", "routine"):
        try:
            chain = routeBrains(taskType, classification, policy)
        except DataBoundaryError:
            continue
        print(f"\n  {taskType}")
        print(f"    {explainRouting(taskType, classification, policy, chain)}")
    return 0


# ══════════════════════════ mission ══════════════════════════

def cmdMission(args) -> int:
    conn = openMissions()
    try:
        if args.action == "new":
            if not args.objective:
                print("thiếu --objective", file=sys.stderr)
                return 2
            mission = createMission(conn, args.objective,
                                    projectId=args.project,
                                    metrics=tuple(args.metric or ()))
            print(f"đã mở mission {mission.missionId}")
            print(f"  mục tiêu: {mission.objective}")
            return 0

        if args.action == "close":
            if not args.missionId:
                print("thiếu --mission-id", file=sys.stderr)
                return 2
            closeMission(conn, args.missionId,
                         MissionStatus(args.status), reason=args.reason or "")
            print(f"đã đóng {args.missionId} ({args.status})")
            return 0

        rows = list(conn.execute(
            "SELECT * FROM mission ORDER BY updatedAt DESC LIMIT 30"))
        print("── Mission ──\n")
        if not rows:
            print("  (chưa có mission nào)")
        for row in rows:
            progress = missionProgress(conn, row["missionId"])
            print(f"  [{row['status']}] {row['missionId']}")
            print(f"    {row['objective']}")
            print(f"    task: {progress['completedCount']}/{progress['taskCount']} "
                  f"đã kiểm chứng")
            if progress["unmeasuredMetrics"]:
                print(f"    ⚠ chỉ số CHƯA AI ĐO: "
                      f"{', '.join(progress['unmeasuredMetrics'])}")
            print()

        stalled = stalledMissions(conn)
        if stalled:
            print(f"  ⚠ {len(stalled)} mission ĐỨNG BÁNH (không nhúc nhích >7 ngày):")
            for mission in stalled:
                print(f"    {mission.missionId} — {mission.objective[:60]}")
            print("    Đứng bánh thì IM LẶNG, và im lặng là thứ khó thấy nhất.")

        waiting = missionsAwaitingReport(conn)
        if waiting:
            print(f"\n  ⚠ {len(waiting)} mission XONG MÀ CHƯA AI BÁO:")
            for mission in waiting:
                print(f"    {mission.missionId} — {mission.objective[:60]}")
            print("    Trạng thái nằm trong sổ KHÔNG PHẢI là thông báo (N3).")
    finally:
        conn.close()
    return 0


# ══════════════════════════ memory ══════════════════════════

def cmdMemory(args) -> int:
    from core.contracts import MemoryTier
    conn = openMemory()
    try:
        if args.action == "expiring":
            items = expiringSoon(conn, withinDays=args.days)
            print(f"── Sắp hết hạn trong {args.days} ngày ──\n")
            if not items:
                print("  (không có)")
            for item in items:
                print(f"  [{item.kind.value}] {item.content[:70]}")
                print(f"    rụng lúc {item.expiresAt}")
            print("\n  Hỏi lại admin TRƯỚC khi chúng im lặng biến mất — bằng")
            print("  không thì M-2 sửa một lỗi bằng cách tạo một lỗi khác.")
            return 0

        try:
            tier = MemoryTier(args.tier)
        except ValueError:
            print(f"tier lạ. Chọn: {', '.join(t.value for t in MemoryTier)}",
                  file=sys.stderr)
            return 2
        items = recall(conn, tier, scopeId=args.scope or "", limit=args.limit)
        print(f"── Trí nhớ `{tier.value}`"
              + (f" · {args.scope}" if args.scope else "") + " ──\n")
        if not items:
            print("  (trống)")
        for item in items:
            mark = item.kind.value
            if item.confidence is not None:
                mark += f" {item.confidence:.1f}"
            print(f"  [{mark}] {item.content[:80]}")
            if item.source:
                print(f"      nguồn: {item.source}")
    finally:
        conn.close()
    return 0


# ══════════════════════════ acquire ══════════════════════════

def cmdAcquire(args) -> int:
    """Soi một repo lạ. KHÔNG chạy nó — chỉ đọc file."""
    from core.acquisition import formatReport, inspectRepository
    if not os.path.isdir(args.path):
        print(f"không có thư mục `{args.path}`", file=sys.stderr)
        return 2
    report = inspectRepository(args.path, source=args.path)
    print(formatReport(report))
    print(f"\n  Gợi ý: {report.verdict}")
    print("  (Đây là GỢI Ý, không phải quyết định. Quyết định cuối là của admin")
    print("   — một báo cáo tự chốt 'an toàn, dùng đi' là cái dấu đỏ không ai đọc.)")
    if args.json:
        print("\n" + json.dumps(report.toDict(), ensure_ascii=False, indent=2))
    return 0


# ══════════════════════════ verify ══════════════════════════

def cmdVerify(args) -> int:
    """Tự kiểm repo này bằng chính Verification Engine."""
    from core.verification import (
        CheckSpec, concludeTask, explainVerdict, loadVerificationPolicy, verify,
    )
    policy = loadVerificationPolicy()
    selfCheck = policy.get("selfCheck") or {}
    timeouts = policy.get("timeoutSec") or {}
    names = tuple(args.check) if args.check else tuple(sorted(selfCheck))

    print(f"── Tự kiểm: {', '.join(names)} ──\n")
    specs = tuple(CheckSpec(name=name, command=selfCheck.get(name),
                            timeoutSec=int(timeouts.get(name, 300)),
                            workingDirectory=ROOT)
                  for name in names)
    verification = verify(specs)
    for check in verification.checks:
        print(f"  {check.name:16} {check.status.value:14} {check.detail[:70]}")
    print(f"\n  {explainVerdict(verification, names)}")
    return 0 if concludeTask(verification, names).value == "completed" else 1


# ══════════════════════════ CLI ══════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(description="cửa vào Travis Core")
    sub = parser.add_subparsers(dest="command", required=True)

    health = sub.add_parser("health", help="hệ có còn sống không")
    health.add_argument("--hours", type=int, default=6,
                        help="im lặng quá ngần này giờ là sự cố")
    health.add_argument("--since", default="2026-09-19",
                        help="soát lời gọi không qua Policy từ mốc này")
    health.set_defaults(fn=cmdHealth)

    why = sub.add_parser("why", help="vì sao lời gọi đó được phép")
    why.add_argument("taskId")
    why.set_defaults(fn=cmdWhy)

    autonomy = sub.add_parser("autonomy", help="mức tự chủ đã kiếm được")
    autonomy.add_argument("--limit", type=int, default=15)
    autonomy.set_defaults(fn=cmdAutonomy)

    sub.add_parser("employees", help="ai làm được gì").set_defaults(
        fn=cmdEmployees)

    brains = sub.add_parser("brains", help="mức dữ liệu này gửi được cho ai")
    brains.add_argument("classification",
                        help="public | internal | private | sensitive | secret")
    brains.set_defaults(fn=cmdBrains)

    mission = sub.add_parser("mission", help="mục tiêu dài hạn")
    mission.add_argument("action", nargs="?", default="list",
                         choices=["list", "new", "close"])
    mission.add_argument("--objective")
    mission.add_argument("--project")
    mission.add_argument("--metric", action="append")
    mission.add_argument("--mission-id", dest="missionId")
    mission.add_argument("--status", default="completed",
                         choices=["completed", "abandoned"])
    mission.add_argument("--reason")
    mission.set_defaults(fn=cmdMission)

    memory = sub.add_parser("memory", help="trí nhớ phân tầng")
    memory.add_argument("action", nargs="?", default="recall",
                        choices=["recall", "expiring"])
    memory.add_argument("--tier", default="system")
    memory.add_argument("--scope")
    memory.add_argument("--limit", type=int, default=20)
    memory.add_argument("--days", type=int, default=7)
    memory.set_defaults(fn=cmdMemory)

    acquire = sub.add_parser("acquire", help="soi repo lạ, KHÔNG chạy nó")
    acquire.add_argument("path")
    acquire.add_argument("--json", action="store_true")
    acquire.set_defaults(fn=cmdAcquire)

    verifyCmd = sub.add_parser("verify", help="tự kiểm repo này")
    verifyCmd.add_argument("--check", action="append")
    verifyCmd.set_defaults(fn=cmdVerify)

    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
