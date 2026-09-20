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
    Capability, Event, EventKind, IssuedBy, PolicyDecision, PolicyRequest,
    RiskTier, TaskStatus,
)
from core.policy import decide  # noqa: E402
from core.audit import (  # noqa: E402
    TEST_TRACE_PREFIXES as PREFIXES, trackRecordRows,
)
from core.events import (  # noqa: E402
    EventBus, NotificationThrottle, Rule, TaskProposal, decideNotification,
    defaultRules,
    deterministicEventId, eventsFromFacts, proposalsAreReadOnly, record,
    openStore as eventsOpenStore, recentEvents, recordIfNew,
    silenceIsAnIncident,
)

# Tên cũ, giữ cho phần ca thử đã có từ trước không phải sửa theo.
openStore = eventsOpenStore


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


class TestEventsAreBornFromFactsNotFromGuesses(unittest.TestCase):
    """`eventsFromFacts` là hàm THUẦN — sự thật vào, event ra.

    Người gọi tra sqlite rồi đưa vào. Nhờ vậy câu "sự cố này có đẻ ra event
    không" kiểm được bằng một dòng assert, thay vì phải dựng một lượt
    scheduler thật với đủ bốn cái sổ.
    """

    def testNoFactsNoEvents(self):
        self.assertEqual(eventsFromFacts({}), ())
        self.assertEqual(eventsFromFacts({"failedTasks": [],
                                          "quotaHits": [],
                                          "stalledMissions": [],
                                          "silence": None}), ())

    def testOneSourceBrokenDoesNotSilenceTheOthers(self):
        """Thiếu khoá KHÔNG phải lỗi — mỗi nguồn hỏng độc lập với nhau.

        Sổ mission hỏng thì vẫn phải báo được lời gọi hỏng. Gộp chung là để
        một nguồn câm làm câm cả bộ phát hiện — đúng thứ 61 giờ im lặng đã
        dạy một lần.
        """
        events = eventsFromFacts({"failedTasks": [{"taskId": "tsk_1"}]})
        self.assertEqual([e.kind for e in events], [EventKind.taskFailed])

    def testEveryKindIsCovered(self):
        events = eventsFromFacts({
            "failedTasks": [{"taskId": "tsk_1", "companyId": "aCompany",
                             "capability": "doIt"}],
            "quotaHits": [{"hitId": 7, "loai": "session"}],
            "stalledMissions": [{"missionId": "msn_1", "title": "x",
                                 "updatedAt": "2026-09-01T00:00:00Z"}],
            "silence": {"hours": 61, "since": "2026-08-14T00:00:00Z"},
        })
        self.assertEqual(
            sorted(e.kind.value for e in events),
            sorted(["taskFailed", "quotaHit", "missionStalled",
                    "productionDown"]))


