#!/usr/bin/env python3
"""ĐI HẾT DÂY CHUYỀN — Task → Employee → Policy → Execution → Verification → Audit.

═══════════════════════════════════════════════════════════════════════
KHÁC GÌ VỚI tests/regression/
═══════════════════════════════════════════════════════════════════════

`tests/regression/` kiểm TỪNG MẢNH, phần lớn bằng hàm thuần. Bộ này kiểm CẢ
DÂY CHUYỀN, qua đúng `ops/dispatch.py` thật, đúng sổ thật, đúng cổng duyệt
thật. Không có cờ nào chỉ dành cho test.

Một hệ có 185 ca đơn vị xanh vẫn có thể hỏng ở chỗ nối. Bộ này canh chỗ nối.

═══════════════════════════════════════════════════════════════════════
VÌ SAO AN TOÀN
═══════════════════════════════════════════════════════════════════════

Mọi thứ đi qua `travisSelfTestCompany` — company `internal: true`, không gọi
mạng, không giữ secret, và tác động duy nhất là một dòng trong sổ sqlite của
chính nó. CEO không nhìn thấy nó (C5), nên nó cũng không làm loãng danh mục.

Phiếu duyệt và dòng audit do bộ này sinh ra mang tiền tố `e2e_`, dọn ở
`tearDownModule`.
"""
import json
import os
import sqlite3
import subprocess
import sys
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "ops"))

import approvals  # noqa: E402
import core.audit as coreAudit  # noqa: E402
from core.autonomy import earnedAutonomy, recordFromAuditRows  # noqa: E402
from core.contracts import RiskTier  # noqa: E402

COMPANY = "travisSelfTestCompany"
TRACE_PREFIX = "e2e_"
RUN_TOKEN = uuid.uuid4().hex[:8]
STORE = os.path.join(REPO_ROOT, "backOffice", "store.sqlite")


def callDispatch(capability: str, payload: dict, *extraArgs,
                 traceSuffix: str = "") -> dict:
    """Gọi đúng cổng thật. `--allow-internal` là cờ của TERMINAL, không phải
    của CEO — nó tồn tại sẵn từ trước, bộ test không thêm cửa nào."""
    traceId = f"{TRACE_PREFIX}{RUN_TOKEN}_{capability}{traceSuffix}"
    argv = [sys.executable, os.path.join(REPO_ROOT, "ops", "dispatch.py"),
            "call", "--company", COMPANY, "--capability", capability,
            "--input", json.dumps(payload, ensure_ascii=False),
            "--trace", traceId, "--allow-internal", *extraArgs]
    proc = subprocess.run(argv, capture_output=True, text=True,
                          cwd=REPO_ROOT, timeout=120)
    if not proc.stdout.strip():
        raise AssertionError(
            f"dispatch không in gì. stderr(đuôi)={proc.stderr[-1500:]!r}")
    result = json.loads(proc.stdout)
    result["_traceId"] = traceId
    return result


def rowFor(taskId: str) -> dict:
    conn = sqlite3.connect(STORE)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM taskLog WHERE taskId = ?",
                           (taskId,)).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def tearDownModule():
    conn = sqlite3.connect(STORE)
    conn.execute("DELETE FROM approvalRequest WHERE traceId LIKE ?",
                 (TRACE_PREFIX + "%",))
    conn.commit()
    conn.close()


# ══════════════════════════ đường ĐỌC ══════════════════════════

