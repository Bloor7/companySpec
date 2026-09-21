#!/usr/bin/env python3
"""Council + Secret broker + Isolation — ba hàng rào cuối."""
import os
import sqlite3
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO_ROOT)

from core.contracts import SecretRequest  # noqa: E402
from brains.council import (  # noqa: E402
    CouncilMisuse, Proposal, assertProposalsWereIndependent,
    assertWorthConvening, buildResult, formatForAdmin, unsourcedClaims,
)
from core.permissions import loadEmployees  # noqa: E402
from core.permissions.isolation import (  # noqa: E402
    IsolationBreach, SandboxPolicy, assertWithinPolicy, hostIsAllowed,
    isolationMaturity, pathIsAllowed, policyFromEmployee, processIsAllowed,
)
from core.secrets import (  # noqa: E402
    SecretDenied, activeLeases, auditTrail, issueLease, openStore, redact,
    resolveForProcess, revoke,
)
import core.secrets as secretsModule  # noqa: E402
import core.audit as coreAudit  # noqa: E402
from core.execution import ProcessLimits, buildChildEnvironment  # noqa: E402

EMPLOYEES = loadEmployees()


class TestCouncilIsNotFreeToConvene(unittest.TestCase):
    """Mỗi ghế là một lời gọi model. Họp cho việc vặt là tiền vứt đi."""

    def testTrivialTaskIsRefused(self):
        for trivial in ("typoFix", "formatCode", "readFile", "runTest"):
            with self.subTest(task=trivial):
                with self.assertRaises(CouncilMisuse):
                    assertWorthConvening(trivial, proposalCount=3)

    def testHardTaskIsAllowed(self):
        assertWorthConvening("securityDesign", proposalCount=3)

    def testOneSeatIsNotACouncil(self):
        with self.assertRaises(CouncilMisuse):
            assertWorthConvening("securityDesign", proposalCount=1)


class TestProposalsMustBeIndependent(unittest.TestCase):
    """Đọc của nhau thì ba tiếng nói thành một tiếng vọng."""

    def testTaintedProposalIsRejected(self):
        proposals = (
            Proposal("claude", "đề xuất A"),
            Proposal("gemini", "đồng ý với A", sawOtherProposals=True),
        )
        with self.assertRaises(CouncilMisuse) as ctx:
            assertProposalsWereIndependent(proposals)
        self.assertIn("gemini", str(ctx.exception))

    def testIndependentProposalsPass(self):
        assertProposalsWereIndependent((
            Proposal("claude", "A"), Proposal("gemini", "B")))


class TestConsensusIsNotEvidence(unittest.TestCase):
    """Lớp soát bằng CODE — lớp mà model không phá được.

    Bài học: hội đồng tuôn ra "73% kênh triệu view dùng giọng AI" nghe như tri
    thức, thật ra là văn mẫu. Chúng học từ cùng một mớ chữ nên sai giống nhau.
    """

    def testNumberNotInFactsIsFlagged(self):
        missing = unsourcedClaims(
            conclusion="Nghiên cứu cho thấy 73% kênh triệu view dùng giọng AI.",
            facts="Kênh hiện có 1200 người theo dõi.")
        self.assertIn("73", " ".join(missing))

    def testNumberPresentInFactsIsFine(self):
        self.assertEqual(
            unsourcedClaims("Kênh có 1200 người theo dõi.",
                            "Dữ kiện: 1200 người theo dõi tính tới 19/09."),
            ())

    def testListNumberingIsNotFlagged(self):
        """Đánh số mục ("1." "2.") không phải khẳng định — đừng làm ồn."""
        self.assertEqual(
            unsourcedClaims("1. Làm A\n2. Làm B", facts=""), ())

    def testResultKnowsItIsUntrustworthy(self):
        result = buildResult(
            question="Chiến lược kênh?",
            proposals=(Proposal("claude", "A"), Proposal("gemini", "B")),
            synthesis="Cần 90 ngày để thoát sandbox.",
            critique="", decision="Chờ 90 ngày.",
            facts="Kênh mở ngày 01/09.")
        self.assertFalse(result.isTrustworthy)
        self.assertIn("90", " ".join(result.unverifiedClaims))

    def testUnverifiedClaimsAppearFirstInTheReport(self):
        """Thứ chưa kiểm chứng phải NẰM TRÊN. Nằm dưới thì admin đọc kết luận
        trước rồi tin luôn."""
        result = buildResult(
            question="x", proposals=(Proposal("a", "1"), Proposal("b", "2")),
            synthesis="Tăng 45% lượt xem.", critique="", decision="Làm đi.",
            facts="")
        text = formatForAdmin(result)
        self.assertTrue(text.startswith("⚠ CHƯA KIỂM CHỨNG"))
        self.assertIn("Đồng thuận KHÔNG phải bằng chứng", text)