class TestTheSameIncidentNeverNotifiesTwice(unittest.TestCase):
    """Bẫy 21 tin lúc nửa đêm, chặn bằng KHOÁ CHÍNH chứ không bằng bảng trạng thái.

    "Cron 15 phút/lần × sự cố 6 tiếng = 21 tin giống hệt lúc nửa đêm, dạy
    admin bỏ qua thông báo." Cách chống rẻ nhất là làm `eventId` tất định theo
    NỘI DUNG sự cố: lần quét thứ hai đụng khoá chính và bị bỏ qua. Không có
    trạng thái thứ hai nào để lệch.
    """

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.conn = eventsOpenStore(
            os.path.join(self.folder.name, "event.sqlite"))

    def tearDown(self):
        self.conn.close()
        self.folder.cleanup()

    def testTwentyOneSweepsOfOneIncidentGiveOneEvent(self):
        facts = {"failedTasks": [{"taskId": "tsk_hong", "companyId": "a",
                                  "capability": "b"}]}
        moi = 0
        for _ in range(21):          # 6 tiếng sự cố, quét mỗi 15 phút
            for event in eventsFromFacts(facts):
                if recordIfNew(self.conn, event):
                    moi += 1
        self.assertEqual(
            moi, 1,
            "cùng một sự cố báo nhiều lần — đúng bẫy 21 tin lúc nửa đêm")

    def testSilenceKeyIsTheStartNotTheDuration(self):
        """Số giờ TĂNG mỗi lần quét, nên khoá theo nó là đẻ event mới mãi.

        Đây là chỗ dễ sai nhất: `{"hours": 1}` rồi `{"hours": 2}` trông như
        hai sự cố, thật ra là một sự cố đang kéo dài.
        """
        moi = 0
        for gio in range(1, 8):
            facts = {"silence": {"hours": gio, "since": "2026-08-14T00:00:00Z"}}
            for event in eventsFromFacts(facts):
                if recordIfNew(self.conn, event):
                    moi += 1
        self.assertEqual(moi, 1)

    def testAMissionThatStallsAgainIsANewIncident(self):
        """Chiều kia: đừng chống lặp quá tay thành ra im lặng vĩnh viễn.

        Mission đứng bánh → nhúc nhích → lại đứng bánh là HAI sự cố, và admin
        cần biết lần thứ hai. Khoá chỉ theo `missionId` thì lần hai không bao
        giờ tới tai ai.
        """
        for updatedAt in ("2026-09-01T00:00:00Z", "2026-09-15T00:00:00Z"):
            for event in eventsFromFacts({"stalledMissions": [
                    {"missionId": "msn_1", "title": "x",
                     "updatedAt": updatedAt}]}):
                recordIfNew(self.conn, event)
        self.assertEqual(len(recentEvents(self.conn)), 2)

    def testDifferentIncidentsDoNotCollide(self):
        for taskId in ("tsk_1", "tsk_2", "tsk_3"):
            for event in eventsFromFacts({"failedTasks": [{"taskId": taskId}]}):
                recordIfNew(self.conn, event)
        self.assertEqual(len(recentEvents(self.conn)), 3)


class TestShippedRulesStillProposeNothingButReading(unittest.TestCase):
    """EV-1 áp cho bộ luật ĐANG CHẠY, không chỉ cho bộ luật lúc viết ra.

    Bộ luật vừa thêm hai cái (`taskFailedThenTell`, `silenceThenAlert`). Ca
    này chạy MỌI luật với event thật rồi soát kết quả — nếu ai đó thêm luật
    thứ sáu đề xuất một việc ghi, nó đỏ ở đây chứ không đỏ lúc 3 giờ sáng.
    """

    def testEveryDefaultRuleProposesOnlyReadWork(self):
        bus = EventBus()
        for rule in defaultRules():
            bus.register(rule)

        proposals = []
        for event in eventsFromFacts({
                "failedTasks": [{"taskId": "t", "companyId": "a",
                                 "capability": "b"}],
                "quotaHits": [{"hitId": 1}],
                "stalledMissions": [{"missionId": "m", "updatedAt": "u"}],
                "silence": {"hours": 61, "since": "s"}}):
            proposals.extend(bus.dispatch(event))

        self.assertTrue(proposals, "không luật nào khớp — bus đang câm")
        self.assertEqual(
            proposalsAreReadOnly(tuple(proposals),
                                 lambda c, k: RiskTier.irreversible), [],
            "có luật đề xuất việc GHI — EV-1 nói event ĐỀ XUẤT, không CẤP QUYỀN")

    def testNoRuleProposesRetryingTheFailedCall(self):
        """Tự thử lại khi chưa biết vì sao hỏng là cách biến lỗi thành vòng lặp.

        Đó là đặc quyền của mức tự chủ 3, và hôm nay không năng lực nào đạt
        tới đó. Nên luật `taskFailed` phải dừng ở BÁO, không đề xuất chạy lại.
        """
        bus = EventBus()
        for rule in defaultRules():
            bus.register(rule)
        proposals = []
        for event in eventsFromFacts({"failedTasks": [
                {"taskId": "t", "companyId": "aCompany",
                 "capability": "doIt"}]}):
            proposals.extend(bus.dispatch(event))

        for proposal in proposals:
            with self.subTest(reason=proposal.reason):
                self.assertEqual(proposal.companyId, "")
                self.assertEqual(proposal.capability, "")
                for tu in ("chạy lại", "thử lại", "retry"):
                    self.assertNotIn(tu, proposal.reason.lower())


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


