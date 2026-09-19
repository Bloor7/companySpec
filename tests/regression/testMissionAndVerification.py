#!/usr/bin/env python3
"""Mission + Verification — "xong" phải có bằng chứng.

Ca ở đây chủ yếu chống MỘT họ lỗi: hệ báo xong trong khi chưa xong. Nó đã xảy
ra ít nhất ba lần với ba hình khác nhau, và không lần nào gây crash.
"""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO_ROOT)

from core.contracts import (  # noqa: E402
    CheckStatus, MissionStatus, TaskStatus, Verification, VerificationCheck,
)
from core.mission import (  # noqa: E402
    MissionError, attachTask, closeMission, createMission, markReported,
    missionProgress, missionsAwaitingReport, openStore, recordMetric,
    stalledMissions,
)
from core.verification import (  # noqa: E402
    NOT_APPLICABLE, CheckSpec, concludeTask, explainVerdict,
    loadVerificationPolicy, requiredCheckNames, runCheck, specsForProject,
    verify,
)

POLICY = loadVerificationPolicy()


class TestDoneMeansEvidence(unittest.TestCase):
    """V-1 — không có bằng chứng thì KHÔNG completed."""

    def testNoChecksIsNotDone(self):
        """Đây là `is_done()` bị đóng đinh: im lặng KHÔNG phải là thành công."""
        self.assertIs(concludeTask(Verification(checks=()), ("test",)),
                      TaskStatus.verifying)

    def testInconclusiveCountsAsFailure(self):
        """"Không chắc" tính là CHƯA XONG, không phải "coi như qua"."""
        verification = Verification(checks=(
            VerificationCheck("test", CheckStatus.inconclusive,
                              "không có lệnh"),))
        self.assertIs(concludeTask(verification, ("test",)), TaskStatus.failed)

    def testMissingRequiredCheckIsNotDone(self):
        """Chạy đủ thứ nhưng thiếu đúng phép kiểm bắt buộc → vẫn chưa xong."""
        verification = Verification(checks=(
            VerificationCheck("lint", CheckStatus.passed),))
        self.assertIs(concludeTask(verification, ("lint", "build")),
                      TaskStatus.verifying)

    def testAllRequiredPassedIsDone(self):
        verification = Verification(checks=(
            VerificationCheck("lint", CheckStatus.passed),
            VerificationCheck("build", CheckStatus.passed),
        ))
        self.assertIs(concludeTask(verification, ("lint", "build")),
                      TaskStatus.completed)

    def testFailedRequiredCheckIsFailure(self):
        verification = Verification(checks=(
            VerificationCheck("lint", CheckStatus.passed),
            VerificationCheck("build", CheckStatus.failed, "thoát mã 1"),
        ))
        self.assertIs(concludeTask(verification, ("lint", "build")),
                      TaskStatus.failed)

    def testOptionalCheckFailureDoesNotBlock(self):
        """Phép kiểm KHÔNG bắt buộc trượt thì không chặn — nhưng vẫn nằm trong
        bằng chứng để admin đọc."""
        verification = Verification(checks=(
            VerificationCheck("lint", CheckStatus.passed),
            VerificationCheck("visual", CheckStatus.failed, "lệch 3px"),
        ))
        self.assertIs(concludeTask(verification, ("lint",)),
                      TaskStatus.completed)