class SecretTestCase(unittest.TestCase):
    def setUp(self):
        self.conn = openStore(os.path.join(
            tempfile.mkdtemp(prefix="travisSec"), "lease.sqlite"))

    def tearDown(self):
        self.conn.close()


class TestSecretBroker(SecretTestCase):

    def testLeaseCarriesNameNotValue(self):
        """P4 — model biết khoá TỒN TẠI thì không sao; ĐỌC ĐƯỢC nó thì đã rò."""
        lease = issueLease(
            self.conn,
            SecretRequest("forge", "GITHUB_TOKEN", reason="đẩy nhánh phụ"),
            allowedSecretNames=("GITHUB_TOKEN",))
        self.assertEqual(lease.secretName, "GITHUB_TOKEN")
        self.assertFalse(hasattr(lease, "value"))
        self.assertNotIn("value", repr(lease).lower())

    def testUndeclaredSecretIsDenied(self):
        with self.assertRaises(SecretDenied):
            issueLease(
                self.conn,
                SecretRequest("sage", "NOTION_TOKEN", reason="tò mò"),
                allowedSecretNames=())

    def testReasonIsMandatory(self):
        """Sổ không có lý do là sổ không tra được."""
        with self.assertRaises(SecretDenied):
            issueLease(self.conn,
                       SecretRequest("forge", "GITHUB_TOKEN", reason="  "),
                       allowedSecretNames=("GITHUB_TOKEN",))

    def testLeaseExpires(self):
        lease = issueLease(
            self.conn, SecretRequest("forge", "GITHUB_TOKEN", reason="đẩy"),
            allowedSecretNames=("GITHUB_TOKEN",), leaseSeconds=60)
        self.assertTrue(lease.isValidAt())
        self.assertFalse(lease.isValidAt("2099-01-01T00:00:00Z"))

    def testExpiredLeaseResolvesToNothing(self):
        lease = issueLease(
            self.conn, SecretRequest("forge", "GITHUB_TOKEN", reason="đẩy"),
            allowedSecretNames=("GITHUB_TOKEN",), leaseSeconds=60)
        environment = {"GITHUB_TOKEN": "giá-trị-thật"}
        self.assertEqual(
            resolveForProcess((lease,), environment), environment)
        self.assertEqual(
            resolveForProcess((lease,), environment,
                              moment="2099-01-01T00:00:00Z"), {})

    def testRevokedLeaseLeavesActiveList(self):
        lease = issueLease(
            self.conn, SecretRequest("forge", "GITHUB_TOKEN", reason="đẩy"),
            allowedSecretNames=("GITHUB_TOKEN",))
        self.assertEqual(len(activeLeases(self.conn)), 1)
        revoke(self.conn, lease.leaseId)
        self.assertEqual(activeLeases(self.conn), [])

    def testAuditTrailAnswersWhoTookWhatAndWhy(self):
        """§30 — "Which secrets were accessed?" phải trả lời được."""
        issueLease(self.conn,
                   SecretRequest("forge", "GITHUB_TOKEN",
                                 reason="đẩy nhánh feature/seo"),
                   allowedSecretNames=("GITHUB_TOKEN",))
        trail = auditTrail(self.conn)
        self.assertEqual(trail[0]["subject"], "forge")
        self.assertIn("feature/seo", trail[0]["reason"])
        self.assertNotIn("value", trail[0])