class TestSkippedIsNotRecovery(unittest.TestCase):
    """"Bỏ qua" KHÁC "đã khỏi". Gộp lại là báo tin mừng 15 phút một lần.

    ═══════════════════════════════════════════════════════════════════
    HOÁ ĐƠN: 67 TIN "ĐÃ CHẠY LẠI ĐƯỢC"
    ═══════════════════════════════════════════════════════════════════

    `calendarWatch` chạy 15 phút/lần với `quietIfEmpty`, nên lịch trống thì nó
    trả `skipped`. Người gọi cố ý BỎ QUA `skipped` khi đi tìm trạng thái trước
    — để một lượt im không xoá dấu vết lần hỏng. Đúng ý định.

    Nhưng bản cũ của `decideNotification` hỏi "lần này có hỏng không?" và coi
    MỌI thứ không-hỏng là đã khỏi. Nên `skipped` → `notifyRecovery`, trong khi
    dòng `failed` cũ nằm đó VĨNH VIỄN vì không lượt `skipped` nào thay được nó.

    Đo 20/09: lần hỏng thật lúc 08:52 (do con bug `gateway.py` của §36). Vá
    xong lúc 17:07, lịch hết hỏng — và từ đó cứ 15 phút admin nhận một tin
    "Đã chạy lại được (hỏng 1 lần liên tiếp trước đó)". Sổ đếm **67** tin loại
    này từ 17/08.

    Trớ trêu: đây đúng là "21 tin lúc nửa đêm" mà chính hàm này sinh ra để
    chặn, chỉ khác là tin BÁO TIN MỪNG. Và nó dạy admin bỏ qua thông báo y hệt.
    """

    def testSkippedAfterFailureStaysSilent(self):
        quyet = decideNotification("failed", "skipped", 1)
        self.assertEqual(
            quyet["action"], "silent",
            "một lượt BỎ QUA bị coi là đã khỏi — 15 phút một tin báo tin mừng")

    def testSkippedDoesNotEraseTheMemoryOfFailure(self):
        """Im lặng ở lượt `skipped`, nhưng lượt CHẠY THẬT sau đó vẫn phải báo.

        Vá quá tay thành "không bao giờ báo khỏi" thì hỏng theo chiều kia:
        admin biết hệ hỏng mà không bao giờ biết nó đã khỏi.
        """
        self.assertEqual(decideNotification("failed", "skipped", 3)["action"],
                         "silent")
        quyet = decideNotification("failed", "ok", 3)
        self.assertEqual(quyet["action"], "notifyRecovery")
        self.assertEqual(quyet["occurrences"], 3)

    def testOnlyRealSuccessCountsAsRecovery(self):
        """Danh sách TRẮNG: trạng thái lạ rơi vào im lặng, không vào "đã khỏi".

        Thêm một trạng thái mới (`deferred`, `partial`…) mà quên khai thì nó
        sai về phía KHÔNG nhắn — ồn ít đi, chứ không ồn thêm.
        """
        for la in ("skipped", "deferred", "partial", "unknown", ""):
            with self.subTest(status=la):
                self.assertEqual(
                    decideNotification("failed", la, 1)["action"], "silent")
        for that in ("ok", "completed"):
            with self.subTest(status=that):
                self.assertEqual(
                    decideNotification("failed", that, 1)["action"],
                    "notifyRecovery")

    def testFailureReportingIsUnchanged(self):
        """Ba nhánh cũ phải y nguyên — đây là bản vá CỘNG THÊM."""
        self.assertEqual(decideNotification(None, "failed")["action"], "notify")
        self.assertEqual(decideNotification("failed", "failed", 2)["action"],
                         "suppress")
        self.assertEqual(decideNotification("ok", "ok")["action"], "silent")