class TestReadPathGoesAllTheWay(unittest.TestCase):
    """Việc ĐỌC: không hỏi ai, chạy, kiểm chứng, ghi sổ đủ."""

    @classmethod
    def setUpClass(cls):
        cls.result = callDispatch("echoRead", {"message": "xin chào Travis"})
        cls.row = rowFor(cls.result["taskId"])

    def testItRan(self):
        self.assertEqual(self.result["status"], "ok")
        self.assertEqual(self.result["output"]["message"], "xin chào Travis")

    def testPolicyAllowedItWithoutAsking(self):
        self.assertEqual(self.row["policyDecision"], "allow")
        self.assertIn("read", self.row["policyReason"])

    def testEvidenceWasProduced(self):
        """V-1 — "xong" phải có bằng chứng, và bằng chứng phải ĐỌC LẠI ĐƯỢC."""
        verification = self.result["verification"]
        self.assertEqual(verification["status"], "verified")
        names = {c["name"]: c["status"] for c in verification["checks"]}
        self.assertEqual(names["statusOk"], "passed")
        self.assertEqual(names["outputSchema"], "passed")
        # Năng lực chỉ ĐỌC thì không có tác động nào để ghi — `skipped`, và đó
        # là câu trả lời đúng, không phải một dấu PASS chưa kiếm được.
        self.assertEqual(names["sideEffectRecorded"], "skipped")

    def testEvidenceIsInTheLedgerNotJustTheReply(self):
        """Bằng chứng chỉ nằm trong câu trả lời thì nó chết theo câu trả lời."""
        saved = json.loads(self.row["verificationJson"])
        self.assertEqual(saved["status"], "verified")

    def testAuditAnswersWhyItWasAllowed(self):
        """§30 — câu hỏi mà bản cũ KHÔNG trả lời được."""
        conn = coreAudit.openStore(STORE)
        try:
            answer = coreAudit.whyWasThisAllowed(conn, self.result["taskId"])
        finally:
            conn.close()
        self.assertIsNotNone(answer)
        self.assertEqual(answer["policyDecision"], "allow")
        self.assertTrue(answer["policyReason"])
        self.assertIn("checks", answer["verification"])


# ══════════════════════════ đường GHI ══════════════════════════

class TestWritePathNeedsASignature(unittest.TestCase):
    """Việc GHI: dừng lại hỏi, và chỉ chạy khi có chữ ký khớp NỘI DUNG."""

    def testWriteStopsAndAsks(self):
        result = callDispatch("recordWrite",
                              {"label": "alpha", "value": "thu nghiem"},
                              traceSuffix="_ask")
        self.assertEqual(result["status"], "needsApproval")
        self.assertIn("approvalRequest", result)
        self.assertTrue(result["approvalRequest"]["consequence"])
        # G8 — `label` là enum ba giá trị, đúng nhóm whitelist được.
        self.assertTrue(result["approvalRequest"]["canWhitelist"])

    def testSignedApprovalLetsItRunAndRecordsTheSideEffect(self):
        payload = {"label": "beta", "value": "co chu ky"}
        asked = callDispatch("recordWrite", payload, traceSuffix="_signed")
        self.assertEqual(asked["status"], "needsApproval")
        approvalId = asked["approvalRequest"]["approvalId"]

        # Admin bấm duyệt.
        approvals.decide(approvalId, "approved")

        done = callDispatch("recordWrite", payload,
                            "--approval-id", approvalId,
                            traceSuffix="_signedRun")
        self.assertEqual(done["status"], "ok",
                         f"chữ ký hợp lệ mà không chạy: {done.get('summary')}")

        # Tác động ra ngoài PHẢI được khai và ghi.
        self.assertTrue(done["sideEffects"])
        names = {c["name"]: c["status"]
                 for c in done["verification"]["checks"]}
        self.assertEqual(names["sideEffectRecorded"], "passed")
        self.assertEqual(done["verification"]["status"], "verified")

        row = rowFor(done["taskId"])
        self.assertEqual(row["policyDecision"], "allowWithVerify")

    def testSignatureIsLockedToContent(self):
        """G4 — đổi nội dung là chữ ký hết giá trị.

        Không có luật này thì "duyệt ghi alpha" cũng duyệt luôn "ghi gamma".
        """
        asked = callDispatch("recordWrite",
                             {"label": "alpha", "value": "noi dung goc"},
                             traceSuffix="_lock")
        approvalId = asked["approvalRequest"]["approvalId"]
        approvals.decide(approvalId, "approved")

        sneaky = callDispatch("recordWrite",
                              {"label": "gamma", "value": "noi dung KHAC"},
                              "--approval-id", approvalId,
                              traceSuffix="_lockAbuse")
        self.assertNotEqual(
            sneaky["status"], "ok",
            "chữ ký cho một nội dung lại mở được một nội dung khác")


