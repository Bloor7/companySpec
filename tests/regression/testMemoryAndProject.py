#!/usr/bin/env python3
"""Memory + Project — ba luật trí nhớ phải đứng bằng code, không bằng lời dặn."""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO_ROOT)

from core.contracts import MemoryItem, MemoryKind, MemoryTier, utcNow  # noqa: E402
from core.memory import (  # noqa: E402
    MemoryValidationError, SecretInMemoryError, expiringSoon, looksLikeSecret,
    newDecision, newFact, newInference, openStore, recall, remember,
    summariseForPrompt, supersede,
)
from core.registry import (  # noqa: E402
    isProtectedBranch, loadProjects, mayEmployeeWorkOn, workspaceIsSafe,
)


def _inDays(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)
            ).strftime("%Y-%m-%dT%H:%M:%SZ")


class MemoryTestCase(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(prefix="travisMem"),
                                 "memory.sqlite")
        self.conn = openStore(self.path)

    def tearDown(self):
        self.conn.close()


class TestInferenceIsNeverAFact(MemoryTestCase):
    """M-1 — suy đoán không được cất như sự thật."""

    def testInferenceWithoutConfidenceIsRejected(self):
        bad = MemoryItem(tier=MemoryTier.system, kind=MemoryKind.inference,
                         content="Hydration có thể là nguyên nhân",
                         source="đoán")
        with self.assertRaises(MemoryValidationError):
            remember(self.conn, bad)

    def testInferenceWithoutSourceIsRejected(self):
        bad = MemoryItem(tier=MemoryTier.system, kind=MemoryKind.inference,
                         content="Có lẽ do cache", confidence=0.5)
        with self.assertRaises(MemoryValidationError):
            remember(self.conn, bad)

    def testFactNeedsNeither(self):
        remember(self.conn, newFact(MemoryTier.system, "Panharmon dùng Next.js"))
        self.assertEqual(len(recall(self.conn, MemoryTier.system)), 1)

    def testPromptLabelsInferenceDistinctly(self):
        """Bỏ nhãn đi là mời model nói suy đoán bằng giọng của sự thật.

        Đây đúng là lỗi hội đồng từng mắc: "73% kênh triệu view dùng giọng AI"
        nghe như tri thức, thật ra là văn mẫu.
        """
        text = summariseForPrompt([
            newFact(MemoryTier.project, "Dự án dùng Next.js"),
            newInference(MemoryTier.project, "Hydration gây chậm", 0.6,
                         "quan sát log"),
        ])
        self.assertIn("[sự thật]", text)
        self.assertIn("suy đoán", text)
        self.assertIn("0.6", text)
        self.assertIn("nguồn: quan sát log", text)