class TestDrillTrafficIsRegisteredAsTestTraffic(unittest.TestCase):
    """Bộ diễn tập phát minh nhãn mới thì phải ĐĂNG KÝ nó.

    Tối 20/09, bài `hong` cố ý làm `failOnPurpose` hỏng bốn kiểu. Nhãn `drl_`
    chưa có trong `TEST_TRACE_PREFIXES`, nên event bus thấy chúng trong
    `taskLog`, tưởng là sự cố THẬT, và nhắn admin năm dòng
    "travisSelfTestCompany.failOnPurpose hỏng — báo admin, chờ admin quyết".

    Bộ đo tự báo động về chính nó. Bẫy này đã ghi HAI lần trong bảng, và vẫn
    dính — vì phát minh một nhãn mới thì không có gì bắt phải đăng ký.
    """

    def testEveryKnownMeasuringPrefixIsRegistered(self):
        for nhan in ("reg_", "evl_", "e2e_", "demo_", "drl_"):
            with self.subTest(prefix=nhan):
                self.assertIn(
                    nhan, PREFIXES,
                    f"`{nhan}` là nhãn của một bộ đo nhưng chưa đăng ký — "
                    "mọi thứ nó đẻ ra sẽ bị đếm như việc THẬT")

    def testTheDrillRunnerAsksForItsPrefix(self):
        """Bộ diễn tập phải LẤY nhãn từ danh sách chung, không gõ lại chuỗi.

        Gõ lại thì hai bản sẽ lệch đúng vào hôm ai đó thêm bộ đo thứ sáu.
        """
        duongDan = os.path.join(REPO_ROOT, "tests", "drills", "run.py")
        with open(duongDan, encoding="utf-8") as fh:
            nguon = fh.read()
        self.assertIn("from core.audit import TEST_TRACE_PREFIXES", nguon)
        self.assertIn("assert DRILL_PREFIX in TEST_TRACE_PREFIXES", nguon)


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