# ══════════════════════════ EMPLOYEE ══════════════════════════

class TestEmployeeBoundaryHoldsEndToEnd(unittest.TestCase):

    def testSageCannotWriteThroughDispatch(self):
        """`sage` không ghi được gì, ở đâu cả — và điều đó được giữ bằng
        QUYỀN HẠN, không bằng lời dặn trong prompt (P2)."""
        result = callDispatch("recordWrite",
                              {"label": "alpha", "value": "sage thu ghi"},
                              "--employee", "sage", traceSuffix="_sageWrite")
        self.assertEqual(result["status"], "denied")
        self.assertIn("sage", result["summary"])

    def testSageCannotEvenReadTheAdminsDatabases(self):
        """CỐ Ý, và đây là tuyến phòng thủ thứ hai.

        `sage` là employee tiếp xúc chữ từ trang lạ — ranh giới mỏng nhất của
        hệ. Nó chỉ có `web.read` và `filesystem.read`, KHÔNG có `database.read`.

        Nghĩa là kể cả khi một trang web dụ được nó, nó cũng không đọc nổi sổ
        chi tiêu, ví hay nhật ký của admin — không có gì để mang đi. Chặn ở
        tầng QUYỀN thì không phụ thuộc việc model có nghe lời hay không (P2).

        Ca này ghi lại ý định. Ai thấy nó đỏ vì vừa thêm `database.read` cho
        sage thì hãy đọc đoạn trên trước khi sửa ca.
        """
        result = callDispatch("echoRead", {"message": "sage thu doc so"},
                              "--employee", "sage", traceSuffix="_sageRead")
        self.assertEqual(result["status"], "denied")

    def testSentinelCanReadBecauseAuditingNeedsIt(self):
        """`sentinel` ĐỌC được mọi thứ — soát mà không nhìn được thì soát gì.

        Đổi lại, nó không SỬA được thứ nó vừa soát. Người gác cửa mà tự mở cửa
        cho mình thì không còn là người gác cửa.
        """
        readOk = callDispatch("echoRead", {"message": "sentinel doc"},
                              "--employee", "sentinel",
                              traceSuffix="_sentinelRead")
        self.assertEqual(readOk["status"], "ok")

        writeBlocked = callDispatch("recordWrite",
                                    {"label": "alpha", "value": "sentinel sua"},
                                    "--employee", "sentinel",
                                    traceSuffix="_sentinelWrite")
        self.assertEqual(writeBlocked["status"], "denied")

    def testDenialIsRecordedWithTheEmployeeName(self):
        """O5 — lần bị chặn cũng là dữ liệu, và phải biết CHẶN AI."""
        result = callDispatch("recordWrite",
                              {"label": "alpha", "value": "x"},
                              "--employee", "sage", traceSuffix="_sageAudit")
        row = rowFor(result["taskId"])
        self.assertEqual(row["employeeId"], "sage")
        self.assertEqual(row["policyDecision"], "deny")


# ══════════════════════════ HỎNG thì phải BÁO ĐƯỢC ══════════════════════════

