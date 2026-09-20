#!/usr/bin/env python3
"""Đối chiếu core/policy với gateway/cli/dispatch.py — cho MỌI năng lực thật.

VÌ SAO CA NÀY LÀ BẮT BUỘC

Bóc luật ra một file mới mà không chứng minh nó trả lời GIỐNG bản đang chạy
thì ta không "tách tầng" — ta tạo ra NGUỒN SỰ THẬT THỨ HAI. Và dự án này đã
trả giá cho đúng chuyện đó: "hạn mức ăn uống còn bao nhiêu" ra 1.091.154đ theo
CEO và 4.789.000đ theo báo cáo tối. Cả hai đều chạy, đều không lỗi, và admin
không có cách nào biết tin cái nào.

Nên chừng nào `gateway/cli/dispatch.py` còn là bản đang chạy, ca này phải xanh.

Nó cũng là điều kiện để BỎ bản cũ: khi dispatch đã gọi vào core/policy thì ca
này thành phép kiểm hồi quy bình thường, không còn là phép đối chiếu.
"""
import os
import sqlite3
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO_ROOT)

from harness import (  # noqa: E402
    TRACE_PREFIX, callDispatch, capabilitiesOf, loadManifests, sampleInputFor,
)
from core.contracts import (  # noqa: E402
    Capability, IssuedBy, PolicyDecision, PolicyRequest,
)
from core.policy import decide  # noqa: E402

# Bỏ company `internal: true` — xem ghi chú trong testDryRunAllCapabilities.py.
MANIFESTS = loadManifests(includeInternal=False)


def tearDownModule():
    """Dọn phiếu duyệt do chính ca này đẻ ra — tách bằng nhãn `reg_`."""
    path = os.path.join(REPO_ROOT, "backOffice", "store.sqlite")
    if not os.path.exists(path):
        return
    conn = sqlite3.connect(path)
    conn.execute("DELETE FROM approvalRequest WHERE traceId LIKE ?",
                 (TRACE_PREFIX + "%",))
    conn.commit()
    conn.close()


def _whitelistRuleFor(companyId: str, name: str, payload: dict):
    """Quyền đứng admin đã cấp cho đúng lời gọi này, hoặc None.

    Hỏi thẳng `core/policy/approvals.py` chứ không tự đọc lại whitelist.jsonl: viết bản
    thứ hai của cùng một phép so là tạo ra nguồn sự thật thứ hai, và nó sẽ lệch
    đúng vào hôm ai đó sửa một bên.
    """
    sys.path.insert(0, os.path.join(REPO_ROOT, "core", "policy"))
    import approvals  # noqa: E402

    raw = capabilitiesOf(MANIFESTS[companyId])[name]
    try:
        rule = approvals.whitelist_match(companyId, name, payload, raw)
    except Exception:
        return None
    return rule["ruleId"] if rule else None


def _capabilitiesToCheck():
    """Mọi năng lực, trừ thứ tiêu TIỀN THẬT.

    Năng lực `paidApi` bị loại vì ca không được đứng gần ví admin — kể cả khi
    biết chắc đường đó không tiêu gì.
    """
    for companyId in sorted(MANIFESTS):
        spec = MANIFESTS[companyId]
        for name, raw in sorted(capabilitiesOf(spec).items()):
            if raw.get("paidApi"):
                continue
            yield companyId, name, Capability.fromManifest(companyId, raw)


class TestDryRunParity(unittest.TestCase):
    """Chạy khô: dispatch cho qua, policy nói `dryRun`."""

    def testEveryCapability(self):
        for companyId, name, capability in _capabilitiesToCheck():
            with self.subTest(company=companyId, capability=name):
                outcome = decide(PolicyRequest(
                    identity=IssuedBy.admin,
                    capability=capability,
                    inputValue=sampleInputFor(
                        {"inputSchema": capability.inputSchema}),
                    isDryRun=True))
                self.assertIs(outcome.decision, PolicyDecision.dryRun)
                self.assertTrue(outcome.isAllowed)


