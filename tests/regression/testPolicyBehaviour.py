#!/usr/bin/env python3
"""Hành vi Policy — đóng băng những quyết định quyền hạn đang có.

Đây là bộ ca quan trọng nhất của lưới: nó nói "lời gọi như thế này thì hệ trả
lời thế kia". Lát nữa khi bóc policy ra khỏi gateway/cli/dispatch.py sang core/policy,
những câu trả lời đó phải KHÔNG ĐỔI.

Chạy thật, qua đúng cổng thật (gateway/cli/dispatch.py), không có cờ nào chỉ dành cho
test — bài học "bộ đo tự đứng ngoài phép đo".
"""
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import (  # noqa: E402
    REPO_ROOT, TRACE_PREFIX, callDispatch, capabilitiesOf, loadManifests,
)

# Bỏ company `internal: true` — xem ghi chú trong testDryRunAllCapabilities.py.
MANIFESTS = loadManifests(includeInternal=False)


def _pickCapability(riskTier: str):
    """Tìm một năng lực thật có riskTier cho trước, để ca không phải viết cứng.

    Viết cứng tên company vào test nghĩa là đổi tên company thì test đỏ vì lý
    do sai. Ở đây ta hỏi manifest, đúng nguồn chân lý.
    """
    for companyId in sorted(MANIFESTS):
        for name, cap in sorted(capabilitiesOf(MANIFESTS[companyId]).items()):
            # Bỏ qua thứ tiêu tiền thật: ca thử không được đụng ví admin.
            if cap.get("paidApi"):
                continue
            if cap["riskTier"] == riskTier:
                return companyId, name, cap
    raise unittest.SkipTest(f"không có năng lực nào riskTier={riskTier}")


def tearDownModule():
    """Dọn phiếu duyệt mà chính bộ test sinh ra.

    Không dọn thì admin mở Telegram thấy một đống phiếu chờ do máy đẻ. Dọn được
    vì mọi lời gọi của test mang traceId tiền tố `reg_` — tách bằng NHÃN, không
    bằng cách trốn khỏi sổ.
    """
    # Phiếu duyệt nằm chung backOffice/store.sqlite, KHÔNG phải
    # ops/approvals.sqlite — file đó là xác chết không ai đọc (đã soát
    # 2026-09-19), giữ lại chỉ để lừa người đọc sau này.
    path = os.path.join(REPO_ROOT, "backOffice", "store.sqlite")
    if not os.path.exists(path):
        return
    conn = sqlite3.connect(path)
    conn.execute("DELETE FROM approvalRequest WHERE traceId LIKE ?",
                 (TRACE_PREFIX + "%",))
    conn.commit()
    conn.close()


class TestInputGate(unittest.TestCase):
    """C2.1 / C2.2 / C2.3 — cổng vào chặn thứ không khai báo."""

    def testUnknownCompanyIsRejected(self):
        result = callDispatch("khongCoCongTyNay", "lamGiDo", {})
        self.assertEqual(result["status"], "rejected")

    def testUnknownCapabilityIsRejected(self):
        companyId = sorted(MANIFESTS)[0]
        result = callDispatch(companyId, "nangLucKhongTonTai", {})
        self.assertEqual(result["status"], "rejected")
        self.assertIn("C2.2", result["summary"])

    def testUndeclaredFieldIsRejected(self):
        """`additionalProperties: false` phải thật sự chặn.

        Đây là hàng rào canh con bug đắt nhất dự án: gọi bằng tên trường không
        có trong manifest. Nó phải chặn NGAY, không phải chặn sau khi đã chạy.
        """
        companyId, name, _cap = _pickCapability("read")
        result = callDispatch(companyId, name,
                              {"truongHoanToanBiaRa": "xyz"})
        self.assertEqual(result["status"], "rejected",
                         f"{companyId}.{name} nhận cả trường không khai báo")
        self.assertIn("C2.3", result["summary"])

    def testWrongTypeIsRejected(self):
        """Sai KIỂU cũng phải chặn, không chỉ sai tên."""
        target = None
        for companyId in sorted(MANIFESTS):
            for name, cap in sorted(capabilitiesOf(MANIFESTS[companyId]).items()):
                if cap.get("paidApi"):
                    continue
                props = (cap.get("inputSchema") or {}).get("properties") or {}
                for fieldName, sub in props.items():
                    if sub.get("type") in ("number", "integer"):
                        target = (companyId, name, fieldName)
                        break
                if target:
                    break
            if target:
                break
        if not target:
            self.skipTest("không có trường số nào để thử")
        companyId, name, fieldName = target
        result = callDispatch(companyId, name, {fieldName: "khong-phai-so"})
        self.assertEqual(result["status"], "rejected")


