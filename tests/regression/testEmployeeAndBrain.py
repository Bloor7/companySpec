#!/usr/bin/env python3
"""Employee + Brain — ranh giới phải đứng, không chỉ được khai.

Ca ở đây chứng minh ba thứ mà một manifest đẹp KHÔNG tự chứng minh:
  · `cannot` thật sự thắng `permissions`
  · tính cách không đẻ ra quyền
  · ưu tiên định tuyến không nâng được ranh giới dữ liệu
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO_ROOT)

from brains.router import (  # noqa: E402
    DataBoundaryError, allowedBrainsFor, classificationForPrivacyLevel,
    explainRouting, filterProviderChain, loadBrainPolicy, routeBrains,
)
from core.contracts import (  # noqa: E402
    ActionKind, DataClassification, Employee, Environment, Permission,
    ResourceKind,
)
from core.permissions import (  # noqa: E402
    EMPLOYEES_DIR, EmployeeManifestError, loadEmployee, loadEmployees,
    maxDataClassificationOf, whoCanDo,
)

EMPLOYEES = loadEmployees()
POLICY = loadBrainPolicy()


class TestManifestsAreSound(unittest.TestCase):

    def testEveryEmployeeOnDiskLoads(self):
        """Mọi hồ sơ trong `employees/` phải nạp được, không sót cái nào.

        Bản cũ viết cứng danh sách năm người. Nó đỏ ngày 2026-09-20 khi `ceo`
        được khai thành employee — đúng loại ca thử bắt người ta phải sửa ca
        thử mỗi lần thêm một thứ hợp lệ, và sửa mãi thì có ngày sửa bừa.

        Nay soát TÍNH CHẤT: có bao nhiêu thư mục thì phải nạp được bấy nhiêu.
        Thêm employee không phải sửa ca này; để sót một hồ sơ hỏng thì đỏ.
        """
        import glob
        thuMuc = sorted(
            os.path.basename(os.path.dirname(p)) for p in
            glob.glob(os.path.join(REPO_ROOT, "employees", "*", "employee.yaml")))
        self.assertEqual(sorted(EMPLOYEES), thuMuc)
        self.assertGreaterEqual(len(EMPLOYEES), 5)

    def testCeoIsOnTheList(self):
        """CEO phải là một employee CÓ KHAI BÁO, không phải một ngoại lệ ngầm.

        Đo 20/09: 6/6.146 lời gọi thật mang `employeeId` — tầng Employee đã
        dựng mà gần như không nằm trên đường chạy, vì CEO đi vòng qua nó với
        quyền ngầm định vô hạn.
        """
        self.assertIn("ceo", EMPLOYEES)

    def testEveryEmployeeDeclaresSomethingItCannotDo(self):
        """Không ai được là toàn năng.

        Một employee không có `cannot` nào là một employee chưa ai nghĩ tới
        ranh giới cho nó — và đó là lúc nguy hiểm nhất, vì nó trông như đã được
        thiết kế.
        """
        for employeeId, employee in EMPLOYEES.items():
            with self.subTest(employee=employeeId):
                self.assertTrue(
                    employee.cannot,
                    f"{employeeId} không khai `cannot` nào")

    def testNobodyCanReadSecrets(self):
        """P4 — secret không bao giờ đi qua tay employee, KỂ CẢ sentinel.

        Sentinel soát xem secret có RÒ không; việc đó làm được bằng cách tìm
        dấu vết, không cần cầm giá trị thật.
        """
        for employeeId, employee in EMPLOYEES.items():
            with self.subTest(employee=employeeId):
                self.assertTrue(
                    employee.isForbidden("secret.read"),
                    f"{employeeId} không cấm `secret.read`")
                self.assertFalse(
                    employee.mayDo(ResourceKind.secret, ActionKind.read))

    def testNobodyDeploysProduction(self):
        for employeeId, employee in EMPLOYEES.items():
            with self.subTest(employee=employeeId):
                self.assertFalse(
                    employee.mayDo(ResourceKind.production, ActionKind.deploy),
                    f"{employeeId} deploy được production")


class TestCannotBeatsPermissions(unittest.TestCase):
    """E-2 — `cannot` là luật CỨNG.

    Một luật cấm mà có thể bị một luật cho phép lấn qua thì nó không phải luật
    cấm. Ca này dựng đúng tình huống mâu thuẫn để chứng minh chiều thắng.
    """

    def testExplicitDenyWinsOverExplicitGrant(self):
        conflicted = Employee(
            employeeId="thuNghiem",
            role="test",
            permissions=(Permission(subject="thuNghiem",
                                    resource=ResourceKind.production,
                                    action=ActionKind.deploy),),
            cannot=("production.deploy",))
        self.assertFalse(
            conflicted.mayDo(ResourceKind.production, ActionKind.deploy),
            "permissions lấn qua được cannot — luật cấm không còn là luật cấm")

    def testPersonalityGrantsNothing(self):
        """P3 kế hoạch — personality và permission là hai hệ độc lập."""
        bold = Employee(employeeId="manhDan", role="test",
                        personality=("bold", "ships fast", "breaks things"),
                        permissions=(), cannot=())
        for resource in ResourceKind:
            for action in ActionKind:
                self.assertFalse(
                    bold.mayDo(resource, action),
                    f"tính cách đẻ ra quyền {resource.value}.{action.value}")


class TestScopedPermissions(unittest.TestCase):
    """PM-1 — không có quyền ngầm định. Không khai = không có."""

    def testForgeWritesDevButNotProduction(self):
        forge = EMPLOYEES["forge"]
        self.assertTrue(forge.mayDo(
            ResourceKind.repository, ActionKind.modify,
            environment=Environment.dev, branch="feature/x"))
        self.assertFalse(
            forge.mayDo(ResourceKind.repository, ActionKind.modify,
                        environment=Environment.production, branch="feature/x"),
            "forge ghi được production")

    def testForgeNeverTouchesProtectedBranch(self):
        """R2 — nhánh `main` chỉ admin ghi. Company đẩy nhánh phụ, hết."""
        forge = EMPLOYEES["forge"]
        for branch in ("main", "master", "production"):
            with self.subTest(branch=branch):
                self.assertFalse(
                    forge.mayDo(ResourceKind.repository, ActionKind.modify,
                                environment=Environment.dev, branch=branch),
                    f"forge ghi được vào nhánh được bảo vệ `{branch}`")

    def testSageWritesNowhere(self):
        """Ranh giới mỏng nhất của hệ: chữ trên trang lạ đi vào phần suy luận.

        Giữ bằng QUYỀN HẠN chứ không bằng lời dặn trong prompt (P2). Sage không
        ghi được gì thì một trang web có dụ được nó cũng không làm gì được.
        """
        sage = EMPLOYEES["sage"]
        for action in (ActionKind.create, ActionKind.modify, ActionKind.delete,
                       ActionKind.deploy, ActionKind.send, ActionKind.publish):
            for resource in ResourceKind:
                with self.subTest(resource=resource.value, action=action.value):
                    self.assertFalse(
                        sage.mayDo(resource, action),
                        f"sage làm được {resource.value}.{action.value}")

    def testSentinelCannotFixWhatItAudits(self):
        """Người gác cửa mà tự mở cửa cho mình thì không còn là người gác cửa."""
        sentinel = EMPLOYEES["sentinel"]
        self.assertTrue(sentinel.mayDo(ResourceKind.repository, ActionKind.read))
        self.assertFalse(
            sentinel.mayDo(ResourceKind.repository, ActionKind.modify,
                           environment=Environment.dev))

    def testWhoCanDoReturnsEmptyHonestly(self):
        """Rỗng là câu trả lời hợp lệ: việc này cần admin, không phải chọn nhầm người."""
        self.assertEqual(
            whoCanDo(EMPLOYEES, ResourceKind.production, ActionKind.deploy), ())


class TestManifestValidation(unittest.TestCase):
    """Manifest sai phải NÉM, không được nuốt (O10)."""

    def _writeTemp(self, body: str, folder: str = "thuNghiem"):
        import tempfile
        base = tempfile.mkdtemp(prefix="travisEmp")
        directory = os.path.join(base, folder)
        os.makedirs(directory)
        path = os.path.join(directory, "employee.yaml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        return path

    def testTypoInCannotIsCaught(self):
        """`producton.deploy` viết sai thì luật cấm BIẾN MẤT trong im lặng.

        Người đọc manifest sau này vẫn thấy một dòng trông như hàng rào. Đó
        đúng là loại hỏng mà cả dự án này chống.
        """
        path = self._writeTemp(
            "employeeId: thuNghiem\nrole: test\n"
            "cannot: [producton.deploy]\n")
        with self.assertRaises(EmployeeManifestError) as ctx:
            loadEmployee(path)
        self.assertIn("producton", str(ctx.exception))

    def testUnknownActionIsCaught(self):
        path = self._writeTemp(
            "employeeId: thuNghiem\nrole: test\n"
            "permissions:\n  - { resource: repository, action: yolo }\n")
        with self.assertRaises(EmployeeManifestError):
            loadEmployee(path)

    def testFolderNameMustMatchId(self):
        path = self._writeTemp("employeeId: khacHan\nrole: test\n",
                               folder="thuNghiem")
        with self.assertRaises(EmployeeManifestError):
            loadEmployee(path)


class TestDataBoundary(unittest.TestCase):
    """§29 — "local-first" không có nghĩa dữ liệu không bao giờ rời máy."""

    def testSecretGoesNowhere(self):
        self.assertEqual(
            allowedBrainsFor(DataClassification.secret, POLICY), ())
        with self.assertRaises(DataBoundaryError):
            routeBrains("routine", DataClassification.secret, POLICY)

    def testFreeProvidersNeverGetPrivateData(self):
        """Đây là phép đo 37.282 byte, đóng đinh thành một ca thử."""
        for classification in (DataClassification.private,
                               DataClassification.sensitive):
            allowed = allowedBrainsFor(classification, POLICY)
            for freeProvider in ("groq", "cerebras", "openrouter", "mistral"):
                with self.subTest(data=classification.value,
                                  brain=freeProvider):
                    self.assertNotIn(
                        freeProvider, allowed,
                        f"`{classification.value}` gửi được sang {freeProvider}")

    def testUnknownClassificationIsClosedNotOpen(self):
        """Quên khai một mức mới thì hệ DỪNG, không lặng lẽ gửi đi đâu đó."""
        emptyPolicy = {"dataBoundary": {}, "taskRouting": {}}
        self.assertEqual(
            allowedBrainsFor(DataClassification.internal, emptyPolicy), ())


class TestRoutingCannotEscalate(unittest.TestCase):
    """Ưu tiên KHÔNG nâng được quyền — luật quan trọng nhất của router."""

    def testPreferredBrainIsDroppedWhenBoundaryForbidsIt(self):
        chain = routeBrains(
            taskType="research",
            classification=DataClassification.sensitive,
            policy=POLICY,
            # Cố tình đòi một nhà miễn phí cho dữ liệu nhạy cảm.
            employeePreferred=("groq", "cerebras"))
        self.assertNotIn("groq", chain)
        self.assertNotIn("cerebras", chain)
        self.assertTrue(chain, "chặn sạch tới mức không còn ai — chặn quá tay")

    def testUnhealthyBrainGoesLastNotAway(self):
        """Nhà đang hỏng xuống cuối hàng, KHÔNG bị loại hẳn.

        Nó có thể đã khỏe lại, và một ghế cuối hàng vẫn hơn không còn ghế nào —
        bài học "cả hệ treo vào một bộ não".
        """
        healthy = routeBrains("codeChange", DataClassification.internal, POLICY)
        degraded = routeBrains("codeChange", DataClassification.internal,
                               POLICY, unhealthyBrains=(healthy[0],))
        self.assertEqual(sorted(healthy), sorted(degraded))
        self.assertEqual(degraded[-1], healthy[0])

    def testEveryEmployeePreferenceSurvivesItsOwnClassification(self):
        """Mỗi employee phải còn ít nhất MỘT não ở mức dữ liệu của chính nó.

        Không còn ai nghĩa là employee đó không bao giờ chạy được — một lỗi cấu
        hình im lặng, chỉ lộ ra vào lúc cần dùng.
        """
        for employeeId, employee in EMPLOYEES.items():
            path = os.path.join(EMPLOYEES_DIR, employeeId, "employee.yaml")
            classification = maxDataClassificationOf(path)
            with self.subTest(employee=employeeId):
                chain = routeBrains(
                    "default", classification, POLICY,
                    employeePreferred=employee.preferredBrains,
                    employeeFallback=employee.fallbackBrains)
                self.assertTrue(
                    chain,
                    f"{employeeId} (mức `{classification.value}`) không còn "
                    "bộ não nào dùng được")

    def testExplanationNamesWhatWasBlocked(self):
        """Audit phải trả lời được "vì sao đi tới nhà đó" sau nhiều tuần."""
        chain = routeBrains("research", DataClassification.sensitive, POLICY)
        text = explainRouting("research", DataClassification.sensitive,
                              POLICY, chain)
        self.assertIn("sensitive", text)
        self.assertIn("chặn", text)


class TestPrivacyLevelMapsToClassification(unittest.TestCase):
    """`fallback.riengTu` quyết định prompt bị cắt tới đâu → quyết định gửi cho ai."""

    def testMoreCuttingMeansMoreOpen(self):
        """Cắt NHIỀU hơn thì được gửi RỘNG hơn — thứ tự phải đúng chiều.

        ⚠ Bản đầu chỉ khai hai mức, nên `toiThieu` (cắt nhiều nhất) rơi vào
        mặc định an toàn `sensitive` và bị chặn CHẶT HƠN `canTrong` — ngược
        hoàn toàn. Mặc định an toàn là đúng, nhưng nó không thay được việc
        khai đủ.
        """
        openness = {
            "toiThieu": len(allowedBrainsFor(
                classificationForPrivacyLevel("toiThieu"), POLICY)),
            "canTrong": len(allowedBrainsFor(
                classificationForPrivacyLevel("canTrong"), POLICY)),
            "dayDu": len(allowedBrainsFor(
                classificationForPrivacyLevel("dayDu"), POLICY)),
        }
        self.assertGreaterEqual(openness["toiThieu"], openness["canTrong"])
        self.assertGreater(openness["canTrong"], openness["dayDu"])

    def testUnknownLevelIsTreatedAsMostSensitive(self):
        """Thêm mức mới mà quên khai thì hệ CHẶN và hỏi, không lặng lẽ gửi đi."""
        self.assertIs(classificationForPrivacyLevel("mucLaHoac"),
                      DataClassification.sensitive)


class TestLastResortProviderSurvives(unittest.TestCase):
    """Đừng chặn mất cái phao cứu sinh."""

    def testGroqStaysAvailableForCutPrompts(self):
        """`groq` là LỚP ĐỠ CUỐI, bật 31/08 sau một phép đo thật: cả hai model
        Gemini cùng trả 503 trong một lần gọi.

        Bỏ nó khỏi mức `internal` nghĩa là đúng lúc Claude đã câm VÀ cả hai
        Gemini cùng hỏng, hệ im luôn — tức là im đúng lúc admin cần nó nhất.

        Ca này suýt không tồn tại: bản đầu của brainPolicy.yaml KHÔNG có groq
        ở `internal`, và nó chỉ lộ ra khi 12 ca não phụ đỏ.
        """
        allowed = allowedBrainsFor(
            classificationForPrivacyLevel("canTrong"), POLICY)
        self.assertIn("groq", allowed)

    def testRealFallbackChainSurvivesTheBoundaryAtDefaultPrivacy(self):
        """Chuỗi THẬT trong models.yaml phải còn dùng được ở mức mặc định."""
        import yaml
        with open(os.path.join(REPO_ROOT, "registry", "models.yaml"),
                  encoding="utf-8") as fh:
            models = yaml.safe_load(fh) or {}
        chain = (models.get("nao") or {}).get("chuoi") or []
        self.assertTrue(chain, "models.yaml không khai chuỗi dự phòng nào")

        kept, blocked = filterProviderChain(
            chain, classificationForPrivacyLevel("canTrong"), POLICY)
        self.assertTrue(
            kept,
            f"ranh giới dữ liệu chặn SẠCH chuỗi dự phòng (chặn: {blocked}). "
            "Nghĩa là não phụ không bao giờ chạy được — và nó chỉ chạy đúng "
            "lúc Claude đã câm.")

    def testFullProfileModeBlocksFreeProviders(self):
        """`dayDu` gửi cả hồ sơ đời tư và số dư ví — nhà miễn phí KHÔNG nhận.

        Nghe khó chịu nhưng đúng: bộ não dự phòng chỉ chạy khi Claude đã câm,
        và đúng lúc đó mà gửi số dư ví sang một nhà miễn phí thì cái giá không
        nằm ở chỗ tiện hay không tiện.
        """
        kept, blocked = filterProviderChain(
            [{"nha": "gemini", "model": "x"}, {"nha": "groq", "model": "y"}],
            classificationForPrivacyLevel("dayDu"), POLICY)
        self.assertEqual(kept, ())
        self.assertIn("gemini", blocked)
        self.assertIn("groq", blocked)


if __name__ == "__main__":
    unittest.main(verbosity=2)