class TestBrokerIsLoadBearingNotDecorative(SecretTestCase):
    """Phiếu phải QUYẾT ĐỊNH cái gì đi vào tiến trình con, không chỉ ghi sổ.

    ═══ VÌ SAO CA NÀY QUAN TRỌNG HƠN VẺ NGOÀI CỦA NÓ ═══

    Cách nối sai — và là cách dễ nối nhất — là: cấp phiếu để có dòng trong sổ,
    rồi vẫn bơm secret theo danh sách manifest như cũ. Lúc đó `auditTrail()`
    trả lời rất đẹp cho câu §30 "khoá nào đã bị chạm", trong khi cái phiếu
    không hề kiểm soát gì. Đó là HÀNG RÀO GIẢ, và hàng rào giả hại hơn không
    có hàng rào, vì người đọc sổ sau này sẽ tin nó.

    Nên ca này đo đúng một thứ: **secret không có phiếu thì không đi vào môi
    trường của tiến trình con.**
    """

    def testEnvironmentIsBuiltFromLeasesNotFromTheManifest(self):
        lease = issueLease(
            self.conn,
            SecretRequest("ceo", "NOTION_TOKEN", reason="chạy x.y"),
            allowedSecretNames=("NOTION_TOKEN", "GITHUB_TOKEN"))

        # Manifest khai HAI khoá, broker chỉ cấp phiếu cho MỘT.
        limits = ProcessLimits(
            timeoutSec=10,
            allowedSecretNames=tuple(l.secretName for l in (lease,)))
        parentEnv = {"NOTION_TOKEN": "gt-notion", "GITHUB_TOKEN": "gt-github",
                     "PATH": "/usr/bin"}
        childEnv = buildChildEnvironment(limits, parentEnv)

        self.assertEqual(childEnv.get("NOTION_TOKEN"), "gt-notion")
        self.assertNotIn(
            "GITHUB_TOKEN", childEnv,
            "khoá KHÔNG có phiếu vẫn đi vào tiến trình con — phiếu đang là "
            "một bản ghi trang trí, không phải một cái cổng")

    def testDeniedSecretNeverReachesTheChild(self):
        """Broker từ chối thì khoá phải VẮNG MẶT, không phải vẫn đi kèm."""
        with self.assertRaises(SecretDenied):
            issueLease(self.conn,
                       SecretRequest("sage", "NOTION_TOKEN", reason="tò mò"),
                       allowedSecretNames=())
        childEnv = buildChildEnvironment(
            ProcessLimits(timeoutSec=10, allowedSecretNames=()),
            {"NOTION_TOKEN": "gt-notion", "PATH": "/usr/bin"})
        self.assertNotIn("NOTION_TOKEN", childEnv)

    def testNoLeaseAtAllMeansNoSecretAtAll(self):
        """Company không khai `secrets` thì tiến trình con trắng khoá."""
        childEnv = buildChildEnvironment(
            ProcessLimits(timeoutSec=10, allowedSecretNames=()),
            {"NOTION_TOKEN": "gt", "GEMINI_API_KEY": "gt2", "PATH": "/usr/bin"})
        self.assertEqual(
            [k for k in childEnv if k.endswith(("TOKEN", "KEY"))], [])


class TestSecretAuditSeparatesTestTraffic(SecretTestCase):
    """Sổ "khoá nào đã bị chạm" mà toàn dòng của `tests/run.py` là sổ vô dụng.

    Mỗi lượt `tests/run.py` đi qua hơn 80 năng lực, nên không tách thì lần
    chạm THẬT chìm mất. Theo đúng tiền lệ `evl_` ở `ceoRunLog`: không che đi,
    chỉ tách ra — và vẫn lấy đủ được khi cần.
    """

    def _issue(self, traceId):
        issueLease(self.conn,
                   SecretRequest("ceo", "NOTION_TOKEN", reason="chạy x.y"),
                   allowedSecretNames=("NOTION_TOKEN",), traceId=traceId)

    def testTestTrafficIsHiddenByDefault(self):
        for prefix in secretsModule.TEST_TRACE_PREFIXES:
            self._issue(f"{prefix}abc")
        self._issue("trc_that")

        trail = auditTrail(self.conn)
        self.assertEqual(
            [row["traceId"] for row in trail], ["trc_that"],
            "lưu lượng bộ đo đang lấp sổ tra secret")

    def testNothingIsActuallyHidden(self):
        """Bộ đo tự xoá dấu vết của mình là bộ đo không kiểm được."""
        self._issue("reg_abc")
        self.assertEqual(auditTrail(self.conn), [])
        self.assertEqual(
            len(auditTrail(self.conn, includeTestTraffic=True)), 1)

    def testPrefixListMatchesTheAuditLedger(self):
        """Hai hằng cùng nghĩa ở hai gói — ép chúng khớp, đừng tin là khớp.

        `core.secrets` cố ý KHÔNG import `core.audit` chỉ để lấy một hằng, nên
        có hai bản. Hai bản của cùng một danh sách thì sớm muộn lệch, và lệch
        ở đây nghĩa là một loại lưu lượng bộ đo lọt vào sổ mà không ai thấy.
        """
        chuan = tuple(sorted(coreAudit.TEST_TRACE_PREFIXES))
        self.assertEqual(tuple(sorted(secretsModule.TEST_TRACE_PREFIXES)),
                         chuan)

        # Bản thứ BA và thứ TƯ. `core/events/review.py` từng chép tay và
        # thiếu `drl_` — nên bản soát tuần đếm lỗi CỐ Ý của bộ diễn tập như
        # sự cố thật. Không ca nào canh nó cho tới 21/09.
        import core.events.review as review
        import core.policy.approvals as approvals
        self.assertEqual(tuple(sorted(review.TEST_TRACE_PREFIXES)), chuan,
                         "`core/events/review` lệch danh sách nhãn bộ đo")
        self.assertEqual(tuple(sorted(approvals.TEST_TRACE_PREFIXES)), chuan,
                         "`core/policy/approvals` lệch danh sách nhãn bộ đo")