class TestFailuresNeverSlamTheDoor(unittest.TestCase):
    """O8 — hỏng kiểu gì cũng phải trả về thứ CEO đọc được."""

    def testTimeoutBecomesReportableResult(self):
        result = callDispatch("failOnPurpose", {"mode": "timeout"},
                              traceSuffix="_timeout")
        self.assertEqual(result["status"], "budgetExceeded")
        self.assertTrue(result["summary"])

    def testBadOutputIsCaughtBySchema(self):
        result = callDispatch("failOnPurpose", {"mode": "badOutput"},
                              traceSuffix="_badOutput")
        self.assertEqual(result["status"], "failed")
        self.assertIn("C2.3", result["summary"])

    def testCrashKeepsTheLastLineOfTheTraceback(self):
        """Cắt log từ ĐẦU là mất đúng dòng nói hỏng vì cái gì."""
        result = callDispatch("failOnPurpose", {"mode": "crash"},
                              traceSuffix="_crash")
        self.assertEqual(result["status"], "failed")
        self.assertIn("SelfTestCrash", result["summary"],
                      "mất dòng cuối của traceback — log bị cắt từ đầu")

    def testNeedsInputIsItsOwnAnswer(self):
        """"Thiếu dữ kiện" KHÁC "hỏng" — gộp lại thì CEO thử lại thay vì hỏi."""
        result = callDispatch("failOnPurpose", {"mode": "needsInput"},
                              traceSuffix="_needsInput")
        self.assertEqual(result["status"], "needsInput")

    def testEveryFailureStillLeavesATrace(self):
        for mode in ("badOutput", "crash", "needsInput"):
            with self.subTest(mode=mode):
                result = callDispatch("failOnPurpose", {"mode": mode},
                                      traceSuffix=f"_trace{mode}")
                row = rowFor(result["taskId"])
                self.assertTrue(row, f"{mode} không để lại dòng nào trong sổ")
                self.assertTrue(row["policyDecision"])


# ══════════════════════════ AUTONOMY đọc từ sổ THẬT ══════════════════════════

class TestAutonomyReadsRealHistory(unittest.TestCase):
    """Mức tự chủ tính từ lịch sử ĐO ĐƯỢC, không nhận từ model."""

    def testTrackRecordComesFromTheLedger(self):
        for index in range(3):
            callDispatch("echoRead", {"message": f"lan {index}"},
                         traceSuffix=f"_auto{index}")

        conn = coreAudit.openStore(STORE)
        try:
            rows = coreAudit.trackRecordRows(conn, COMPANY, "echoRead")
        finally:
            conn.close()

        self.assertGreaterEqual(len(rows), 3)
        record = recordFromAuditRows(COMPANY, "echoRead", rows)
        self.assertGreaterEqual(record.totalRuns, 3)

        # `ok` của company KHÔNG phải `completed` — chỉ Verification mới đẩy
        # được lên đó. Nên mức kiếm được vẫn là 1, và đó là câu trả lời ĐÚNG:
        # hệ chưa có đường nào đóng dấu `completed` vào sổ.
        self.assertEqual(earnedAutonomy(record, RiskTier.read), 1,
                         "mức tự chủ nhảy lên trong khi sổ chưa có dòng nào "
                         "`completed` — ai đó đang đếm `ok` là thành công")


# ══════════════════════════ không có đường vòng ══════════════════════════

class TestNoCallEscapesPolicy(unittest.TestCase):

    def testEveryCallFromThisRunHasAPolicyDecision(self):
        """Lời gọi không có quyết định policy nghĩa là có đường vào hệ mà
        không qua cửa — thứ nguy hiểm nhất có thể tồn tại ở đây."""
        conn = sqlite3.connect(STORE)
        conn.row_factory = sqlite3.Row
        try:
            missing = [dict(r) for r in conn.execute(
                "SELECT taskId, capability, status FROM taskLog "
                "WHERE traceId LIKE ? AND policyDecision IS NULL",
                (f"{TRACE_PREFIX}{RUN_TOKEN}%",))]
        finally:
            conn.close()
        self.assertEqual(
            missing, [],
            f"{len(missing)} lời gọi không qua Policy: {missing[:3]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