class TestMissingToolIsNotAPass(unittest.TestCase):
    """V-2 — thiếu công cụ kiểm KHÁC với đã kiểm."""

    def testNoCommandIsInconclusiveNotSkipped(self):
        """Dự án không có script test → KHÔNG được coi là "test PASS".

        Bản ngây thơ sẽ bỏ qua và in "build PASS · test PASS", trong khi sự
        thật là không có lệnh nào chạy cả.
        """
        check = runCheck(CheckSpec(name="test", command=None))
        self.assertIs(check.status, CheckStatus.inconclusive)
        self.assertIn("KHÔNG chứng minh được", check.detail)

    def testExplicitlyNotApplicableIsSkipped(self):
        """Bỏ qua được, NHƯNG phải khai rõ. Im lặng thì không."""
        check = runCheck(CheckSpec(name="build", command=NOT_APPLICABLE))
        self.assertIs(check.status, CheckStatus.skipped)

    def testDeclaredNotApplicableDoesNotBlockDone(self):
        """Cửa thoát của V-2 phải DÙNG ĐƯỢC, không thì nó chỉ là trang trí.

        ⚠ Bản đầu của core/verification.py gộp `skipped` với `inconclusive`,
        nên khai rõ `notApplicable` lại làm kết luận ra `failed`. Chính bộ đo
        bắt được khi chạy selfCheck của repo này (Python thuần nên typecheck và
        build đều `notApplicable`). Ca này canh để không ai gộp lại.
        """
        verification = Verification(checks=(
            VerificationCheck("lint", CheckStatus.passed),
            VerificationCheck("build", CheckStatus.skipped,
                              "khai rõ là không áp dụng"),
        ))
        self.assertIs(concludeTask(verification, ("lint", "build")),
                      TaskStatus.completed)

    def testInconclusiveStillBlocksEvenNextToSkipped(self):
        """`skipped` qua, `inconclusive` thì KHÔNG — hai thứ khác hẳn nhau."""
        verification = Verification(checks=(
            VerificationCheck("build", CheckStatus.skipped, "không áp dụng"),
            VerificationCheck("test", CheckStatus.inconclusive, "thiếu lệnh"),
        ))
        self.assertIs(concludeTask(verification, ("build", "test")),
                      TaskStatus.failed)

    def testProjectWithNullTestCommandCannotSilentlyPass(self):
        """registry/projects.yaml có `test: null` cho panharmon — cố ý, vì
        package.json chưa có script test. Nó phải ra `inconclusive`."""
        specs = specsForProject({"build": "true", "lint": "true",
                                 "test": None},
                                ("build", "lint", "test"))
        verification = verify(specs)
        self.assertIs(concludeTask(verification, ("build", "lint", "test")),
                      TaskStatus.failed)


class TestRealCommandsRun(unittest.TestCase):
    """Phép kiểm phải CHẠY THẬT, không phải giả vờ."""

    def testPassingCommandPasses(self):
        check = runCheck(CheckSpec(name="lint", command="true"))
        self.assertIs(check.status, CheckStatus.passed)

    def testFailingCommandFails(self):
        check = runCheck(CheckSpec(name="lint", command="false"))
        self.assertIs(check.status, CheckStatus.failed)
        self.assertIn("thoát mã 1", check.detail)

    def testTimeoutIsInconclusiveNotPassed(self):
        check = runCheck(CheckSpec(name="build", command="sleep 5",
                                   timeoutSec=1))
        self.assertIs(check.status, CheckStatus.inconclusive)

    def testMissingBinaryIsInconclusive(self):
        check = runCheck(CheckSpec(name="test",
                                   command="/khong/ton/tai/binary"))
        self.assertIs(check.status, CheckStatus.inconclusive)


class TestVerdictText(unittest.TestCase):
    """"Chưa xong" mà không nói thiếu gì thì admin phải đi mò."""

    def testSaysWhichCheckIsMissing(self):
        text = explainVerdict(
            Verification(checks=(VerificationCheck("lint", CheckStatus.passed),)),
            ("lint", "build"))
        self.assertIn("CHƯA XONG", text)
        self.assertIn("build", text)

    def testSaysWhichCheckFailed(self):
        text = explainVerdict(
            Verification(checks=(
                VerificationCheck("build", CheckStatus.failed, "thiếu module x"),)),
            ("build",))
        self.assertIn("thiếu module x", text)


class TestVerificationPolicy(unittest.TestCase):

    def testUiChangeNeedsEyes(self):
        """typecheck và build không bao giờ bắt được "nút lệch 40px"."""
        required = requiredCheckNames(POLICY, "uiChange")
        self.assertIn("visual", required)
        self.assertIn("browser", required)

    def testDataChangeNeedsReadback(self):
        """Đọc lại đúng cái vừa ghi — bắt họ lỗi mà `status: ok` không bắt được."""
        self.assertIn("dataReadback", requiredCheckNames(POLICY, "dataChange"))

    def testResearchNeedsSources(self):
        """Bài học hội đồng: nhiều model đồng thuận KHÔNG phải bằng chứng."""
        self.assertIn("sourcesCited", requiredCheckNames(POLICY, "research"))

    def testUnknownChangeKindFallsBackToStrictDefault(self):
        """Task không khai loại là Task chưa ai nghĩ kỹ — đòi NHIỀU, không ít."""
        required = requiredCheckNames(POLICY, "chuaBaoGioThayLoaiNay")
        self.assertEqual(set(required),
                         set(requiredCheckNames(POLICY, "default")))
        self.assertTrue(required)