class TestSecretIsNeverMemory(MemoryTestCase):
    """M-3 / P4 — chặn ở CỬA VÀO, không dọn ở cửa ra."""

    def testObviousSecretsAreBlocked(self):
        for leaked in (
            "khoá là sk-proj-abcdefghijklmnopqrstuvwx1234",
            "token ntn_1234567890abcdefghijklmnopqrst",
            "NOTION_TOKEN = secret_abcdefghijklmnop",
            "AIzaSyA1234567890abcdefghijklmnopqrstuv",
            "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        ):
            with self.subTest(text=leaked[:24]):
                self.assertTrue(looksLikeSecret(leaked))
                with self.assertRaises(SecretInMemoryError):
                    remember(self.conn, newFact(MemoryTier.system, leaked))

    def testNormalTextIsNotMistakenForSecret(self):
        """Bắt quá tay cũng là hỏng: admin không cất được thứ mình cần cất."""
        for ordinary in (
            "Admin dậy lúc 5h30 và thích cà phê đen",
            "Dự án Panharmon dùng Supabase cho nội dung",
            "Quyết định: không dùng Prisma",
        ):
            with self.subTest(text=ordinary[:24]):
                self.assertFalse(looksLikeSecret(ordinary))


class TestExpiry(MemoryTestCase):
    """M-2 — thứ chỉ đúng trong một quãng phải có ngày rụng."""

    def testExpiredItemDisappearsFromRecall(self):
        item = newFact(MemoryTier.personal, "Đang trông khách sạn thay người")
        item.expiresAt = _inDays(-1)
        remember(self.conn, item)
        self.assertEqual(recall(self.conn, MemoryTier.personal), [])

    def testUnexpiredItemStays(self):
        item = newFact(MemoryTier.personal, "Đang học tiếng Trung")
        item.expiresAt = _inDays(30)
        remember(self.conn, item)
        self.assertEqual(len(recall(self.conn, MemoryTier.personal)), 1)

    def testExpiringSoonWarnsBeforeItVanishes(self):
        """Không có bước này thì M-2 sửa một lỗi bằng cách tạo một lỗi khác:
        quên mất thứ vẫn còn đúng."""
        soon = newFact(MemoryTier.personal, "Đang trông khách sạn")
        soon.expiresAt = _inDays(3)
        later = newFact(MemoryTier.personal, "Đang học tiếng Trung")
        later.expiresAt = _inDays(90)
        remember(self.conn, soon)
        remember(self.conn, later)

        warnings = expiringSoon(self.conn, withinDays=7)
        self.assertEqual([w.content for w in warnings], ["Đang trông khách sạn"])


class TestScoping(MemoryTestCase):
    """Trí nhớ hai dự án không được trộn vào nhau."""

    def testProjectMemoryNeedsScope(self):
        with self.assertRaises(MemoryValidationError):
            remember(self.conn, newFact(MemoryTier.project, "dùng Next.js"))

    def testScopesStaySeparate(self):
        remember(self.conn, newFact(MemoryTier.project, "dùng Next.js"),
                 scopeId="panharmon")
        remember(self.conn, newFact(MemoryTier.project, "dùng Astro"),
                 scopeId="partycards")
        self.assertEqual(
            [i.content for i in recall(self.conn, MemoryTier.project,
                                       scopeId="panharmon")],
            ["dùng Next.js"])


class TestSupersede(MemoryTestCase):
    """Đổi ý phải ĐỌC LẠI ĐƯỢC, không phải ghi đè."""

    def testOldDecisionIsKeptButNotRecalled(self):
        old = newDecision(MemoryTier.project, "Dùng Prisma")
        remember(self.conn, old, scopeId="panharmon")
        new = newDecision(MemoryTier.project, "KHÔNG dùng Prisma")
        supersede(self.conn, old.memoryId, new, scopeId="panharmon")

        current = [i.content for i in recall(self.conn, MemoryTier.project,
                                             scopeId="panharmon")]
        self.assertEqual(current, ["KHÔNG dùng Prisma"])
        # Cái cũ vẫn nằm trong sổ — đó là câu trả lời cho "trước đây tin gì".
        stillThere = self.conn.execute(
            "SELECT COUNT(*) FROM memoryItem").fetchone()[0]
        self.assertEqual(stillThere, 2)


class TestProjectRegistry(unittest.TestCase):

    def setUp(self):
        self.projects = loadProjects()

    def testPanharmonLoads(self):
        self.assertIn("panharmon", self.projects)

    def testProtectedBranchIsRespected(self):
        """R2 — nhánh `main` chỉ admin ghi."""
        panharmon = self.projects["panharmon"]
        self.assertTrue(isProtectedBranch(panharmon, panharmon.protectedBranch))
        self.assertFalse(isProtectedBranch(panharmon, "feature/seo"))

    def testEmptyAllowListMeansNobodyYet(self):
        """Rỗng là ĐÓNG. Bài học `whitelistScope: []`."""
        panharmon = self.projects["panharmon"]
        if panharmon.allowedEmployees:
            self.skipTest("dự án đã khai danh sách employee")
        self.assertFalse(mayEmployeeWorkOn(panharmon, "forge"))

    def testAdminWorkspaceIsNeverSafe(self):
        """Company KHÔNG trỏ vào thư mục làm việc thật của admin.

        Ở đó có việc dở và `.env.local` chứa khoá Supabase, Resend thật.
        """
        panharmon = self.projects["panharmon"]
        home = os.path.expanduser("~")
        self.assertFalse(
            workspaceIsSafe(panharmon, os.path.join(home, "panharmon")))
        self.assertTrue(
            workspaceIsSafe(panharmon, "/workspace/panharmon-clone"))
        self.assertFalse(workspaceIsSafe(panharmon, ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
