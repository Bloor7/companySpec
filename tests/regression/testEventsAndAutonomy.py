#!/usr/bin/env python3
"""Events + Autonomy — tự phát hiện mà không tự cấp quyền."""
import os
import sqlite3
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO_ROOT)

from core.policy.autonomy import (  # noqa: E402
    MIN_RUNS_FOR_PROMOTION, TrackRecord, describeLevel, earnedAutonomy,
    explainAutonomy, maxAutonomyFor, mayActWithoutAsking, mayRetryAfterFailure,
    recordFromAuditRows, requiresVerification,
)
from core.contracts import (  # noqa: E402
    Event, EventKind, IssuedBy, RiskTier, TaskStatus,
)
from core.events import (  # noqa: E402
    EventBus, NotificationThrottle, Rule, TaskProposal, defaultRules,
    proposalsAreReadOnly, record, openStore, recentEvents,
    silenceIsAnIncident,
)


class TestEventBus(unittest.TestCase):

    def testRuleFailureDoesNotKillTheBus(self):
        """Một luật viết ẩu KHÔNG được làm câm cả khả năng tự phát hiện.

        Cùng họ với O8: cửa vào không được sập. Ở đây cửa là khả năng nhìn
        thấy vấn đề, và mất nó thì mất trong im lặng.
        """
        bus = EventBus()

        def explode(event):
            raise RuntimeError("luật này hỏng")

        bus.register(Rule("hong", EventKind.buildFailed, explode))
        bus.register(Rule("tot", EventKind.buildFailed,
                          lambda e: (TaskProposal("", "", {}, "vẫn chạy"),)))

        proposals = bus.dispatch(Event(kind=EventKind.buildFailed))
        reasons = [p.reason for p in proposals]
        self.assertTrue(any("vẫn chạy" in r for r in reasons))
        self.assertTrue(any("HỎNG" in r for r in reasons))

    def testOnlyMatchingRulesRun(self):
        bus = EventBus()
        bus.register(Rule("a", EventKind.buildFailed,
                          lambda e: (TaskProposal("", "", {}, "build"),)))
        bus.register(Rule("b", EventKind.quotaHit,
                          lambda e: (TaskProposal("", "", {}, "quota"),)))
        proposals = bus.dispatch(Event(kind=EventKind.quotaHit))
        self.assertEqual([p.reason for p in proposals], ["quota"])

    def testProposalCarriesEventTriggerIdentity(self):
        """Đề xuất phải mang danh tính `eventTrigger`, để Policy nhận ra nó."""
        proposal = TaskProposal("x", "y", {}, "vì sao")
        self.assertIs(proposal.issuedBy, IssuedBy.eventTrigger)


class TestEventsProposeButNeverGrant(unittest.TestCase):
    """EV-1 bằng CODE, không bằng lời dặn."""

    def testDefaultRulesProposeNoWrites(self):
        writeRisk = {("x", "ghiGiDo"): RiskTier.write}
        proposals = (TaskProposal("x", "ghiGiDo", {}, "thử"),)
        offenders = proposalsAreReadOnly(
            proposals, lambda c, cap: writeRisk[(c, cap)])
        self.assertTrue(offenders)
        self.assertIn("không được đề xuất việc ghi", offenders[0])

    def testReadProposalsPass(self):
        offenders = proposalsAreReadOnly(
            (TaskProposal("x", "docGiDo", {}, "thử"),),
            lambda c, cap: RiskTier.read)
        self.assertEqual(offenders, [])

    def testShippedRulesNeverNameAWriteCapability(self):
        """Bộ luật mặc định cố ý KHÔNG đề xuất việc ghi nào.

        Hệ tự phát hiện vấn đề là một chuyện; hệ tự sửa mà không ai nhìn là
        chuyện khác hẳn, và chuyện thứ hai phải đợi Autonomy có bằng chứng.
        """
        bus = EventBus()
        for rule in defaultRules():
            bus.register(rule)
        for kind in (EventKind.buildFailed, EventKind.quotaHit,
                     EventKind.missionStalled):
            for proposal in bus.dispatch(Event(kind=kind)):
                with self.subTest(kind=kind.value):
                    self.assertEqual(
                        proposal.capability, "",
                        "luật mặc định đề xuất thẳng một năng lực — phải để "
                        "admin/Core chọn, không tự chỉ định")