class MissionTestCase(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(prefix="travisMis"),
                                 "mission.sqlite")
        self.conn = openStore(self.path)

    def tearDown(self):
        self.conn.close()


class TestMission(MissionTestCase):

    def testObjectiveIsRequired(self):
        with self.assertRaises(MissionError):
            createMission(self.conn, "   ")

    def testProgressCountsOnlyCompleted(self):
        """`ok` của company nghĩa là "chạy trót lọt", không phải "đã kiểm chứng"."""
        mission = createMission(self.conn, "Panharmon lên top 10 cho 5 từ khoá")
        attachTask(self.conn, mission.missionId, "tsk_1", "completed")
        attachTask(self.conn, mission.missionId, "tsk_2", "verifying")
        attachTask(self.conn, mission.missionId, "tsk_3", "failed")

        progress = missionProgress(self.conn, mission.missionId)
        self.assertEqual(progress["taskCount"], 3)
        self.assertEqual(progress["completedCount"], 1)

    def testUnmeasuredMetricsAreNamedNotZeroed(self):
        """Số liệu chưa ai đo là số liệu CHƯA CÓ — đừng để 0 trông như đã đo (O10)."""
        mission = createMission(self.conn, "Tăng traffic",
                                metrics=("organicClicks", "avgPosition"))
        recordMetric(self.conn, mission.missionId, "organicClicks", "1200")

        progress = missionProgress(self.conn, mission.missionId)
        self.assertEqual(progress["unmeasuredMetrics"], ["avgPosition"])

    def testStalledMissionIsFound(self):
        """Đứng bánh thì IM LẶNG — và im lặng đã để hệ chết 61 giờ không ai biết."""
        mission = createMission(self.conn, "Một mục tiêu bị bỏ quên")
        old = (datetime.now(timezone.utc) - timedelta(days=30)
               ).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.conn.execute("UPDATE mission SET updatedAt = ? WHERE missionId = ?",
                          (old, mission.missionId))
        self.conn.commit()

        stalled = stalledMissions(self.conn, afterDays=7)
        self.assertEqual([m.missionId for m in stalled], [mission.missionId])

    def testCompletedMissionIsNotDoneUntilReported(self):
        """N3 — trạng thái nằm trong sổ KHÔNG PHẢI là thông báo.

        Đây là vụ web todolist: dựng xong, đặt về `choXem`, im lặng — và cùng
        tối admin hỏi "cái web làm sao xem".
        """
        mission = createMission(self.conn, "Dựng trang todolist")
        closeMission(self.conn, mission.missionId, MissionStatus.completed)

        waiting = missionsAwaitingReport(self.conn)
        self.assertEqual([m.missionId for m in waiting], [mission.missionId])

        markReported(self.conn, mission.missionId)
        self.assertEqual(missionsAwaitingReport(self.conn), [])

    def testAbandoningNeedsAReason(self):
        """Bỏ dở mà không nói vì sao thì lần sau lại làm lại từ đầu."""
        mission = createMission(self.conn, "Một thứ sẽ bỏ dở")
        with self.assertRaises(MissionError):
            closeMission(self.conn, mission.missionId,
                         MissionStatus.abandoned, reason="")
        closeMission(self.conn, mission.missionId, MissionStatus.abandoned,
                     reason="Notion đổi API, không đáng theo")

    def testCannotCloseWithNonTerminalStatus(self):
        mission = createMission(self.conn, "Đang chạy")
        with self.assertRaises(MissionError):
            closeMission(self.conn, mission.missionId, MissionStatus.active)


if __name__ == "__main__":
    unittest.main(verbosity=2)
