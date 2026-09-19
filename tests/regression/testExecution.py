#!/usr/bin/env python3
"""Executor — ép nó vào đúng những tình huống đã gây sự cố thật.

Mỗi ca ở đây tương ứng một dòng trong bảng bẫy của CLAUDE.md. Chúng chạy bằng
company GIẢ dựng trong thư mục tạm, nên nhanh, không mạng, không đụng gì.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO_ROOT)

from core.execution import (  # noqa: E402
    ProcessLimits, buildChildEnvironment, looksSuccessful, runCompanyProcess,
    sideEffectsOf, warnIfWorldAlreadyChanged,
)

ENVELOPE = {"taskId": "tsk_x", "traceId": "trc_x", "capability": "doThing",
            "input": {}, "policy": {"dryRun": False}}


class FakeCompany:
    """Dựng một company giả một dòng, chạy được thật."""

    def __init__(self, body: str):
        self.directory = tempfile.mkdtemp(prefix="travisExec")
        self.path = os.path.join(self.directory, "main.py")
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(body)

    def cleanup(self):
        shutil.rmtree(self.directory, ignore_errors=True)


class TestSecretScoping(unittest.TestCase):
    """C2.4 — company chỉ nhận đúng secret nó đã khai."""

    def testUndeclaredSecretIsNotPassed(self):
        parent = {"PATH": "/bin", "NOTION_TOKEN": "bí mật",
                  "OPENAI_KEY": "cũng bí mật", "HOME": "/home/x"}
        limits = ProcessLimits(timeoutSec=10,
                               allowedSecretNames=("NOTION_TOKEN",))
        childEnv = buildChildEnvironment(limits, parent)
        self.assertIn("NOTION_TOKEN", childEnv)
        self.assertNotIn(
            "OPENAI_KEY", childEnv,
            "company không khai OPENAI_KEY mà vẫn nhận được — C2.4 thủng, và "
            "'mỗi company một phạm vi' chỉ còn là lời nói")

    def testNoBlanketEnvironmentLeak(self):
        parent = {"PATH": "/bin", "SOME_PRIVATE_THING": "x"}
        childEnv = buildChildEnvironment(ProcessLimits(timeoutSec=10), parent)
        self.assertNotIn("SOME_PRIVATE_THING", childEnv)


class TestDoorNeverSlamsShut(unittest.TestCase):
    """O8 — cửa vào không được phép sập. LUÔN trả về thứ báo được."""

    def testTimeoutReturnsReportableResult(self):
        """Company treo → `budgetExceeded`, KHÔNG phải một cục traceback.

        Đây là vụ 12:57:14: admin bấm duyệt, hệ treo, 600 giây sau văng
        TimeoutExpired. Admin chờ 10 phút, mã duyệt đã tiêu, việc không chạy.
        """
        company = FakeCompany("import time\ntime.sleep(30)\n")
        try:
            result = runCompanyProcess(
                company.path, sys.executable, ENVELOPE,
                ProcessLimits(timeoutSec=3))
        finally:
            company.cleanup()
        self.assertEqual(result["status"], "budgetExceeded")
        self.assertIn("summary", result)
        self.assertTrue(result["summary"])

    def testMissingEntrypointIsReported(self):
        """Thiếu hẳn cái lệnh để chạy — tiền lệ: thiếu `claude` sập cửa vào."""
        result = runCompanyProcess(
            "/khong/ton/tai/main.py", "/khong/ton/tai/python", ENVELOPE,
            ProcessLimits(timeoutSec=5))
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["summary"])

    def testGarbageStdoutIsReported(self):
        company = FakeCompany("print('không phải JSON')\n")
        try:
            result = runCompanyProcess(
                company.path, sys.executable, ENVELOPE,
                ProcessLimits(timeoutSec=10))
        finally:
            company.cleanup()
        self.assertEqual(result["status"], "failed")
        self.assertIn("không phải JSON", result["summary"])


class TestErrorLogIsCutFromTail(unittest.TestCase):
    """Traceback Python để LOẠI LỖI ở dòng cuối — cắt từ đầu là mất nó."""

    def testLastLineOfTracebackSurvives(self):
        company = FakeCompany(
            "import sys\n"
            "sys.stderr.write('x' * 5000 + chr(10))\n"
            "sys.stderr.write('ValueError: đây là dòng nói hỏng vì cái gì' + chr(10))\n"
            "sys.exit(1)\n")
        try:
            result = runCompanyProcess(
                company.path, sys.executable, ENVELOPE,
                ProcessLimits(timeoutSec=10))
        finally:
            company.cleanup()
        self.assertEqual(result["status"], "failed")
        self.assertIn(
            "đây là dòng nói hỏng vì cái gì", result["summary"],
            "log bị cắt từ ĐẦU nên mất đúng dòng cần đọc — đây là bug poller "
            "ghi stderr[:300] ngày trước")


class TestExitCodeZeroIsNotSuccess(unittest.TestCase):
    """Mã thoát 0 KHÔNG có nghĩa là chạy được."""

    def testStatusOkWithErrorFlagIsNotSuccess(self):
        self.assertFalse(looksSuccessful(
            {"status": "ok", "is_error": True, "result": "Failed to authenticate"}))
        self.assertFalse(looksSuccessful(
            {"status": "ok", "isError": True}))
        self.assertFalse(looksSuccessful(
            {"status": "ok", "error": "có lỗi nhưng vẫn khai ok"}))
        self.assertTrue(looksSuccessful({"status": "ok"}))

    def testNonOkStatusIsNeverSuccess(self):
        for status in ("failed", "rejected", "needsApproval", "needsInput",
                       "budgetExceeded"):
            with self.subTest(status=status):
                self.assertFalse(looksSuccessful({"status": status}))


class TestSideEffects(unittest.TestCase):

    def testReadsBothSpellingsOfReversible(self):
        """Hợp đồng C1 với 22 company đang chạy khai `reversible`; §7 muốn
        `isReversible`. Đọc cả hai, để không phải bắt 22 company sửa cùng lúc."""
        effects = sideEffectsOf({"sideEffects": [
            {"type": "notion.page", "target": "abc", "reversible": True},
            {"type": "telegram.send", "target": "x", "isReversible": False},
        ]})
        self.assertEqual(len(effects), 2)
        self.assertTrue(effects[0].isReversible)
        self.assertFalse(effects[1].isReversible)

    def testWarnsWhenWorldAlreadyChanged(self):
        """Output sai schema NHƯNG việc đã làm → phải nói rõ ĐỪNG LÀM LẠI.

        2026-08-04: bảng kế hoạch ĐƯỢC TẠO trên Notion trong khi CEO báo "chưa
        được tạo", admin thử lại, thành ra làm hai lần.
        """
        warning = warnIfWorldAlreadyChanged(
            {"sideEffects": [{"type": "notion.page", "target": "abc"}]})
        self.assertIn("ĐỪNG làm lại", warning)
        self.assertEqual(warnIfWorldAlreadyChanged({"sideEffects": []}), "")


class TestHappyPath(unittest.TestCase):

    def testWellBehavedCompanyRoundTrips(self):
        company = FakeCompany(
            "import json, sys\n"
            "env = json.load(sys.stdin)\n"
            "print(json.dumps({'taskId': env['taskId'], "
            "'traceId': env['traceId'], 'status': 'ok', "
            "'output': {'echo': env['capability']}, 'summary': 'xong', "
            "'sideEffects': []}))\n")
        try:
            result = runCompanyProcess(
                company.path, sys.executable, ENVELOPE,
                ProcessLimits(timeoutSec=10))
        finally:
            company.cleanup()
        self.assertTrue(looksSuccessful(result))
        self.assertEqual(result["output"]["echo"], "doThing")
        self.assertIn("durationMs", result["usage"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