class TestRedaction(unittest.TestCase):
    """Lớp cuối cùng. Phải dùng tới nó nghĩa là đã rò ở trên rồi."""

    def testKnownSecretValueIsRemoved(self):
        environment = {"NOTION_TOKEN": "ntn_abcdefghijklmnop123456",
                       "LANG": "C.UTF-8"}
        cleaned = redact(
            "lỗi khi gọi với token ntn_abcdefghijklmnop123456", environment)
        self.assertNotIn("ntn_abcdefghijklmnop123456", cleaned)
        self.assertIn("<đã ẩn:NOTION_TOKEN>", cleaned)

    def testNonSecretVariablesAreLeftAlone(self):
        environment = {"LANG": "C.UTF-8xxxxxxxxxxxxx"}
        text = "ngôn ngữ là C.UTF-8xxxxxxxxxxxxx"
        self.assertEqual(redact(text, environment), text)


class TestIsolation(unittest.TestCase):

    def testEmptyListMeansNothingAllowed(self):
        """Rỗng là ĐÓNG. Bài học `whitelistScope: []`, lần thứ n."""
        closed = SandboxPolicy(subject="x")
        self.assertFalse(pathIsAllowed(closed, "/tmp"))
        self.assertFalse(hostIsAllowed(closed, "github.com"))
        self.assertFalse(processIsAllowed(closed, "/usr/bin/git"))

    def testPathTraversalIsBlocked(self):
        policy = SandboxPolicy(subject="forge", allowedPaths=("/tmp",))
        self.assertTrue(pathIsAllowed(policy, "/tmp/project/file.txt"))
        self.assertFalse(pathIsAllowed(policy, "/tmp/../etc/passwd"))

    def testLookalikeDomainIsBlocked(self):
        """`endswith` trần thì `evil-github.com` lọt qua luật `github.com`."""
        policy = SandboxPolicy(subject="forge", allowedHosts=("github.com",))
        self.assertTrue(hostIsAllowed(policy, "github.com"))
        self.assertTrue(hostIsAllowed(policy, "api.github.com"))
        self.assertFalse(hostIsAllowed(policy, "evil-github.com"))
        self.assertFalse(hostIsAllowed(policy, "github.com.evil.net"))

    def testCannotOverridesCallerGenerosity(self):
        """E-2 — người gọi có thể lỡ tay mở rộng; `cannot` thì không được bỏ qua."""
        sage = EMPLOYEES["sage"]
        policy = policyFromEmployee(
            sage, allowedSecretNames=("NOTION_TOKEN", "GITHUB_TOKEN"))
        self.assertEqual(
            policy.allowedSecretNames, (),
            "sage cấm `secret.read` mà vẫn được cấp secret")
        self.assertFalse(policy.mayTouchProduction)

    def testBreachRaisesBeforeRunning(self):
        policy = SandboxPolicy(subject="forge", allowedPaths=("/tmp",),
                               allowedHosts=("github.com",),
                               allowedProcesses=("git",))
        assertWithinPolicy(policy, path="/tmp/x", host="github.com",
                           executable="/usr/bin/git")
        with self.assertRaises(IsolationBreach):
            assertWithinPolicy(policy, path="/etc/passwd")
        with self.assertRaises(IsolationBreach):
            assertWithinPolicy(policy, host="evil.example")
        with self.assertRaises(IsolationBreach):
            assertWithinPolicy(policy, executable="/bin/rm")

    def testMaturityIsHonestAboutWhatIsNotEnforced(self):
        """Hệ nói dối về mức cô lập nguy hiểm hơn hệ không cô lập gì.

        Vì người dùng nó sẽ dám làm những việc đáng ra không dám.
        """
        maturity = isolationMaturity()
        self.assertEqual(maturity["level"], "logical")
        self.assertIn("container/VM", maturity["notEnforced"])
        self.assertIn("KHÔNG chặn mã độc", maturity["meaning"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