class TestApprovalParity(unittest.TestCase):
    """Cửa duyệt: hai bên phải nói CÙNG một câu, cho từng năng lực."""

    def testWhoNeedsApproval(self):
        """⚠ ĐỌC TRƯỚC KHI SỬA CA NÀY.

        Ca này gọi dispatch KHÔNG dry-run, nghĩa là nếu policy cho qua thì
        company CHẠY THẬT. Bản đầu của ca đã làm đúng thế: 10 năng lực ghi đã
        được admin whitelist nên dispatch không hỏi mà thi hành luôn.

        Lần đó không mất gì, nhờ hai lớp may mắn chứ không nhờ thiết kế:
        `gateway/cli/dispatch.py` KHÔNG nạp `ops/.env`, nên chạy từ shell trần là không
        có `NOTION_TOKEN` và mọi company dùng Notion ngã ở cửa token trước khi
        chạm mạng. Đừng dựa vào điều đó: `xuongCompany` chỉ dùng sqlite local,
        và nó ĐÃ chạy thật.

        Nên: năng lực nào whitelist khớp thì KHÔNG gọi dispatch. Ta biết trước
        dispatch sẽ cho qua, và "biết trước rồi vẫn bấm nút" là cách người ta
        làm hỏng dữ liệu thật.
        """
        mismatches, granted = [], 0
        for companyId, name, capability in _capabilitiesToCheck():
            payload = sampleInputFor({"inputSchema": capability.inputSchema})
            rule = _whitelistRuleFor(companyId, name, payload)

            outcome = decide(PolicyRequest(
                identity=IssuedBy.admin,
                capability=capability,
                inputValue=payload,
                # Đây là chỗ bản đầu sai: hỏi core mà GIẤU nó thông tin
                # whitelist mà dispatch có. Hai bên biết khác nhau thì so sánh
                # không nói lên điều gì.
                whitelistGrant=rule))

            if rule:
                granted += 1
                with self.subTest(company=companyId, capability=name):
                    self.assertTrue(
                        outcome.isAllowed,
                        f"{companyId}.{name}: admin đã whitelist mà core vẫn "
                        f"chặn ({outcome.decision.value})")
                continue

            result = callDispatch(companyId, name, payload, dryRun=False,
                                  traceSuffix="_parity")
            coreWantsApproval = (
                outcome.decision is PolicyDecision.allowWithApproval)
            dispatchWantsApproval = result["status"] == "needsApproval"

            if coreWantsApproval != dispatchWantsApproval:
                mismatches.append(
                    f"{companyId}.{name} (riskTier={capability.riskTier.value}"
                    f", paidApi={bool(capability.paidApi)}): "
                    f"core={'hỏi' if coreWantsApproval else 'không hỏi'} · "
                    f"dispatch={'hỏi' if dispatchWantsApproval else 'không hỏi'}"
                    f" [{result['status']}]")

        self.assertFalse(mismatches, "\n  " + "\n  ".join(mismatches))
        print(f"\n  {granted} năng lực đã whitelist — không gọi dispatch")

    def testWhitelistButtonParity(self):
        """Nút "Luôn cho phép" hiện ở đúng những chỗ giống nhau.

        Đây là chỗ `whitelistScope: []` từng lừa cả người đọc lẫn người viết.
        """
        mismatches = []
        for companyId, name, capability in _capabilitiesToCheck():
            payload = sampleInputFor({"inputSchema": capability.inputSchema})
            # Cùng lý do như ca trên: whitelist khớp thì dispatch sẽ CHẠY THẬT.
            if _whitelistRuleFor(companyId, name, payload):
                continue
            result = callDispatch(companyId, name, payload, dryRun=False,
                                  traceSuffix="_whitelistParity")
            if result["status"] != "needsApproval":
                continue
            dispatchSaysCan = bool(
                result["approvalRequest"].get("canWhitelist"))
            outcome = decide(PolicyRequest(
                identity=IssuedBy.admin,
                capability=capability,
                inputValue=payload))
            if outcome.canWhitelist != dispatchSaysCan:
                mismatches.append(
                    f"{companyId}.{name}: core={outcome.canWhitelist} · "
                    f"dispatch={dispatchSaysCan}")
        self.assertFalse(mismatches, "\n  " + "\n  ".join(mismatches))