class TestPolicyReadsEarnedAutonomy(unittest.TestCase):
    """A-1 — Policy bớt hỏi khi mức đã KIẾM ĐƯỢC, và chỉ khi company KHAI.

    ═══ ĐÂY LÀ CA CANH MỘT LẦN NỚI QUYỀN ═══

    Trước 2026-09-20 mọi việc `write` đều hỏi admin, không có ngoại lệ nào
    ngoài whitelist và chữ ký. Cửa này là ngoại lệ thứ ba, nên nó phải chứng
    minh được hai chiều chứ không phải một:

      · chiều MỞ — có khai, có bằng chứng thì đi được (không thì cửa là hàng
        rào giả: khai một khoá mà không ai đọc);
      · chiều ĐÓNG — `irreversible` và `paidApi` KHÔNG BAO GIỜ đi được, dù
        thống kê đẹp tới đâu; và không khai thì cũng không đi được, dù mức 4.

    Chiều ĐÓNG mới là chiều quan trọng, vì nó hỏng trong IM LẶNG: một năng lực
    lẽ ra phải hỏi mà tự chạy thì không có dòng lỗi nào, chỉ có một việc đã làm
    xong mà admin không biết.
    """

    @staticmethod
    def _capability(risk=RiskTier.write, optIn=True, paid=None):
        return Capability(
            companyId="caGiaCompany", name="ghiThu",
            description="ghi một dòng vào sổ của chính nó",
            riskTier=risk, maxDurationSec=20,
            autonomyOptIn=optIn, paidApi=paid)

    @staticmethod
    def _ask(capability, level):
        return decide(PolicyRequest(
            identity=IssuedBy.ceo, capability=capability,
            inputValue={"label": "alpha"}, earnedAutonomyLevel=level))

    # ─────────────────── chiều MỞ ───────────────────

    def testEarnedLevelTwoStopsAskingForWrite(self):
        """Có khai + mức 2 thì đi thẳng, KHÔNG hỏi admin nữa."""
        outcome = self._ask(self._capability(), 2)
        self.assertIs(outcome.decision, PolicyDecision.allowWithVerify)
        self.assertIn("tự chủ", outcome.reason)

    def testItNeverBecomesAPlainAllow(self):
        """Được tự do hơn thì phải chứng minh NHIỀU hơn, không phải ít hơn.

        `allow` trần nghĩa là chạy xong không ai đòi bằng chứng. Nếu cửa này
        ra `allow` thì mức tự chủ sẽ trôi lên dựa trên một quá khứ không còn ai
        đo được — đúng vòng lặp mà `requiresVerification` sinh ra để cắt.
        """
        outcome = self._ask(self._capability(), 2)
        self.assertIsNot(outcome.decision, PolicyDecision.allow)
        self.assertTrue(requiresVerification(2))

    # ─────────────────── chiều ĐÓNG ───────────────────

    def testWithoutOptInItStillAsksEvenAtLevelFour(self):
        """Không khai = không bao giờ. Thống kê không thay được một lời khai."""
        outcome = self._ask(self._capability(optIn=False), 4)
        self.assertIs(outcome.decision, PolicyDecision.allowWithApproval)

    def testLevelOneStillAsks(self):
        outcome = self._ask(self._capability(), 1)
        self.assertIs(outcome.decision, PolicyDecision.allowWithApproval)

    def testIrreversibleNeverRunsWithoutAsking(self):
        """Hàng rào quan trọng nhất, nên nó đứng bằng HAI chân độc lập.

        `maxAutonomyFor(irreversible)` là 0, VÀ `canEverActOnEarnedAutonomy`
        loại thẳng nó. Gỡ một chân thì chân kia vẫn giữ — đó là chủ ý, vì một
        lần sai ở đây không có đường về.
        """
        cap = self._capability(risk=RiskTier.irreversible)
        self.assertFalse(cap.canEverActOnEarnedAutonomy)
        self.assertEqual(maxAutonomyFor(RiskTier.irreversible), 0)
        for level in (0, 1, 2, 3, 4):
            with self.subTest(level=level):
                self.assertIs(self._ask(cap, level).decision,
                              PolicyDecision.allowWithApproval)

    def testPaidApiNeverRunsWithoutAsking(self):
        """G9 cho ví: "luôn cho phép tiêu tiền" là câu không ai muốn nói."""
        cap = self._capability(
            paid={"nhaCungCap": "nhà nào đó", "giaUocVnd": 5000})
        self.assertFalse(cap.canEverActOnEarnedAutonomy)
        for level in (2, 3, 4):
            with self.subTest(level=level):
                self.assertIs(self._ask(cap, level).decision,
                              PolicyDecision.allowWithApproval)

    def testHighRiskNeverRunsWithoutAsking(self):
        """Trần của `high` là 1, nên `mayActWithoutAsking` chặn dù đã khai."""
        cap = self._capability(risk=RiskTier.high)
        self.assertTrue(cap.canEverActOnEarnedAutonomy)
        for level in (2, 3, 4):
            with self.subTest(level=level):
                self.assertIs(self._ask(cap, level).decision,
                              PolicyDecision.allowWithApproval)

    def testAutonomyDoesNotOpenTheCronDoor(self):
        """S3 đứng ĐẦU hàng luật, nên mức tự chủ không nâng được nó.

        Cron không có quyền gì để mà nới. Nếu ca này đỏ thì thứ tự luật trong
        `core/policy.decide` đã bị đảo, và một lịch chạy 5 phút/lần vừa có
        quyền ghi vào sổ của admin lúc 3h sáng.
        """
        outcome = decide(PolicyRequest(
            identity=IssuedBy.scheduledTrigger,
            capability=self._capability(),
            inputValue={"label": "alpha"},
            earnedAutonomyLevel=4))
        self.assertIs(outcome.decision, PolicyDecision.deny)
        self.assertIn("S3", outcome.reason)

    def testDefaultRequestKeepsTheOldBehaviour(self):
        """Người gọi nào quên tra mức thì nhận về hành vi CŨ.

        Mặc định phải sai về phía CHẶT. Nếu `earnedAutonomyLevel` mặc định là
        một số ≥2 thì mọi người gọi chưa sửa sẽ lặng lẽ được nới quyền.
        """
        outcome = decide(PolicyRequest(
            identity=IssuedBy.ceo, capability=self._capability(),
            inputValue={"label": "alpha"}))
        self.assertIs(outcome.decision, PolicyDecision.allowWithApproval)

    # ─────────────────── ai đã khai, tính tới hôm nay ───────────────────

    @staticmethod
    def _storeWithRows(folder, traceIds):
        """Một sổ tạm với những dòng HOÀN HẢO: chạy xong và đã kiểm chứng.

        Hoàn hảo là có chủ ý — ca ở dưới hỏi "lưu lượng nào được TÍNH", không
        hỏi "chạy đúng hay sai". Trộn hai câu đó lại thì một bộ lọc hỏng vẫn
        xanh nhờ mấy dòng trượt.
        """
        conn = sqlite3.connect(os.path.join(folder, "store.sqlite"))
        conn.executescript(
            """
            CREATE TABLE taskLog (
              taskId TEXT PRIMARY KEY, traceId TEXT, companyId TEXT,
              capability TEXT, status TEXT, startedAt TEXT,
              policyDecision TEXT, verificationJson TEXT);
            """)
        conn.row_factory = sqlite3.Row
        for index, traceId in enumerate(traceIds):
            conn.execute(
                "INSERT INTO taskLog (taskId, traceId, companyId, capability, "
                "status, startedAt, policyDecision, verificationJson) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (f"tsk_{index}", traceId, "caGiaCompany", "ghiThu", "ok",
                 "2026-09-20T00:00:00Z", "allowWithVerify",
                 '{"status": "verified"}'))
        conn.commit()
        return conn

    def testTestTrafficNeverEarnsAutonomy(self):
        """Chạy bộ ca thử KHÔNG phải là bằng chứng rằng hệ đáng tin hơn.

        Đo 2026-09-20, TRƯỚC khi vá: 227 dòng của
        `travisSelfTestCompany.recordWrite` gồm 194 dòng `e2e_` và 33 dòng
        `demo_` — không một lời gọi thật nào, mà bảng `travis.py autonomy` in
        ra mức 2. Chừng nào con số ấy chỉ để NHÌN thì đó là một phép đo bẩn;
        từ lúc `core/policy` đọc nó để bớt hỏi admin thì nó thành một cái cửa
        mở được bằng `python3 tests/run.py`.

        Ca này THỬ PHÁ chứ không đọc mã rồi tin: nó đổ vào sổ 50 dòng hoàn hảo
        mang nhãn bộ đo và đòi mức phải ĐỨNG YÊN ở 1.
        """
        with tempfile.TemporaryDirectory() as folder:
            conn = self._storeWithRows(
                folder,
                [f"{PREFIXES[index % len(PREFIXES)]}{index}"
                 for index in range(50)])

            rows = trackRecordRows(conn, "caGiaCompany", "ghiThu")
            self.assertEqual(
                rows, [],
                "lưu lượng của bộ đo lọt vào phép tính mức tự chủ")

            level = earnedAutonomy(
                recordFromAuditRows("caGiaCompany", "ghiThu", rows),
                RiskTier.write)
            self.assertEqual(level, 1)
            self.assertFalse(mayActWithoutAsking(level, RiskTier.write))
            conn.close()

    def testRealTrafficStillEarnsIt(self):
        """Chiều kia của cùng một ca: loại bộ đo mà đừng loại luôn việc thật.

        Không có ca này thì một bộ lọc quá tay — chẳng hạn loại mọi dòng — vẫn
        xanh, và cái thang thành thứ không ai trèo được. Hỏng theo hướng CHẶT
        thì im lặng, nên nó cần một ca riêng đi tìm.
        """
        with tempfile.TemporaryDirectory() as folder:
            conn = self._storeWithRows(
                folder, [f"trc_{index}" for index in range(12)])

            rows = trackRecordRows(conn, "caGiaCompany", "ghiThu")
            self.assertEqual(len(rows), 12)
            level = earnedAutonomy(
                recordFromAuditRows("caGiaCompany", "ghiThu", rows),
                RiskTier.write)
            self.assertEqual(level, 2)
            self.assertTrue(mayActWithoutAsking(level, RiskTier.write))
            conn.close()

    def testOptInIsDeclaredInManifestNotInCode(self):
        """Đọc từ manifest THẬT — khai bằng code là khai ở chỗ không ai soát."""
        raw = {"name": "ghiThu", "riskTier": "write", "autonomyOptIn": True}
        self.assertTrue(
            Capability.fromManifest("caGiaCompany", raw).autonomyOptIn)
        self.assertFalse(
            Capability.fromManifest(
                "caGiaCompany", {"name": "x", "riskTier": "write"}
            ).autonomyOptIn)


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