class TestNotificationThrottle(unittest.TestCase):
    """21 tin giống hệt lúc nửa đêm dạy admin bỏ qua thông báo."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.throttle = NotificationThrottle(self.conn)

    def testFirstFailureNotifies(self):
        self.assertEqual(self.throttle.onFailure("notion-503")["action"],
                         "notify")

    def testRepeatsAreSuppressed(self):
        self.throttle.onFailure("notion-503")
        for _ in range(20):
            result = self.throttle.onFailure("notion-503")
        self.assertEqual(result["action"], "suppress")
        self.assertEqual(result["occurrences"], 21)

    def testRecoveryReportsTheCount(self):
        """"Đã khỏi" một mình không nói lên gì; "đã khỏi sau 21 lần" thì có."""
        for _ in range(21):
            self.throttle.onFailure("notion-503")
        recovery = self.throttle.onRecovery("notion-503")
        self.assertEqual(recovery["action"], "notifyRecovery")
        self.assertEqual(recovery["occurrences"], 21)

    def testRecoveryWithoutIncidentIsSilent(self):
        self.assertEqual(self.throttle.onRecovery("chuaBaoGioHong")["action"],
                         "silent")

    def testDifferentIncidentsAreIndependent(self):
        self.throttle.onFailure("notion-503")
        self.assertEqual(self.throttle.onFailure("telegram-429")["action"],
                         "notify")


class TestSilenceIsAnIncident(unittest.TestCase):
    """Hệ chỉ biết kêu khi có lỗi thì nó CÂM đúng lúc nó chết."""

    def testLongSilenceRaisesEvent(self):
        event = silenceIsAnIncident("2026-09-17T00:00:00Z",
                                    maxSilenceHours=6,
                                    now="2026-09-19T13:00:00Z")
        self.assertIsNotNone(event, "61 giờ im lặng mà không ai kêu")
        self.assertIs(event.kind, EventKind.productionDown)

    def testFreshHeartbeatIsFine(self):
        self.assertIsNone(silenceIsAnIncident("2026-09-19T12:30:00Z",
                                              maxSilenceHours=6,
                                              now="2026-09-19T13:00:00Z"))

    def testNoHeartbeatAtAllIsAnIncident(self):
        self.assertIsNotNone(silenceIsAnIncident(None))

    def testUnparseableHeartbeatIsAnIncidentNotASilentPass(self):
        """Mốc hỏng KHÔNG được nuốt thành "chắc ổn" (O10)."""
        event = silenceIsAnIncident("hôm qua", now="2026-09-19T13:00:00Z")
        self.assertIsNotNone(event)


class TestEventStore(unittest.TestCase):

    def testEventsAreRecordedAndReadBack(self):
        path = os.path.join(tempfile.mkdtemp(prefix="travisEvt"), "e.sqlite")
        conn = openStore(path)
        try:
            record(conn, Event(kind=EventKind.quotaHit,
                               payload={"resetsAt": "2am"}, source="test"))
            rows = recentEvents(conn, EventKind.quotaHit)
            self.assertEqual(len(rows), 1)
            self.assertIn("2am", rows[0]["payload"])
        finally:
            conn.close()


class TestAutonomyCeilings(unittest.TestCase):
    """Trần theo rủi ro là phần KHÔNG thương lượng."""

    def testIrreversibleIsAlwaysZero(self):
        """"Đã làm đúng 500 lần" không phải lý lẽ với thứ không lấy lại được."""
        perfect = TrackRecord("x", "y", totalRuns=500, verifiedSuccesses=500)
        self.assertEqual(maxAutonomyFor(RiskTier.irreversible), 0)
        self.assertEqual(earnedAutonomy(perfect, RiskTier.irreversible), 0)

    def testWriteCapsAtTwo(self):
        perfect = TrackRecord("x", "y", totalRuns=500, verifiedSuccesses=500)
        self.assertEqual(earnedAutonomy(perfect, RiskTier.write), 2)

    def testReadCanReachFour(self):
        perfect = TrackRecord("x", "y", totalRuns=500, verifiedSuccesses=500)
        self.assertEqual(earnedAutonomy(perfect, RiskTier.read), 4)


class TestAutonomyIsEarnedNotAssumed(unittest.TestCase):

    def testNoHistoryIsNotTrust(self):
        """"Chưa hỏng lần nào" KHÁC "luôn chạy đúng" (O10).

        Nhầm hai câu đó là cách một thứ chưa ai thử được trao quyền tự chạy.
        """
        fresh = TrackRecord("x", "y")
        self.assertEqual(fresh.successRate, 0.0)
        self.assertEqual(earnedAutonomy(fresh, RiskTier.read), 1)

    def testTooFewRunsStaysAtOne(self):
        record_ = TrackRecord("x", "y", totalRuns=MIN_RUNS_FOR_PROMOTION - 1,
                              verifiedSuccesses=MIN_RUNS_FOR_PROMOTION - 1)
        self.assertEqual(earnedAutonomy(record_, RiskTier.read), 1)

    def testLowSuccessRateStaysAtOne(self):
        record_ = TrackRecord("x", "y", totalRuns=10, verifiedSuccesses=5,
                              failures=5)
        self.assertEqual(earnedAutonomy(record_, RiskTier.read), 1)

    def testOneIrreversibleFailureDemotesToZero(self):
        """Trung bình che mất cái đuôi, mà cái đuôi mới là thứ giết người."""
        record_ = TrackRecord("x", "y", totalRuns=100, verifiedSuccesses=99,
                              failures=1, irreversibleFailures=1)
        self.assertEqual(earnedAutonomy(record_, RiskTier.read), 0)

    def testLadderGoesDownNotOnlyUp(self):
        """Một cái thang chỉ đi lên là cái thang không ai dám trèo."""
        good = TrackRecord("x", "y", totalRuns=20, verifiedSuccesses=20)
        self.assertEqual(earnedAutonomy(good, RiskTier.read), 4)
        afterTrouble = TrackRecord("x", "y", totalRuns=21,
                                   verifiedSuccesses=20, failures=1)
        self.assertLess(earnedAutonomy(afterTrouble, RiskTier.read), 4)


class TestAutonomyGates(unittest.TestCase):

    def testActingWithoutAskingNeedsBothLevelAndRisk(self):
        """Hai điều kiện, không phải một — autonomy tăng CÙNG permission."""
        self.assertTrue(mayActWithoutAsking(2, RiskTier.read))
        self.assertFalse(mayActWithoutAsking(4, RiskTier.irreversible))
        self.assertFalse(mayActWithoutAsking(1, RiskTier.read))

    def testHigherAutonomyDemandsMoreProofNotLess(self):
        self.assertFalse(requiresVerification(1))
        self.assertTrue(requiresVerification(2))
        self.assertTrue(requiresVerification(4))

    def testSelfRetryIsLevelThreePrivilege(self):
        """Tự thử lại khi chưa biết vì sao hỏng là cách biến lỗi thành vòng lặp."""
        self.assertFalse(mayRetryAfterFailure(2))
        self.assertTrue(mayRetryAfterFailure(3))


class TestTrackRecordFromAudit(unittest.TestCase):
    """Lịch sử đọc từ SỔ, không nhận từ model."""

    def testOnlyCompletedCountsAsSuccess(self):
        rows = [
            {"status": TaskStatus.completed.value},
            {"status": TaskStatus.verifying.value},   # chạy xong ≠ đã kiểm chứng
            {"status": TaskStatus.failed.value},
        ]
        record_ = recordFromAuditRows("x", "y", rows)
        self.assertEqual(record_.totalRuns, 3)
        self.assertEqual(record_.verifiedSuccesses, 1)
        self.assertEqual(record_.failures, 1)

    def testApprovalRequestsAreNotFailures(self):
        """⚠ Bẫy đã dính thật: `needsApproval` bị đếm vào MẪU SỐ.

        Hệ dừng lại hỏi admin KHÔNG phải là trượt — đó là hệ làm đúng. Đếm
        chúng làm tỉ lệ đạt tụt vô nghĩa: `xuongCompany.nhanViec` ra 20% trong
        khi mọi lần nó CHẠY đều xong, chỉ là phần lớn lượt dừng ở cửa duyệt.

        Và cái sai đó nghiêng về phía CHẶT hơn nên nó im lặng — không ai đi
        tìm lý do một năng lực mãi không lên mức. (Sau khi sửa: 77%.)
        """
        rows = [{"status": TaskStatus.completed.value}] * 3
        rows += [{"status": "needsApproval"}] * 20
        rows += [{"status": "rejected"}] * 5
        record_ = recordFromAuditRows("x", "y", rows)
        self.assertEqual(record_.totalRuns, 3,
                         "lần KHÔNG CHẠY vẫn vào mẫu số")
        self.assertEqual(record_.successRate, 1.0)

    def testRanButUnverifiedCountsInDenominatorOnly(self):
        """`ok` = chạy trót lọt nhưng CHƯA kiểm chứng.

        Nó vào mẫu số mà không vào tử số — chạy mà không chứng minh được thì
        không được kéo mức lên.
        """
        rows = [{"status": TaskStatus.completed.value},
                {"status": "ok"}]
        record_ = recordFromAuditRows("x", "y", rows)
        self.assertEqual(record_.totalRuns, 2)
        self.assertEqual(record_.verifiedSuccesses, 1)
        self.assertEqual(record_.successRate, 0.5)

    def testIrreversibleFailureIsCounted(self):
        rows = [{"status": TaskStatus.failed.value, "isReversible": False}]
        self.assertEqual(
            recordFromAuditRows("x", "y", rows).irreversibleFailures, 1)

    def testExplanationIsReadable(self):
        text = explainAutonomy(TrackRecord("expenseCompany", "addExpense"),
                               RiskTier.write)
        self.assertIn("expenseCompany.addExpense", text)
        self.assertIn("chưa đủ", text)
        self.assertIn(describeLevel(1), text)


class TestWeeklyReview(unittest.TestCase):
    """§21 — bản soát tuần trả lời câu mà báo cáo ngày không trả lời được."""

    def setUp(self):
        import tempfile
        self.path = os.path.join(tempfile.mkdtemp(prefix="travisRev"),
                                 "store.sqlite")
        conn = sqlite3.connect(self.path)
        conn.executescript(
            """
            CREATE TABLE taskLog (
              taskId TEXT PRIMARY KEY, traceId TEXT, companyId TEXT,
              capability TEXT, status TEXT, startedAt TEXT,
              policyDecision TEXT, costUsd REAL);
            CREATE TABLE ceoRunLog (
              runId INTEGER PRIMARY KEY AUTOINCREMENT, traceId TEXT,
              createdAt TEXT, isError INTEGER, loi TEXT, costUsd REAL);
            """)
        self.conn = conn

    def _addCall(self, taskId, status, *, capability="doThing",
                 policyDecision="allow", traceId="trc_x",
                 startedAt="2026-09-19T10:00:00Z"):
        self.conn.execute(
            "INSERT INTO taskLog (taskId, traceId, companyId, capability, "
            "status, startedAt, policyDecision, costUsd) VALUES (?,?,?,?,?,?,?,0)",
            (taskId, traceId, "someCompany", capability, status, startedAt,
             policyDecision))
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def testFailingCapabilityIsNamed(self):
        from core.events.review import collect, weakSpots
        for index in range(8):
            self._addCall(f"t{index}",
                          "failed" if index < 4 else "ok")
        spots = weakSpots(collect(since="2026-09-01", storePath=self.path))
        self.assertTrue(any("someCompany.doThing" in s for s in spots))

    def testTinySampleIsNotAnAlarm(self):
        """1/2 là 50% nhưng nó chỉ có nghĩa "chạy hai lần".

        Báo động vì một mẫu quá nhỏ thì sớm muộn admin bỏ qua mọi báo động.
        """
        from core.events.review import collect, weakSpots
        self._addCall("a", "failed")
        self._addCall("b", "ok")
        self.assertEqual(
            weakSpots(collect(since="2026-09-01", storePath=self.path)), [])

    def testOldRowsWithoutPolicyColumnAreNotAlarmed(self):
        """⚠ Bẫy đã dính thật: bản đầu đếm CẢ dòng cũ hơn ngày thêm cột
        `policyDecision`, ra "5288 lời gọi không qua policy".

        Những dòng ấy KHÔNG THỂ có giá trị — cột chưa tồn tại lúc chúng được
        ghi. Báo động về quá khứ là báo động sai, và một cảnh báo đúng luật
        nhưng sai chỗ thì cũng dạy người ta bỏ qua cảnh báo.
        """
        from core.events.review import collect
        # Dòng CŨ: chưa có quyết định, ghi trước khi cột ra đời.
        self._addCall("old1", "ok", policyDecision=None,
                      startedAt="2026-09-01T10:00:00Z")
        self._addCall("old2", "ok", policyDecision=None,
                      startedAt="2026-09-02T10:00:00Z")
        # Dòng MỚI: cột đã có.
        self._addCall("new1", "ok", policyDecision="allow",
                      startedAt="2026-09-19T10:00:00Z")

        data = collect(since="2026-08-01", storePath=self.path)
        self.assertEqual(
            data["unexplained"], 0,
            "đếm cả dòng cũ hơn cột policyDecision — báo động về quá khứ")

    def testTrulyUnexplainedCallIsAlarmed(self):
        """Nhưng dòng MỚI mà thiếu quyết định thì PHẢI kêu — đó là đường vào
        hệ không qua cửa, thứ nguy hiểm nhất có thể tồn tại ở đây."""
        from core.events.review import collect, proposals
        self._addCall("new1", "ok", policyDecision="allow",
                      startedAt="2026-09-19T10:00:00Z")
        self._addCall("sneaky", "ok", policyDecision=None,
                      startedAt="2026-09-19T11:00:00Z")

        data = collect(since="2026-08-01", storePath=self.path)
        self.assertEqual(data["unexplained"], 1)
        self.assertTrue(any("KHÔNG có quyết định policy" in p
                            for p in proposals(data)))

    def testTestTrafficIsExcluded(self):
        """Bộ đo không được làm hỏng phép đo."""
        from core.events.review import collect
        for prefix in ("reg_", "evl_", "e2e_", "demo_"):
            self._addCall(f"x{prefix}", "failed", traceId=f"{prefix}abc")
        data = collect(since="2026-09-01", storePath=self.path)
        self.assertEqual(data["byCapability"], [])

    def testProposalsNeverPromiseAction(self):
        """§34 dừng ở CHỮ. Không Task nào sinh ra từ bản soát."""
        from core.events.review import collect, render
        self._addCall("a", "ok")
        text = render(collect(since="2026-09-01", storePath=self.path))
        self.assertIn("ĐỀ XUẤT, không phải việc đã làm", text)

    def testEmptyWeekSaysSoHonestly(self):
        """"Không thấy gì" KHÁC "mọi thứ tốt" — nói đúng cái mình biết."""
        from core.events.review import collect, proposals
        items = proposals(collect(since="2026-09-01", storePath=self.path))
        self.assertTrue(any("KHÔNG có nghĩa là mọi thứ tốt" in p
                            for p in items))


if __name__ == "__main__":
    unittest.main(verbosity=2)
