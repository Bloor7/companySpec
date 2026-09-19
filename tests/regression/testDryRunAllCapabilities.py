#!/usr/bin/env python3
"""Chạy khô MỌI năng lực của MỌI company.

Đây là ca phủ rộng nhất của lưới. Nó không kiểm nghiệp vụ — nó kiểm rằng con
đường từ lời gọi tới company còn thông: manifest đọc được, tên năng lực khớp,
input hợp schema, tiến trình con chạy được, và company trả về JSON đúng hợp
đồng C1.

An toàn vì `--dry-run`: đã soát cả 22 company đều chặn dryRun TRƯỚC khi chạm
handler và trước cả khi lấy token — không mạng, không Notion, không phiếu duyệt.

Đây chính là ca sẽ đỏ nếu việc đổi tên làm gãy một chỗ nào đó.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import (  # noqa: E402
    callDispatch, capabilitiesOf, loadManifests, sampleInputFor,
)

MANIFESTS = loadManifests()

# Năng lực tiêu TIỀN THẬT: không gọi, kể cả dry-run.
#
# dryRun có chặn thật, nhưng nguyên tắc ở đây không phải "chắc là không sao" —
# mà là ca thử không bao giờ đứng gần ví của admin. Rẻ hơn nhiều so với một
# ngày phải đi đối chiếu hoá đơn.
def _isPaid(cap: dict) -> bool:
    return bool(cap.get("paidApi"))


class TestEveryCapabilityIsReachable(unittest.TestCase):

    def testDryRunEveryCapability(self):
        checked, skipped = 0, []
        for companyId in sorted(MANIFESTS):
            spec = MANIFESTS[companyId]
            for name, cap in sorted(capabilitiesOf(spec).items()):
                if _isPaid(cap):
                    skipped.append(f"{companyId}.{name} (paidApi)")
                    continue
                with self.subTest(company=companyId, capability=name):
                    payload = sampleInputFor(cap)
                    # traceSuffix riêng cho từng lớp ca: L4 chống lặp đếm theo
                    # traceId, nên hai lớp dùng chung một trace thì lớp thứ hai
                    # bị chặn — hàng rào đúng, người gọi sai.
                    result = callDispatch(companyId, name, payload, dryRun=True,
                                          traceSuffix="_reach")

                    # Hợp đồng C1 — mọi company trả đúng bộ khoá này.
                    for key in ("taskId", "traceId", "status", "summary"):
                        self.assertIn(key, result,
                                      f"{companyId}.{name}: result thiếu `{key}`")

                    self.assertEqual(
                        result["status"], "ok",
                        f"{companyId}.{name} chạy khô mà không ok: "
                        f"{result.get('summary', '')[:200]} "
                        f"| error={str(result.get('error'))[:200]} "
                        f"| input đã gửi={payload}")
                    checked += 1

        self.assertGreater(checked, 0, "không chạy được năng lực nào")
        print(f"\n  đã chạy khô {checked} năng lực"
              + (f", bỏ qua {len(skipped)} năng lực tốn tiền" if skipped else ""))


class TestCompanyResultContract(unittest.TestCase):
    """C1 — envelope vào stdin, companyResult ra stdout, không lệch."""

    def testStatusIsAlwaysKnown(self):
        known = {"ok", "failed", "rejected", "needsApproval", "needsInput",
                 "budgetExceeded", "scheduled"}
        for companyId in sorted(MANIFESTS):
            spec = MANIFESTS[companyId]
            for name, cap in sorted(capabilitiesOf(spec).items()):
                if _isPaid(cap):
                    continue
                with self.subTest(company=companyId, capability=name):
                    result = callDispatch(companyId, name, sampleInputFor(cap),
                                          traceSuffix="_contract")
                    self.assertIn(
                        result["status"], known,
                        f"{companyId}.{name} trả status lạ: {result['status']!r}. "
                        "Status không nằm trong bộ đã biết thì CEO không xử lý "
                        "được, và nó sẽ đoán.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
