#!/usr/bin/env python3
"""CEO là một employee CÓ KHAI BÁO — và việc khai không được làm gãy gì.

═══════════════════════════════════════════════════════════════════════
VÌ SAO CA NÀY PHẢI CÓ TRƯỚC KHI CHUYỂN NGƯỜI GỌI
═══════════════════════════════════════════════════════════════════════

Đo 2026-09-20: trong 6.146 lời gọi THẬT của bảy ngày, đúng **6 lời gọi** mang
`employeeId` — 0,1%. Tầng Employee đã dựng, đã kiểm, và gần như không nằm
trên đường chạy. Hệ có hai hình: hình trên giấy (Task → Employee → Brain →
Policy) và hình đang chạy (CEO → Policy), và chỉ hình thứ hai mới đúng.

Khai CEO thành employee là **THẮT LẠI**: trước đây nó chưa từng bị `mayDo()`
soát. Mà thắt lại thì có thể gãy — một quyền khai thiếu nghĩa là một năng lực
admin vẫn dùng bỗng bị từ chối, và từ chối ở tầng quyền thì KHÔNG có nút
duyệt để cứu.

Nên cùng kỷ luật đã dùng cho Policy và Memory: **ĐỐI CHIẾU TRƯỚC, CHUYỂN SAU.**

Ca chính là `testCeoCanStillCallEverything`: nó duyệt TOÀN BỘ danh mục CEO
được phép gọi và đòi hồ sơ `ceo` cho qua từng cái. Khai thiếu một dòng quyền
thì nó đỏ ngay, kèm tên năng lực — không phải đợi admin nhắn rồi mới biết.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, HERE)

import yaml  # noqa: E402
from harness import capabilitiesOf, loadManifests  # noqa: E402
from core.contracts import (  # noqa: E402
    ActionKind, Capability, ResourceKind, RiskTier,
)
from core.permissions import (  # noqa: E402
    loadEmployees, maxDataClassificationOf,
)

EMPLOYEES = loadEmployees()
MANIFESTS = loadManifests(includeInternal=False)


def _ceoCallableCapabilities():
    """Mọi năng lực CEO được phép gọi, đọc từ `canBeCalledBy` trong manifest."""
    for companyId in sorted(MANIFESTS):
        spec = MANIFESTS[companyId]
        if "ceo" not in (spec.get("canBeCalledBy") or []):
            continue
        for name, raw in sorted(capabilitiesOf(spec).items()):
            yield companyId, name, Capability.fromManifest(
                companyId, raw, companyResource=spec.get("resource"))


class TestCeoIsADeclaredEmployee(unittest.TestCase):

    def testCeoExists(self):
        self.assertIn(
            "ceo", EMPLOYEES,
            "chưa có employees/ceo/employee.yaml — CEO vẫn đang gọi với "
            "quyền ngầm định vô hạn")

    def testCeoDataClassificationCoversWhatItReads(self):
        """CEO đọc hồ sơ đời tư và số dư ví — đó là `sensitive`.

        Khai thấp hơn thì `brains/router.py` sẽ cho phép gửi gói tin ấy sang
        một nhà miễn phí mà admin chưa đọc điều khoản. Đo một lượt thật từng
        ra 37.282 byte, trong đó có giờ dậy, nghề, nơi ở và số dư từng ví.
        """
        # Đọc qua `maxDataClassificationOf(path)` chứ không qua dataclass:
        # đây là chính sách ĐỊNH TUYẾN (brain nào được nhận gói tin), không
        # phải thuộc tính của con người — lý do ghi trong core/permissions.
        muc = maxDataClassificationOf(
            os.path.join(REPO_ROOT, "employees", "ceo", "employee.yaml"))
        self.assertEqual(muc.value, "sensitive")


class TestSwitchingCallerBreaksNothing(unittest.TestCase):
    """Phép đối chiếu: hồ sơ mới phải cho qua mọi thứ CEO vốn gọi được."""

    def testCeoCanStillCallEverything(self):
        ceo = EMPLOYEES["ceo"]
        thieu = []
        daSoat = 0
        for companyId, name, capability in _ceoCallableCapabilities():
            daSoat += 1
            resource, action = capability.touches
            if not ceo.mayDo(resource, action):
                thieu.append(
                    f"{companyId}.{name} cần `{resource.value}.{action.value}`"
                    f" (riskTier={capability.riskTier.value})")

        self.assertGreater(daSoat, 50, "không soát được danh mục — harness hỏng")
        self.assertEqual(
            thieu, [],
            "Hồ sơ `ceo` khai THIẾU quyền. Chuyển người gọi lúc này sẽ làm "
            "những năng lực sau bị từ chối ở TẦNG QUYỀN — và ở đó không có "
            "nút duyệt nào để cứu:\n  " + "\n  ".join(thieu))

    def testNoPermissionIsDeclaredForNothing(self):
        """Chiều kia: đừng khai thừa. Mỗi dòng quyền phải có năng lực đứng sau.

        Một quyền không ai dùng là một cánh cửa mở sẵn chờ company tiếp theo
        vô tình đi qua. `PM-1` nói không khai = không có; hệ quả ngược lại
        cũng phải đúng: khai rồi thì phải có lý do đọc được.
        """
        canDung = set()
        for _cid, _name, capability in _ceoCallableCapabilities():
            resource, action = capability.touches
            canDung.add((resource, action))

        thua = []
        for permission in EMPLOYEES["ceo"].permissions:
            if (permission.resource, permission.action) not in canDung:
                thua.append(f"{permission.resource.value}."
                            f"{permission.action.value}")
        self.assertEqual(
            thua, [],
            "Hồ sơ `ceo` khai quyền mà KHÔNG năng lực nào cần tới: "
            + ", ".join(thua)
            + ". Bỏ đi — quyền không ai dùng là cửa mở sẵn chờ người đi qua.")


class TestTheHardLimitsHold(unittest.TestCase):
    """`cannot` thắng `permissions`, và nó phải thắng cả với CEO."""

    def testCeoCannotReadSecrets(self):
        ceo = EMPLOYEES["ceo"]
        self.assertFalse(ceo.mayDo(ResourceKind.secret, ActionKind.read))
        self.assertTrue(ceo.isForbidden("secret.read"))

    def testCeoCannotTouchProduction(self):
        ceo = EMPLOYEES["ceo"]
        for action in (ActionKind.deploy, ActionKind.modify):
            with self.subTest(action=action.value):
                self.assertFalse(ceo.mayDo(ResourceKind.production, action))

    def testCeoCannotDelete(self):
        """Xoá không phải quyền đứng của người điều phối."""
        ceo = EMPLOYEES["ceo"]
        for resource in (ResourceKind.repository, ResourceKind.database,
                         ResourceKind.filesystem):
            with self.subTest(resource=resource.value):
                self.assertFalse(ceo.mayDo(resource, ActionKind.delete))

    def testCeoCannotSendTelegramItself(self):
        """CEO trả lời qua gateway; một quyền gửi tin đứng sẵn là mở đường
        cho việc nhắn cho người KHÁC."""
        self.assertFalse(
            EMPLOYEES["ceo"].mayDo(ResourceKind.telegram, ActionKind.send))


class TestPublishIsNotDelete(unittest.TestCase):
    """`riskTier` nói NẶNG CỠ NÀO, `action` nói LÀM GÌ. Đừng suy cái này từ cái kia.

    Bảng suy ép `irreversible` → `delete`, nên ĐĂNG một bài lên web bị soát
    quyền như thể nó XOÁ CẢ KHO. Hệ quả: muốn CEO đăng được bài thì phải cấp
    `repository.delete` — vừa sai nghĩa, vừa là đúng cái quyền mà `forge` và
    `sentinel` đang bị cấm vì lý do hoàn toàn khác.

    Bằng chứng cho thấy đây là lỗ hổng thật chứ không phải chuyện chữ nghĩa:
    trước khi vá, BỐN trong bảy giá trị `ActionKind` (`create`, `publish`,
    `send`, `deploy`) KHÔNG THỂ nào xuất hiện — kể cả `publish`, thứ mà bảng
    duyệt §7 gọi tên riêng thành một dòng.
    """

    def testPublishingAPostIsPublishNotDelete(self):
        spec = yaml.safe_load(open(
            os.path.join(REPO_ROOT, "companies", "panharmonCompany",
                         "companySpec.yaml"), encoding="utf-8"))
        raw = next(c for c in spec["capabilities"] if c["name"] == "dangBai")
        capability = Capability.fromManifest(
            "panharmonCompany", raw, companyResource=spec.get("resource"))
        resource, action = capability.touches

        self.assertEqual(capability.riskTier.value, "irreversible",
                         "đăng công khai vẫn phải là irreversible (G1)")
        self.assertIs(action, ActionKind.publish)
        self.assertIsNot(action, ActionKind.delete)
        self.assertIs(resource, ResourceKind.repository)

    def testDeclaredActionWinsOverTheInferredOne(self):
        khai = Capability(companyId="x", name="y", description="",
                          riskTier=RiskTier.irreversible, maxDurationSec=10,
                          action=ActionKind.publish)
        self.assertIs(khai.touches[1], ActionKind.publish)

    def testNoDeclarationStillInfers(self):
        """Không khai thì vẫn suy như cũ — đây là thay đổi CỘNG THÊM.

        Chiều này quan trọng không kém: 87 năng lực còn lại không khai
        `action`, và chúng phải giữ nguyên hành vi.
        """
        suy = Capability(companyId="x", name="y", description="",
                         riskTier=RiskTier.write, maxDurationSec=10)
        self.assertIs(suy.touches[1], ActionKind.modify)
        doc = Capability(companyId="x", name="y", description="",
                         riskTier=RiskTier.read, maxDurationSec=10)
        self.assertIs(doc.touches[1], ActionKind.read)

    def testBadActionNameThrowsAtLoad(self):
        """Khai sai tên thì NÉM lúc nạp, không nuốt thành mặc định (O10)."""
        with self.assertRaises(ValueError):
            Capability.fromManifest("x", {"name": "y", "riskTier": "write",
                                          "action": "khongCoHanhDongNay"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