class TestScheduledTriggerParity(unittest.TestCase):
    """S3 — cron chỉ được đọc. Hai bên phải chặn đúng cùng một tập."""

    def testCronWriteIsDeniedByBoth(self):
        mismatches = []
        for companyId, name, capability in _capabilitiesToCheck():
            payload = sampleInputFor({"inputSchema": capability.inputSchema})

            outcome = decide(PolicyRequest(
                identity=IssuedBy.scheduledTrigger,
                capability=capability,
                inputValue=payload))
            coreDenies = outcome.decision is PolicyDecision.deny

            result = callDispatch(companyId, name, payload, dryRun=False,
                                  extraArgs=["--issued-by", "scheduledTrigger"],
                                  traceSuffix="_cronParity")
            dispatchDenies = (result["status"] == "rejected"
                              and "S3" in result.get("summary", ""))

            if coreDenies != dispatchDenies:
                mismatches.append(
                    f"{companyId}.{name} (riskTier={capability.riskTier.value}): "
                    f"core={'chặn' if coreDenies else 'cho'} · "
                    f"dispatch={'chặn' if dispatchDenies else 'cho'} "
                    f"[{result['status']}]")

        self.assertFalse(mismatches, "\n  " + "\n  ".join(mismatches))


class TestPolicyIsDeterministic(unittest.TestCase):
    """Cùng đầu vào → cùng quyết định. Đây là cả lý do core/policy tồn tại."""

    def testSameRequestSameOutcome(self):
        for companyId, name, capability in _capabilitiesToCheck():
            payload = sampleInputFor({"inputSchema": capability.inputSchema})
            request = PolicyRequest(identity=IssuedBy.admin,
                                    capability=capability,
                                    inputValue=payload)
            first, second = decide(request), decide(request)
            with self.subTest(company=companyId, capability=name):
                self.assertIs(first.decision, second.decision)
                self.assertEqual(first.reason, second.reason)


class TestHardRulesCannotBeLifted(unittest.TestCase):
    """Những luật KHÔNG quyền nào nâng được. Kiểm bằng assert, không bằng niềm tin."""

    def _anyCapability(self, predicate):
        for _companyId, _name, capability in _capabilitiesToCheck():
            if predicate(capability):
                return capability
        self.skipTest("không có năng lực phù hợp")

    def testWhitelistCannotLiftScheduledTriggerBan(self):
        """Quyền đứng KHÔNG mở được cửa cho cron ghi.

        Whitelist không gắn với nội dung nào, nên nó mở một cánh cửa rộng chứ
        không phải một khe. Nếu đảo thứ tự luật trong core/policy thì ca này đỏ.
        """
        capability = self._anyCapability(
            lambda c: c.riskTier.needsApprovalByDefault)
        outcome = decide(PolicyRequest(
            identity=IssuedBy.scheduledTrigger,
            capability=capability,
            inputValue={},
            whitelistGrant="wl_gia_dinh"))
        self.assertIs(outcome.decision, PolicyDecision.deny)
        self.assertIn("S3", outcome.reason)

    def testPaidCapabilityNeverGetsWhitelistButton(self):
        """"Luôn cho phép tiêu tiền" là câu không ai thật sự muốn nói."""
        for companyId in sorted(MANIFESTS):
            for name, raw in sorted(capabilitiesOf(MANIFESTS[companyId]).items()):
                if not raw.get("paidApi"):
                    continue
                capability = Capability.fromManifest(companyId, raw)
                with self.subTest(company=companyId, capability=name):
                    self.assertFalse(capability.canWhitelist)
                    outcome = decide(PolicyRequest(
                        identity=IssuedBy.admin, capability=capability,
                        inputValue={}))
                    self.assertIs(outcome.decision,
                                  PolicyDecision.allowWithApproval)
                    self.assertIn("TỐN TIỀN THẬT", outcome.consequence)

    def testScheduleAlwaysWaitsEvenWithWhitelist(self):
        """Hẹn giờ + whitelist vẫn phải CHỜ.

        Whitelist trả lời "được làm không"; hẹn giờ trả lời "làm lúc nào". Cho
        whitelist nuốt cái hẹn thì việc chạy ngay — đúng thứ admin vừa bảo đừng.
        """
        capability = self._anyCapability(lambda c: c.canWhitelist)
        outcome = decide(PolicyRequest(
            identity=IssuedBy.admin, capability=capability, inputValue={},
            whitelistGrant="wl_gia_dinh", scheduledAt="2026-12-01T05:30:00Z"))
        self.assertIs(outcome.decision, PolicyDecision.allowWithApproval)


if __name__ == "__main__":
    unittest.main(verbosity=2)