class TestRiskComesFromManifest(unittest.TestCase):
    """G3 — model không tự hạ rủi ro của chính nó."""

    def testWriteNeedsApprovalWithoutToken(self):
        """Việc GHI mà không có chữ ký thì phải dừng lại hỏi."""
        companyId, name, cap = _pickCapability("write")
        payload = _minimalValidInput(cap)
        result = callDispatch(companyId, name, payload, dryRun=False,
                              traceSuffix="_needApproval")
        self.assertEqual(
            result["status"], "needsApproval",
            f"{companyId}.{name} là `write` mà chạy luôn không hỏi duyệt")
        self.assertIn("approvalRequest", result)
        self.assertEqual(result["approvalRequest"]["riskTier"], "write")

    def testApprovalRequestNeverLeaksPayloadHash(self):
        """Biết hash từng là biết cách tự duyệt. Đừng đưa model thứ nó không cần."""
        companyId, name, cap = _pickCapability("write")
        result = callDispatch(companyId, name, _minimalValidInput(cap),
                              dryRun=False, traceSuffix="_noHashLeak")
        if result["status"] != "needsApproval":
            self.skipTest("không sinh được phiếu duyệt để soi")
        self.assertNotIn("payloadHash", result["approvalRequest"])

    def testReadDoesNotNeedApproval(self):
        companyId, name, cap = _pickCapability("read")
        result = callDispatch(companyId, name, _minimalValidInput(cap))
        self.assertNotEqual(result["status"], "needsApproval",
                            f"{companyId}.{name} là `read` mà vẫn đòi duyệt")


class TestScheduledTriggerIsReadOnly(unittest.TestCase):
    """S3 — cron quan sát và chuẩn bị, không hành động."""

    def testScheduledWriteIsRejected(self):
        companyId, name, cap = _pickCapability("write")
        result = callDispatch(companyId, name, _minimalValidInput(cap),
                              dryRun=False,
                              extraArgs=["--issued-by", "scheduledTrigger"],
                              traceSuffix="_cronWrite")
        # Từ 21/09 cron có danh tính `scheduler` (chỉ đọc), nên nó bị chặn ở
        # cổng EMPLOYEE — chạy trước Policy — thay vì ở S3. Hai mã trạng thái
        # khác nhau, cùng một kết cục: cron KHÔNG ghi được.
        #
        # Thứ ca này thật sự canh không phải mã trạng thái mà là CÂU TRẢ LỜI:
        # nó phải nói vì sao CRON nói riêng bị cấm. Chặn sớm hơn không được
        # làm mất lý do thật.
        self.assertIn(result["status"], ("rejected", "denied"),
                      "cron ghi được — S3 thủng")
        self.assertIn("S3", result["summary"],
                      "bị chặn nhưng câu trả lời không nói vì sao CRON bị cấm")


class TestEveryCallLeavesATrace(unittest.TestCase):
    """O5 — lần bị CHẶN cũng là dữ liệu."""

    def testRejectedCallIsLogged(self):
        traceId = TRACE_PREFIX + "auditProof"
        callDispatch("khongCoCongTyNay", "lamGiDo", {},
                     traceSuffix="")  # traceId do harness dựng
        storePath = os.path.join(REPO_ROOT, "backOffice", "store.sqlite")
        conn = sqlite3.connect(storePath)
        rows = conn.execute(
            "SELECT COUNT(*) FROM taskLog WHERE traceId LIKE ?",
            (TRACE_PREFIX + "%",)).fetchone()[0]
        conn.close()
        self.assertGreater(rows, 0,
                           "lời gọi bị từ chối KHÔNG để lại dòng nào trong sổ")


def _minimalValidInput(cap: dict) -> dict:
    from harness import sampleInputFor
    return sampleInputFor(cap)


if __name__ == "__main__":
    unittest.main(verbosity=2)
